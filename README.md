# goal-hook

A Claude Code plugin that provides a reliable Stop hook for `/goal` sessions. When the built-in prompt-based goal evaluator fails with JSON validation errors, this plugin keeps your task running.

## How It Works

The plugin registers a command-type Stop hook that checks a single status file:

```
.goal_status.json missing  → pass (not a /goal session, no interference)
status = "in_progress"      → block (keep the goal loop running)
status = "terminated"       → pass (goal achieved, auto-cleanup)
```

Your GOAL_PROMPT writes `in_progress` at startup and `terminated` on completion. The hook does the rest.

### Why This Matters

Claude Code's `/goal` uses a prompt-type Stop hook that asks a small model to evaluate progress. That model can output malformed JSON, triggering **"Stop hook error: JSON validation failed"** — which can kill your session mid-task.

This plugin runs alongside the built-in hook. When the built-in hook fails, the command-type hook still blocks based on the file on disk — your task continues uninterrupted.

### Crash Recovery

If a `/goal` session crashes before writing `terminated`, the stale `in_progress` file auto-expires after 7 days of inactivity.

## Installation

**Method 1: Local Marketplace (recommended)**

```bash
git clone https://github.com/hellowind777/goal-hook.git D:/GitHub/dev/plugin/goal-hook
```

Add to `~/.claude/settings.json`:

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

**Method 2: Manual Copy**

Copy the plugin directory to `~/.claude/plugins/goal-hook/`, then enable:

```json
{
  "enabledPlugins": {
    "goal-hook@local": true
  }
}
```

Restart Claude Code after either method.

## Usage

Your GOAL_PROMPT writes the status file at startup:

```python
import json
json.dump({"status": "in_progress", "reason": "Task in progress"},
          open("scripts/data/.goal_status.json", "w", encoding="utf-8"))
```

And on completion:

```python
import json
json.dump({"status": "terminated", "reason": "All checks passed"},
          open("scripts/data/.goal_status.json", "w", encoding="utf-8"))
```

Non-`/goal` sessions are completely unaffected — no file means no interference.

## Recommended Companion Setting

Prevent the 8-block limit from killing long-running tasks:

```json
"CLAUDE_CODE_STOP_HOOK_BLOCK_CAP": "1000"
```

## Files

| File | Purpose |
|------|---------|
| `hooks/hooks.json` | Stop hook registration |
| `scripts/_goal_check.py` | Status file checker (93 lines) |
| `.claude-plugin/plugin.json` | Plugin metadata |

## License

Apache-2.0
