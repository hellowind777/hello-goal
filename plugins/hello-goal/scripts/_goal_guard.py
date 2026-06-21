#!/usr/bin/env python3
"""hello-goal v2.0 — Hybrid Guardian for /goal tasks.

四层级联守护:
  Phase 1:   stop_reason 异常 → 直接 BLOCK（中断恢复）
  Phase 1.5: API 错误模式匹配 → BLOCK（第三方大模型容错恢复）
  Phase 2:   行为结构信号加权 → 明确则直接 BLOCK/PASS
  Phase 3:   LLM 语义兜底 → 仅模糊区间触发（20%-50%）

零外部依赖。语言无关（行为结构分析 + LLM 自然理解任意语言）。

用法（由 CC hook 系统自动调用）:
  python ${CLAUDE_PLUGIN_ROOT}/scripts/_goal_guard.py
"""
import json
import os
import re
import sys
import time

# ============================================================
# 配置
# ============================================================

PLUGIN_DATA_DIR = os.environ.get("CLAUDE_PLUGIN_DATA", "")
PLUGIN_NAME = "hello-goal"
STATE_FILE = (
    os.path.join(PLUGIN_DATA_DIR, ".goal_sessions.json")
    if PLUGIN_DATA_DIR else ""
)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
LLM_TIMEOUT = 8
LLM_MODEL = "claude-3-5-haiku-20241022"

# 信号权重（总和不超过 1.0）
W_NO_TOOLS = 0.30        # 末轮无工具调用
W_TREND_COLLAPSE = 0.25  # 趋势塌缩（消息长度 & 工具调用数下降）
W_STUCK_LOOP = 0.20      # 停滞循环（连续相同工具模式）
W_READONLY_STALL = 0.15  # 只读停滞（连续 Read 无 Write）

BLOCK_THRESHOLD = 0.50   # ≥ 此分数直接 BLOCK，无需 LLM
PASS_THRESHOLD = 0.20    # < 此分数直接 PASS
STOP_HOOK_ACTIVE_MULT = 1.4  # 连续 block 时阈值放大

# API 错误模式 —— 第三方大模型常见异常，/goal 模式下自动恢复继续
_API_ERROR_PATTERNS = [
    r"socket connection was closed unexpectedly",
    r"\b429\b",
    r"\b503\b",
    r"\b502\b",
    r"\b504\b",
    r"rate\s*limit",
    r"too\s+many\s+requests",
    r"overloaded(?:_error)?",
    r"connection\s+(?:reset|refused|timed\s*out|closed)",
    r"fetch\s*failed",
    r"network\s+error",
]

# ============================================================
# 基础工具
# ============================================================

def _read_stdin():
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, IOError):
        return {}


def _block(reason):
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.exit(0)


def _pass(output=None):
    print(json.dumps(output or {}, ensure_ascii=False))
    sys.exit(0)


def _setup_encoding():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ============================================================
# 状态持久化（CLAUDE_PLUGIN_DATA 目录）
# ============================================================

def _load_state():
    if not STATE_FILE or not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_state(state):
    if not STATE_FILE:
        return
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except OSError:
        pass


# ============================================================
# Transcript 读取
# ============================================================

def _read_transcript_tail(transcript_path, num_entries=80):
    """高效读取 transcript JSONL 尾部 N 条记录。"""
    if not transcript_path or not os.path.exists(transcript_path):
        return []
    try:
        size = os.path.getsize(transcript_path)
        read_size = min(size, max(128 * 1024, num_entries * 2048))
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as fh:
            if size > read_size:
                fh.seek(size - read_size)
            lines = fh.readlines()

        entries = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    entries.append(obj)
            except json.JSONDecodeError:
                continue
            if len(entries) >= num_entries:
                break
        entries.reverse()
        return entries
    except Exception:
        return []


# ============================================================
# /goal 活跃检测
# ============================================================

def _is_goal_start(text):
    """判断用户消息是否为 /goal 启动命令（非 clear/status）。"""
    if not text:
        return False
    t = text.strip()
    if not re.match(r'^/goal\b', t):
        return False
    clear_pats = [
        r'^/goal\s+clear\b', r'^/goal\s+stop\b', r'^/goal\s+off\b',
        r'^/goal\s+reset\b', r'^/goal\s+none\b', r'^/goal\s+cancel\b',
        r'^/goal\s+status\b',
    ]
    for pat in clear_pats:
        if re.match(pat, t):
            return False
    if re.match(r'^/goal\s*$', t):
        return False
    return True


def _is_goal_cleared(text):
    """判断用户消息是否为 /goal clear 类命令。"""
    if not text:
        return False
    t = text.strip()
    return bool(re.match(r'^/goal\s+(clear|stop|off|reset|none|cancel)\b', t))


def _detect_goal_active(transcript_path, session_id):
    """检测当前会话中 /goal 是否活跃。

    双信号交叉验证:
      A. transcript 中找到 /goal 启动命令
      B. transcript 中存在最近的 stop_hook_summary（原生 /goal 评估器活动痕迹）

    任一命中 → 判定活跃。结果缓存到插件状态文件。
    每轮先做轻量双向检查（最近条目中的 start/clear），捕获状态切换；
    无切换时信任缓存；无缓存时全量扫描。
    """
    state = _load_state()
    ss = state.get(session_id, {})

    # 轻量双向检查：捕获最近的 /goal 启动或退出，处理反复进入/退出
    recent = _read_transcript_tail(transcript_path, num_entries=15)
    for entry in recent:
        if entry.get("type") == "user":
            msg = entry.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    text = block.get("text", "") if isinstance(block, dict) else str(block)
                    if _is_goal_start(text):
                        ss["goal_detected"] = True
                        ss["goal_checked"] = True
                        ss["detected_at"] = time.time()
                        state[session_id] = ss
                        _save_state(state)
                        return True
                    elif _is_goal_cleared(text):
                        ss["goal_detected"] = False
                        ss["goal_checked"] = True
                        ss["detected_at"] = time.time()
                        state[session_id] = ss
                        _save_state(state)
                        return False

    # 最近条目无状态变更 → 信任缓存
    if ss.get("goal_detected"):
        return True
    if ss.get("goal_checked") and not ss.get("goal_detected"):
        return False

    # 无缓存 → 全量扫描
    entries = _read_transcript_tail(transcript_path, num_entries=120)

    goal_started = False
    goal_cleared = False
    has_recent_summary = False

    for entry in entries:
        etype = entry.get("type", "")

        # 信号 A: /goal 命令
        if etype == "user":
            msg = entry.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    text = block.get("text", "") if isinstance(block, dict) else str(block)
                    if _is_goal_start(text):
                        goal_started = True
                        goal_cleared = False
                    elif _is_goal_cleared(text):
                        goal_cleared = True

        # 信号 B: stop_hook_summary（原生 /goal 评估器产物）
        if etype == "system":
            subtype = entry.get("subtype", "")
            if subtype == "stop_hook_summary":
                has_recent_summary = True

    is_active = (goal_started and not goal_cleared) or has_recent_summary

    # 缓存
    ss["goal_checked"] = True
    ss["goal_detected"] = is_active
    ss["detected_at"] = time.time()
    state[session_id] = ss
    _save_state(state)

    return is_active


# ============================================================
# 行为结构分析
# ============================================================

def _get_assistants(entries):
    return [e for e in entries if e.get("type") == "assistant"]


def _tool_info(entry):
    """从 assistant entry 提取工具调用信息。返回 (count, [names])。"""
    msg = entry.get("message", {})
    content = msg.get("content", [])
    if not isinstance(content, list):
        return 0, []
    tools = [(b.get("name", ""), b.get("input", {}))
             for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
    return len(tools), [t[0] for t in tools]


def _text_len(entry):
    msg = entry.get("message", {})
    content = msg.get("content", [])
    if not isinstance(content, list):
        return 0
    return sum(len(b.get("text", "")) for b in content
               if isinstance(b, dict) and b.get("type") == "text")


def _structural_score(transcript_path):
    """行为结构信号加权评分。

    返回 (score: float 0.0-1.0, flags: dict)。
    纯行为分析，不读文字内容 → 任意语言通用。
    """
    entries = _read_transcript_tail(transcript_path, num_entries=30)
    assistants = _get_assistants(entries)

    if not assistants:
        return 0.0, {}

    score = 0.0
    flags = {}

    # 信号 1: 末轮零工具调用
    last = assistants[-1]
    tc_last, _ = _tool_info(last)
    if tc_last == 0:
        score += W_NO_TOOLS
        flags["no_tools_last_turn"] = True

    # 信号 2: 趋势塌缩（需 ≥3 轮）
    if len(assistants) >= 3:
        w = assistants[-3:]
        lengths = [_text_len(e) for e in w]
        tcounts = [_tool_info(e)[0] for e in w]
        len_drop = lengths[0] > 0 and lengths[-1] < lengths[0] * 0.5
        tool_drop = tcounts[0] > 0 and tcounts[-1] == 0 and any(t > 0 for t in tcounts[:-1])
        if len_drop or tool_drop:
            score += W_TREND_COLLAPSE
            flags["trend_collapse"] = True

    # 信号 3: 停滞循环（连续 3 轮相同工具模式）
    if len(assistants) >= 3:
        patterns = [tuple(_tool_info(e)[1]) for e in assistants[-3:]]
        if len(set(patterns)) == 1 and patterns[0]:
            score += W_STUCK_LOOP
            flags["stuck_loop"] = True

    # 信号 4: 只读停滞（最近 5 轮仅 Read/Glob/Grep，无 Write/Edit/Bash）
    if len(assistants) >= 5:
        read_tools = {"Read", "Glob", "Grep"}
        write_tools = {"Write", "Edit", "Bash"}
        reads = 0
        writes = 0
        for e in assistants[-5:]:
            _, names = _tool_info(e)
            for n in names:
                if n in read_tools:
                    reads += 1
                elif n in write_tools:
                    writes += 1
        if reads >= 3 and writes == 0:
            score += W_READONLY_STALL
            flags["readonly_stall"] = True

    return min(score, 1.0), flags


# ============================================================
# LLM 语义兜底
# ============================================================

def _llm_check(last_assistant_message, stop_reason):
    """调用小模型语义判断：助手是否试图提前放弃任务。

    仅当行为结构信号处于模糊区间（20%-50%）时调用。
    API 不可用 → 返回 None，由调用方保守 BLOCK。
    """
    if not ANTHROPIC_API_KEY:
        return None
    if not last_assistant_message:
        return None

    prompt = (
        "You are a task completion monitor. Analyze whether the assistant's "
        "last message indicates it wants to PREMATURELY STOP or ABANDON the "
        "current task (in any language).\n\n"
        "Signals of premature abandonment:\n"
        "- Wants to pause, defer, or stop before the goal is met\n"
        "- Lowers completion standards ('good enough', 'partial success')\n"
        "- Gives up due to difficulty, exhaustion, or context limits\n"
        "- Delegates remaining work to the user\n"
        "- Only summarizes past work without planning next actions\n\n"
        "The stop_reason was: " + stop_reason + "\n\n"
        "Assistant's last message:\n---\n" +
        last_assistant_message[:4000] + "\n---\n\n"
        "Reply with EXACTLY ONE WORD: BLOCK (if the assistant is trying to "
        "abandon prematurely) or PASS (if genuinely continuing or properly "
        "completed). When uncertain, reply BLOCK."
    )

    try:
        import urllib.request as _req
        url = ANTHROPIC_BASE_URL.rstrip("/") + "/v1/messages"
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = json.dumps({
            "model": LLM_MODEL,
            "max_tokens": 10,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")

        req = _req.Request(url, data=body, headers=headers)
        with _req.urlopen(req, timeout=LLM_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        text = "".join(
            b.get("text", "") for b in result.get("content", [])
            if isinstance(b, dict) and b.get("type") == "text"
        )
        return "BLOCK" in text.upper()

    except Exception:
        return None


# ============================================================
# API 错误检测（第三方大模型 /goal 容错恢复）
# ============================================================

def _match_api_error(text):
    """检查文本是否匹配已知 API 错误模式。返回匹配的模式或 None。"""
    if not isinstance(text, str) or not text:
        return None
    for pattern in _API_ERROR_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return pattern
    return None


def _detect_api_error(ctx):
    """多源检测 API 错误：stop_reason → assistant 消息 → transcript 尾部。
    返回 (detected: bool, info: str)。
    """
    # 源 1: stop_reason 字段
    sr = ctx.get("stop_reason", "")
    pat = _match_api_error(sr)
    if pat:
        return True, "stop_reason 匹配 " + pat

    # 源 2: last_assistant_message（LLM 可能直接报告了错误）
    last_msg = ctx.get("last_assistant_message", "")
    pat = _match_api_error(last_msg)
    if pat:
        return True, "assistant 消息匹配 " + pat

    # 源 3: transcript 尾部（系统错误 / assistant 文本 / user 回显）
    transcript_path = ctx.get("transcript_path", "")
    entries = _read_transcript_tail(transcript_path, num_entries=20)
    for entry in entries:
        etype = entry.get("type", "")
        msg = entry.get("message", {})
        content = msg.get("content", []) if isinstance(msg, dict) else []

        texts = []
        if isinstance(content, list):
            for block in content:
                t = block.get("text", "") if isinstance(block, dict) else str(block)
                if t:
                    texts.append(t)

        pat = _match_api_error(" ".join(texts))
        if pat:
            return True, f"transcript {etype} 匹配 " + pat

        # 也检查 system entry 的 error / reason / detail 字段
        if etype == "system":
            for field in ("error", "reason", "detail"):
                val = entry.get(field, "")
                if isinstance(val, str):
                    pat = _match_api_error(val)
                    if pat:
                        return True, f"transcript system.{field} 匹配 " + pat

    return False, ""


# ============================================================
# 事件处理
# ============================================================

def handle_stop(ctx):
    """Stop hook: 核心守护逻辑。"""
    session_id = ctx.get("session_id", "")
    transcript_path = ctx.get("transcript_path", "")
    stop_reason = ctx.get("stop_reason", "end_turn")
    stop_hook_active = ctx.get("stop_hook_active", False)
    last_msg = ctx.get("last_assistant_message", "")

    # Phase 0: /goal 检测，非 /goal 会话零干预
    if not _detect_goal_active(transcript_path, session_id):
        return _pass()

    # Phase 1: 中断恢复 —— 非正常结束直接 BLOCK
    if stop_reason != "end_turn":
        return _block(
            "[hello-goal] 检测到异常中断 (stop_reason=" + stop_reason + ")。"
            "/goal 任务继续执行。"
        )

    # Phase 1.5: API 错误恢复 —— 第三方大模型常见错误时 /goal 继续
    api_error, api_info = _detect_api_error(ctx)
    if api_error:
        return _block(
            "[hello-goal] 检测到 API 错误 (" + api_info + ")。"
            "/goal 任务自动恢复，继续执行。"
        )

    # Phase 2: 行为结构评分
    score, flags = _structural_score(transcript_path)
    threshold = BLOCK_THRESHOLD
    if stop_hook_active:
        threshold = min(BLOCK_THRESHOLD * STOP_HOOK_ACTIVE_MULT, 0.95)

    if score >= threshold:
        flag_str = ", ".join(flags.keys()) if flags else "行为异常"
        return _block(
            "[hello-goal] 检测到任务可能停滞 (信号: " + flag_str + ")。"
            "/goal 任务继续执行。"
        )

    if score < PASS_THRESHOLD:
        return _pass()

    # Phase 3: LLM 语义兜底（模糊区间 20% ~ threshold）
    result = _llm_check(last_msg, stop_reason)

    if result is True:
        return _block(
            "[hello-goal] 语义分析检测到任务可能提前终止。"
            "/goal 任务继续执行。"
        )
    elif result is False:
        return _pass()
    else:
        # API 不可用 → 保守 BLOCK
        return _block(
            "[hello-goal] 语义分析不可用，保守策略：/goal 任务继续执行。"
        )


def handle_session_start(ctx):
    """SessionStart hook: 清理过期状态，初始化会话追踪。"""
    session_id = ctx.get("session_id", "")
    state = _load_state()

    cleaned = {}
    now = time.time()
    for sid, ss in state.items():
        if sid == session_id:
            cleaned[sid] = ss
            continue
        if now - ss.get("detected_at", 0) < 86400:
            cleaned[sid] = ss

    if session_id not in cleaned:
        cleaned[session_id] = {"detected_at": now}
    elif "detected_at" not in cleaned[session_id]:
        cleaned[session_id]["detected_at"] = now

    _save_state(cleaned)
    return _pass()


def handle_post_compact(ctx):
    """PostCompact hook: 压缩后刷新 /goal 检测缓存。"""
    session_id = ctx.get("session_id", "")
    state = _load_state()
    ss = state.get(session_id, {})
    # 清除检测缓存，下次 Stop hook 重新检测
    ss.pop("goal_checked", None)
    ss.pop("goal_detected", None)
    state[session_id] = ss
    _save_state(state)
    return _pass()


# ============================================================
# 入口
# ============================================================

DISPATCH = {
    "Stop": handle_stop,
    "SessionStart": handle_session_start,
    "PostCompact": handle_post_compact,
}


def main():
    _setup_encoding()
    ctx = _read_stdin()
    event = ctx.get("hook_event_name", "")
    handler = DISPATCH.get(event, lambda c: _pass())
    handler(ctx)


if __name__ == "__main__":
    main()
