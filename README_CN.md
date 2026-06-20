# goal-hook

Claude Code 插件，为 `/goal` 会话提供可靠的 Stop hook。当内置 prompt 型 goal 评估器因 JSON 校验失败而中断任务时，本插件保持任务继续运行。

## 工作原理

插件注册一个 command 型 Stop hook，只检查一个状态文件：

```
.goal_status.json 不存在   → pass（非 /goal 会话，零干预）
status = "in_progress"      → block（保持 goal 循环运行）
status = "terminated"       → pass（目标达成，自动清理）
```

GOAL_PROMPT 在启动时写入 `in_progress`，完成时写入 `terminated`。其余由 hook 处理。

### 为什么需要

Claude Code 的 `/goal` 使用 prompt 型 Stop hook，由一个小模型评估进度。该模型可能输出格式错误的 JSON，触发 **"Stop hook error: JSON validation failed"**——可能在任务中途终止会话。

本插件与内置 hook 并行运行。当内置 hook 失败时，command 型 hook 仍根据磁盘上的文件做出 block 判定——任务无中断继续。

### 崩溃恢复

如果 `/goal` 会话在写入 `terminated` 前崩溃，残留的 `in_progress` 文件在 7 天无活动后自动过期。

## 安装

**方法一：本地市场（推荐）**

```bash
git clone https://github.com/hellowind777/goal-hook.git D:/GitHub/dev/plugin/goal-hook
```

在 `~/.claude/settings.json` 中添加：

```json
{
  "enabledPlugins": {
    "goal-hook@goal-hook-marketplace": true
  },
  "extraKnownMarketplaces": {
    "goal-hook-marketplace": {
      "source": {
        "path": "D:\\GitHub\\dev\\plugin\\goal-hook",
        "source": "directory"
      }
    }
  }
}
```

**方法二：手动复制**

将插件目录复制到 `~/.claude/plugins/goal-hook/`，然后启用：

```json
{
  "enabledPlugins": {
    "goal-hook@local": true
  }
}
```

任选一种方法后重启 Claude Code。

## 使用

GOAL_PROMPT 在启动时写入状态文件：

```python
import json
json.dump({"status": "in_progress", "reason": "任务执行中"},
          open("scripts/data/.goal_status.json", "w", encoding="utf-8"))
```

完成时写入：

```python
import json
json.dump({"status": "terminated", "reason": "全部检查通过"},
          open("scripts/data/.goal_status.json", "w", encoding="utf-8"))
```

非 `/goal` 会话完全不受影响——无文件即无干预。

## 推荐配套设置

防止 8 次 block 上限误杀长任务：

```json
"CLAUDE_CODE_STOP_HOOK_BLOCK_CAP": "1000"
```

## 文件

| 文件 | 用途 |
|------|------|
| `hooks/hooks.json` | Stop hook 注册 |
| `scripts/_goal_check.py` | 状态文件检查（93 行） |
| `.claude-plugin/plugin.json` | 插件元数据 |

## 许可证

Apache-2.0
