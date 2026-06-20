#!/usr/bin/env python3
"""通用 goal Stop hook —— 自动检测 /goal 会话，接管循环控制。

核心逻辑：
  1. 从 stdin 读取 transcript_path，检查是否为 /goal 会话
  2. 非 goal 会话 → pass（不干预）
  3. goal 会话 + 无状态文件 → 自动创建 in_progress + block（auto-bootstrap）
  4. goal 会话 + in_progress → block（继续循环）
  5. goal 会话 + terminated → pass（目标达成）

工作机制：
  - 通过读取 transcript JSONL 的前若干行检测 /goal 命令
  - goal 会话首次触发时自动写 in_progress，解决自然语言 goal 无文件问题
  - block 的 reason 中告知 Claude 如何写 terminated 来结束循环
  - 非 goal 会话完全不受影响

用法：
  python ${CLAUDE_PLUGIN_ROOT}/scripts/_goal_check.py
"""
import json
import os
import sys

STATUS_FILE = "scripts/data/.goal_status.json"

# 写完 terminated 后删除状态文件，避免残留到下次非 goal 会话
CLEANUP_ON_TERMINATED = True

HOW_TO_TERMINATE = (
    "Goal 任务进行中。当你确认目标已达成时，执行以下命令结束循环："
    "python -c \"import json; json.dump({'status':'terminated','reason':'目标达成'},"
    " open('scripts/data/.goal_status.json','w',encoding='utf-8'))\""
)


def _emit(decision: str, reason: str) -> None:
    print(json.dumps({"decision": decision, "reason": reason}, ensure_ascii=False))
    sys.exit(0)


def _read_stdin() -> dict:
    """读取 hook stdin JSON，容错处理。"""
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, IOError):
        return {}


def _is_goal_session(transcript_path: str) -> bool:
    """通过读取 transcript 前若干行判断是否为 /goal 会话。

    Transcript 为 JSONL 格式，每行一个 JSON 对象。
    查找前 20 行中是否包含 /goal 命令或 Goal set 标记。
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return False

    try:
        with open(transcript_path, "r", encoding="utf-8") as fh:
            lines_read = 0
            for line in fh:
                lines_read += 1
                if lines_read > 20:
                    break
                line_lower = line.lower()
                # 检测 /goal 命令的精确标记（XML 标签格式，避免误判）
                if '<command-name>/goal</command-name>' in line_lower:
                    return True
                # 备选：Goal set 系统确认消息
                if '"goal set:"' in line_lower:
                    return True
    except (IOError, OSError):
        pass

    return False


def _read_status() -> dict | None:
    """读取状态文件，不存在返回 None。"""
    if not os.path.exists(STATUS_FILE):
        return None
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, IOError):
        return None


def _write_in_progress() -> None:
    os.makedirs(os.path.dirname(STATUS_FILE) or ".", exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as fh:
        json.dump({"status": "in_progress", "reason": "Goal 任务循环执行中"}, fh, ensure_ascii=False)


def main() -> None:
    hook_input = _read_stdin()
    transcript_path = hook_input.get("transcript_path", "")

    # 非 goal 会话 → 完全放行
    if not _is_goal_session(transcript_path):
        _emit("pass", "非 goal 会话，不干预")

    # ── 以下是 goal 会话 ──
    status_data = _read_status()

    # Auto-bootstrap: goal 会话首次 Stop，自动创建 in_progress
    if status_data is None:
        _write_in_progress()
        _emit("block", "检测到 /goal 会话，自动激活循环保护。" + HOW_TO_TERMINATE)

    status = status_data.get("status", "")

    if status == "terminated":
        if CLEANUP_ON_TERMINATED:
            try:
                os.remove(STATUS_FILE)
            except OSError:
                pass
        _emit("pass", f"目标达成: {status_data.get('reason', '完成')}")

    elif status == "in_progress":
        _emit("block", f"Goal 循环中: {status_data.get('reason', '继续执行')}。" + HOW_TO_TERMINATE)

    else:
        # 未知状态 → 保守处理
        _emit("pass", f"Goal 状态未知 '{status}'，放行由内置 hook 判定")


if __name__ == "__main__":
    main()
