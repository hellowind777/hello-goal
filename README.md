<div align="center">
  <img src="./readme_images/01-hero-banner.svg" alt="goal-hook" width="800">
</div>

# goal-hook

A Claude Code plugin that keeps `/goal` sessions alive when the built-in Stop hook fails. File-based, no dependencies, crash-safe.

[![Version](https://img.shields.io/badge/version-1.0.8-orange.svg)](./RELEASE_NOTES.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE)
[![LINUX DO](https://img.shields.io/badge/LINUX_DO-recognized-0A84FF?logo=linux&logoColor=white)](https://linux.do)

[English](./README.md) · [简体中文](./README_CN.md)

> This project is recognized by the [LINUX DO](https://linux.do) community.

## Table of Contents

<details>
<summary><strong>Click to expand</strong></summary>

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Recommended Settings](#recommended-settings)
- [Files](#files)
- [Version History](#version-history)
- [FAQ](#faq)
- [License](#license)

</details>

## Overview

Claude Code's `/goal` uses a prompt-type Stop hook that asks a small model to evaluate progress. That model can output malformed JSON, causing **"Stop hook error: JSON validation failed"** — which kills your session mid-task.

**goal-hook** runs alongside the built-in hook as a command-type backup. When the built-in hook fails, this plugin still blocks based on a file on disk. Your task keeps running.

### The Problem It Solves

| Scenario | Without goal-hook | With goal-hook |
|----------|-------------------|----------------|
| Built-in hook outputs bad JSON | Session terminates | Blocked by file state, task continues |
| Context compaction resets state | Lost | File survives on disk |
| Session crash leaves stale state | Permanent block | Auto-expires after 7 days |

## How It Works

The plugin registers a command-type Stop hook that checks a single status file (`scripts/data/.goal_status.json`):

<div align="center">
  <img src="./readme_images/architecture.svg" alt="Architecture" width="640">
</div>

**Three states:**

| File State | Hook Action | When |
|------------|-------------|------|
| File missing | **Pass** (no interference) | Not a `/goal` session |
| `status: "in_progress"` | **Block** (keep running) | Goal loop active |
| `status: "terminated"` | **Pass + cleanup** | Goal achieved |

### Crash Recovery

If a `/goal` session crashes before writing `terminated`, the stale `in_progress` file auto-expires after **168 hours (7 days)** of inactivity. Active GOAL_PROMPTs re-write the file every round, so live tasks never trigger the timeout.

### Design Principles

- **Zero dependencies** — no transcript reading, no env var probing, no CC internals
- **File-persistent** — survives context compaction
- **Non-invasive** — no file means no interference for non-`/goal` sessions

## Quick Start

### Prerequisites

- [Claude Code](https://claude.ai/code) installed and configured
- Python 3

### Install

```bash
git clone https://github.com/hellowind777/goal-hook.git
cd goal-hook
python setup.py
```

Restart Claude Code. Done.

### Manual Install

Clone the repo and add to `~/.claude/settings.json`:

```json
{
  "enabledPlugins": {
    "goal-hook@goal-hook-marketplace": true
  },
  "extraKnownMarketplaces": {
    "goal-hook-marketplace": {
      "source": {
        "path": "/path/to/goal-hook",
        "source": "directory"
      }
    }
  }
}
```

### Verify

The `setup.py` script validates that all plugin files are in place:

```
[1/3] Installing to ~/.claude/plugins/local-marketplaces/goal-hook-marketplace/plugins/goal-hook ...
[2/3] Registering in settings.json ...
[3/3] Verifying ...
  [OK] hooks/hooks.json
  [OK] scripts/_goal_check.py
  [OK] .claude-plugin/plugin.json

Installed: .../goal-hook-marketplace
Restart Claude Code to activate.
```

## Usage

The hook itself requires no user action. Your GOAL_PROMPT writes the status file.

**At startup:**

```python
import json
json.dump({"status": "in_progress", "reason": "Task in progress"},
          open("scripts/data/.goal_status.json", "w", encoding="utf-8"))
```

**On completion:**

```python
import json
json.dump({"status": "terminated", "reason": "All checks passed"},
          open("scripts/data/.goal_status.json", "w", encoding="utf-8"))
```

When the hook blocks, the agent sees instructions on how to self-terminate:

```
[goal-hook] GOAL_PROMPT 循环执行中。
当你确认目标已达成，执行:
python -c "import json; json.dump({'status':'terminated','reason':'目标达成'},
open('scripts/data/.goal_status.json','w',encoding='utf-8'))"
```

## Recommended Settings

```json
"CLAUDE_CODE_STOP_HOOK_BLOCK_CAP": "1000"
```

Claude Code v2.1.143+ enforces a maximum of 8 consecutive Stop hook blocks. Raise this to prevent legitimate long-running goal tasks from being killed.

## Files

| File | Purpose |
|------|---------|
| `plugins/goal-hook/hooks/hooks.json` | Stop hook registration |
| `plugins/goal-hook/scripts/_goal_check.py` | Status file checker (99 lines) |
| `plugins/goal-hook/.claude-plugin/plugin.json` | Plugin metadata |
| `.claude-plugin/marketplace.json` | Marketplace manifest |
| `setup.py` | One-click cross-platform installer |

## Version History

### v1.0.8 (2026-06-20)

- Comprehensive README rewrite (bilingual, hero banner, LINUX DO recognition)
- LICENSE updated to dual-license (Apache 2.0 + CC BY 4.0)

### v1.0.7 (2026-06-20)

- Standard CC marketplace directory structure (`plugins/goal-hook/`)
- Removed legacy `setup.bat` and `setup.ps1`

### v1.0.6

- Fixed Stop hook output to valid JSON schema (`{}` for pass, `{"decision":"block",...}` for block)
- Plugin installs to CC plugins directory instead of pointing at repo
- Windows junction handling in setup.py

[Full release notes](./RELEASE_NOTES.md)

## FAQ

<details>
<summary><strong>Q: Does this interfere with non-/goal sessions?</strong></summary>

**A:** No. If `.goal_status.json` doesn't exist, the hook passes immediately. Zero overhead, zero interference.
</details>

<details>
<summary><strong>Q: What if my /goal session crashes mid-task?</strong></summary>

**A:** The stale `in_progress` file auto-expires after 168 hours (7 days). Active tasks re-write the file every round, so they never hit this limit.
</details>

<details>
<summary><strong>Q: Can I use this with any GOAL_PROMPT?</strong></summary>

**A:** Yes. The hook is completely GOAL_PROMPT agnostic. It only reads the status file. Any prompt that writes `in_progress` / `terminated` to the expected path works.
</details>

<details>
<summary><strong>Q: What happens when both the built-in hook and goal-hook run?</strong></summary>

**A:** Claude Code runs all registered Stop hooks. The Command-type hook (goal-hook) executes independently. If the built-in prompt hook fails with a JSON error, the command hook still checks the file and blocks if needed.
</details>

## License

This project is licensed under the [Apache-2.0 License](./LICENSE).

---

<div align="center">

![GitHub stars](https://img.shields.io/github/stars/hellowind777/goal-hook?style=social)
![GitHub forks](https://img.shields.io/github/forks/hellowind777/goal-hook?style=social)

</div>
