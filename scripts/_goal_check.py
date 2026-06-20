#!/usr/bin/env python3
"""通用 goal Stop hook —— 检查 .goal_status.json 判定是否允许停止会话。

与任何具体 GOAL_PROMPT 解耦，只依赖一个约定：
提示词完成任务后写入 scripts/data/.goal_status.json 文件，内容为 {"status": "terminated", ...}。

本脚本被 Stop hook 调用，stdout 输出决定是否阻止停止：
  {"decision": "block", "reason": "..."}  阻止停止，Claude 继续工作
  {"decision": "pass",  "reason": "..."}  允许停止（仅当 .goal_status.json status=terminated）

用法：
  直接作为 command-type Stop hook 的 command：
  python ${CLAUDE_PLUGIN_ROOT}/scripts/_goal_check.py
"""
import json
import os
import sys

STATUS_FILE = "scripts/data/.goal_status.json"


def _emit(decision: str, reason: str) -> None:
    """输出纯 JSON 到 stdout，sys.exit(0)。"""
    print(json.dumps({"decision": decision, "reason": reason}, ensure_ascii=False))
    sys.exit(0)


def main() -> None:
    if not os.path.exists(STATUS_FILE):
        _emit("block", "目标未完成，继续执行当前任务。达成后请写入 scripts/data/.goal_status.json")
        return

    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, IOError) as exc:
        _emit("block", f"状态文件读取异常 ({exc})，继续循环")
        return

    if data.get("status") == "terminated":
        _emit("pass", f"目标达成: Round {data.get('round', '?')}")
    else:
        _emit("block", f"目标未完成: {data.get('reason', '继续执行当前任务')}")


if __name__ == "__main__":
    main()
