#!/usr/bin/env python3
"""hello-goal v2.3.5 — Global API Recovery + Hybrid /goal Guardian.

硬编码 JSON 输出 —— 最终 stdout 输出永远是代码写死的合法 JSON，
LLM 语义分析只影响内部决策分支，绝不直接或间接出现在 hook 的 stdout 上。
使用 print() 走 sys.stdout 通道，确保 CC 能 100% 捕获。
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

ANTHROPIC_API_KEY = (
    os.environ.get("ANTHROPIC_API_KEY", "")
    or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
)
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
LLM_TIMEOUT = 8
# 语义分析使用轻量模型：从 CC 环境变量读取，不硬编码默认值
# —— 不同 API 提供商模型名不同（DeepSeek / Anthropic / 其他），留空则降级为保守 BLOCK
LLM_MODEL = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "")
HOOK_START_TIME = time.time()
HOOK_BUDGET_SEC = 25  # 留 5 秒余量给 JSON 输出和进程清理（hooks.json timeout=30s）

# 信号权重（总和不超过 1.0）
W_NO_TOOLS = 0.30        # 末轮无工具调用
W_TREND_COLLAPSE = 0.25  # 趋势塌缩（消息长度 & 工具调用数下降）
W_STUCK_LOOP = 0.20      # 停滞循环（连续相同工具模式）
W_READONLY_STALL = 0.15  # 只读停滞（连续 Read 无 Write）

PASS_THRESHOLD = 0.20    # < 此分数直接 PASS，≥ 此分数进入 LLM 语义分析

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
    """从 stdin 读取 CC 传入的 JSON 上下文。
    捕获所有可能的解码/解析异常 —— 任何输入问题都以空上下文兜底，
    不会让 hook 因 stdin 读取失败而崩溃。"""
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


# ---- 核心 I/O ----
# 所有 stdout 输出均为硬编码的合法 JSON —— LLM 语义分析只影响内部决策分支，
# 最终输出的 JSON 字符串由代码写死，绝不经过 LLM 生成，从根本消除 JSON 校验失败风险。


def _setup_encoding():
    """尝试将 sys.stdout/stderr 配置为 UTF-8，失败不阻塞。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _block(reason):
    """阻止 CC 退出，任务继续。输出硬编码 JSON —— 绝不依赖 LLM 生成。"""
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.exit(0)


def _pass(output=None):
    """放行，不干预 CC。输出空 JSON 对象 —— 最简格式，最大兼容性。"""
    print(json.dumps(output or {}, ensure_ascii=False))
    sys.exit(0)


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

def _extract_text(entry):
    """从 transcript entry 提取全部文本内容（跨所有 content block）。"""
    msg = entry.get("message", {})
    content = msg.get("content", [])
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict):
            t = block.get("text", "")
            if t:
                parts.append(t)
    return " ".join(parts)


def _has_goal_set_marker(text):
    """CC 原生 goal 激活标记: 'Goal set:'。"""
    if not text:
        return False
    return bool(re.search(r'\bGoal set:', text, re.IGNORECASE))


def _has_goal_cleared_marker(text):
    """CC 原生 goal 清除标记: 'Goal cleared:'。"""
    if not text:
        return False
    return bool(re.search(r'\bGoal cleared:', text, re.IGNORECASE))


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


def _scan_for_goal_markers(entries):
    """扫描 transcript 条目，检测 CC 原生 goal 标记和 /goal 命令。

    返回 (goal_set_found, goal_cleared_found, goal_cmd_found, goal_clear_cmd_found,
            has_stop_hook_summary)。

    goal_set_found / goal_cleared_found 按时间序处理：
    后出现的标记覆盖先出现的（处理「清除后重新设置」场景）。
    """
    goal_set_found = False
    goal_cleared_found = False
    goal_cmd_found = False
    goal_clear_cmd_found = False
    has_stop_hook_summary = False

    for entry in entries:
        etype = entry.get("type", "")
        etext = _extract_text(entry)

        # 信号 A: CC 原生 goal 标记（最权威）
        if _has_goal_set_marker(etext):
            goal_set_found = True
            goal_cleared_found = False  # 重新设置 → 重置清除状态
        if _has_goal_cleared_marker(etext):
            goal_cleared_found = True

        # 信号 B: 用户 /goal 命令（备用）
        if etype == "user":
            if _is_goal_start(etext):
                goal_cmd_found = True
                goal_clear_cmd_found = False
            elif _is_goal_cleared(etext):
                goal_clear_cmd_found = True

        # 信号 C: stop_hook_summary（仅作确认，不独立触发）
        if etype == "system" and entry.get("subtype") == "stop_hook_summary":
            has_stop_hook_summary = True

    return (goal_set_found, goal_cleared_found, goal_cmd_found,
            goal_clear_cmd_found, has_stop_hook_summary)


def _detect_goal_active(transcript_path, session_id):
    """检测当前会话中 /goal 是否活跃。

    三级信号体系（按可靠性降序）:
      A. CC 原生标记 "Goal set:" / "Goal cleared:" —— 零误判
      B. 用户 /goal 命令解析 —— 备用
      C. stop_hook_summary 条目 —— 仅确认，不独立触发

    正确处理同一会话反复进出 /goal 的场景：
      - Goal cleared → 新 Goal set → 仍活跃（时间序判定）
      - 意外中断（stop_reason 异常）→ 由 handle_stop Phase 1 拦截
      - 人工 /goal clear → CC 生成 Goal cleared: → 本函数返回 False
      - 模型偷懒降级 → 由 handle_stop Phase 2 行为信号+LLM 混合拦截
    """
    state = _load_state()
    ss = state.get(session_id, {})

    # Phase 1: 缓存快速路径 —— 已知非 /goal，但需快速复查防重新进入
    if ss.get("goal_checked") and not ss.get("goal_detected"):
        recent = _read_transcript_tail(transcript_path, num_entries=5)
        for entry in recent:
            etext = _extract_text(entry)
            if _has_goal_set_marker(etext) or (
                entry.get("type") == "user" and _is_goal_start(etext)
            ):
                # 检测到重新进入 /goal → 清除缓存，进入 Phase 3 完整检测
                ss.pop("goal_checked", None)
                state[session_id] = ss
                _save_state(state)
                break
        else:
            return False

    # Phase 2: 已知 /goal 活跃 → 时间序判定 set vs clear
    if ss.get("goal_detected"):
        recent = _read_transcript_tail(transcript_path, num_entries=20)
        last_set = -1
        last_clear = -1
        for i, entry in enumerate(recent):
            etext = _extract_text(entry)
            if _has_goal_set_marker(etext):
                last_set = i
            if _has_goal_cleared_marker(etext):
                last_clear = i
            if entry.get("type") == "user":
                if _is_goal_start(etext):
                    last_set = i
                elif _is_goal_cleared(etext):
                    last_clear = i

        # 最后出现的标记决定状态
        if last_clear >= 0 and last_clear > last_set:
            # Clear 是最后动作 → goal 已结束
            ss["goal_detected"] = False
            ss["goal_checked"] = True
            ss["detected_at"] = time.time()
            state[session_id] = ss
            _save_state(state)
            return False

        if last_set >= 0 and last_set >= last_clear:
            # Set 是最后动作（或与 clear 同位但 set 优先）→ 仍活跃
            return True

        # 无 set/clear 标记 → 检查原生评估器是否仍在运行
        has_summary = any(
            e.get("type") == "system" and e.get("subtype") == "stop_hook_summary"
            for e in recent
        )
        if not has_summary:
            # 无任何活跃证据 → 清除粘性状态，进入 Phase 3 重新检测
            ss.pop("goal_detected", None)
            ss.pop("goal_checked", None)
            state[session_id] = ss
            _save_state(state)
            # fall through to Phase 3
        else:
            return True

    # Phase 3: 无缓存（首次检测 / PostCompact / 状态失效）→ 先轻量后全量
    recent = _read_transcript_tail(transcript_path, num_entries=20)
    gs, gc, gcmd, gclr, hss = _scan_for_goal_markers(recent)

    if gs and not gc:
        is_active = True
    elif gcmd and not gclr:
        is_active = True
    elif not gs and not gcmd:
        entries = _read_transcript_tail(transcript_path, num_entries=150)
        gs, gc, gcmd, gclr, hss = _scan_for_goal_markers(entries)

        if gs and not gc:
            is_active = True
        elif gcmd and not gclr:
            is_active = True
        elif hss and (gs or gcmd or ss.get("goal_detected")):
            is_active = True
        else:
            is_active = False
    else:
        is_active = False

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

def _llm_check(last_assistant_message, stop_reason, flags=None):
    """调用小模型语义判断：助手是否试图提前放弃任务。

    flags 为行为结构信号字典，用于给 LLM 提供行为上下文。
    所有 score ≥ PASS_THRESHOLD 的场景统一经此语义分析。
    API 不可用 → 返回 None，由调用方保守 BLOCK。
    """
    if not ANTHROPIC_API_KEY:
        return None
    if not ANTHROPIC_BASE_URL:
        return None
    if not LLM_MODEL:
        return None
    if not last_assistant_message:
        return None

    # 行为信号上下文
    behavior_context = ""
    if flags:
        signal_desc = {
            "no_tools_last_turn": "Assistant's last turn had NO tool calls",
            "trend_collapse": "Message length or tool call count is trending down",
            "stuck_loop": "Assistant repeated the same tool pattern 3+ times",
            "readonly_stall": "Last 5 turns: only Read/Glob/Grep, no Write/Edit/Bash",
        }
        parts = [signal_desc[k] for k in flags if k in signal_desc]
        if parts:
            behavior_context = (
                "Behavioral signals detected (these are heuristics, "
                "may be false positives for tasks winding down normally):\n- "
                + "\n- ".join(parts) + "\n\n"
            )

    prompt = (
        "You are a task completion monitor. Analyze whether the assistant's "
        "last message indicates it wants to PREMATURELY STOP or ABANDON the "
        "current task (in any language).\n\n"
        + behavior_context +
        "Signals of premature abandonment:\n"
        "- Wants to pause, defer, or stop before the goal is met\n"
        "- Lowers completion standards ('good enough', 'partial success')\n"
        "- Gives up due to difficulty, exhaustion, or context limits\n"
        "- Delegates remaining work to the user\n"
        "- Only summarizes past work without planning next actions\n\n"
        "However, if the behavioral signals above look like normal task "
        "wind-down (final report, comprehensive summary, test results "
        "compilation) and the assistant's text indicates genuine completion, "
        "reply PASS.\n\n"
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
        clean = text.upper().strip()
        if clean.startswith("BLOCK"):
            return True
        if clean.startswith("PASS"):
            return False
        return None  # 无法解析 → 保守 BLOCK

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
    """Stop hook: 核心守护逻辑。

    Phase 0 (全局): API 错误检测 —— 无论是否 /goal 模式，API 错误中断所有任务，
                   必须自动恢复。socket 断开、429/502/503 等均为第三方大模型
                   瞬时故障，不应让任务永久中断。
    Phase 1 (/goal): 正常结束的 stop 才进入 /goal 专属守护（异常中断 + 行为信号
                     + LLM 语义分析混合判定）。
    """
    session_id = ctx.get("session_id", "")
    transcript_path = ctx.get("transcript_path", "")
    stop_reason = ctx.get("stop_reason", "end_turn")
    last_msg = ctx.get("last_assistant_message", "")

    # Phase 0 (全局): API 错误检测 —— 优先于 /goal 检查，全局响应
    api_error, api_info = _detect_api_error(ctx)
    if api_error:
        return _block("继续")

    # Phase 1: /goal 检测，非 /goal 会话后续不再干预
    if not _detect_goal_active(transcript_path, session_id):
        return _pass()

    # Phase 2: 中断恢复 —— 非正常结束直接 BLOCK
    if stop_reason != "end_turn":
        return _block("继续")

    # Phase 3: 行为信号 + LLM 语义分析 —— 统一混合判定
    score, flags = _structural_score(transcript_path)

    if score < PASS_THRESHOLD:
        return _pass()

    # score ≥ PASS_THRESHOLD → 存在行为信号，交 LLM 语义分析最终裁决
    # 时间预算保护：剩余时间不足 15 秒则跳过 LLM，保守 BLOCK
    elapsed = time.time() - HOOK_START_TIME
    if elapsed > HOOK_BUDGET_SEC:
        return _block("继续")

    result = _llm_check(last_msg, stop_reason, flags)

    if result is True:
        return _block("继续")
    elif result is False:
        return _pass()
    else:
        return _block("继续")


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
    """PostCompact hook: 清除 goal_checked 强制重新验证，但保留 goal_detected
    作为粘性先验知识 —— CC 在 compact 后继续生成 stop_hook_summary，
    配合先验知识可确认 goal 仍活跃。"""
    session_id = ctx.get("session_id", "")
    state = _load_state()
    ss = state.get(session_id, {})
    ss.pop("goal_checked", None)
    # 保留 goal_detected —— compact 不改变 goal 活跃状态
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
    try:
        _setup_encoding()
        ctx = _read_stdin()
        event = ctx.get("hook_event_name", "")
        handler = DISPATCH.get(event, lambda c: _pass())
        handler(ctx)
    except Exception:
        # 任何未预期异常 → 保守 BLOCK，确保 /goal 任务不丢失
        try:
            _block("继续")
        except Exception:
            sys.exit(0)


if __name__ == "__main__":
    main()
