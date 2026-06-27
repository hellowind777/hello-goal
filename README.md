<div align="center">
  <img src="./readme_images/01-hero-banner.svg" alt="hello-goal" width="800">
</div>

# hello-goal v2.3.1

Global API Recovery + Hybrid Guardian for Claude Code `/goal` tasks. API errors (socket disconnect, 429, 502, 503) auto-recover regardless of `/goal` mode. In `/goal` mode, additionally prevents premature termination via behavioral structure analysis + LLM semantic analysis. Language-agnostic. Zero external dependencies. Pure Python standard library.

[![Version](https://img.shields.io/badge/version-2.3.1-orange.svg)](./RELEASE_NOTES.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE)
[![LINUX DO](https://img.shields.io/badge/LINUX_DO-recognized-0A84FF?logo=linux&logoColor=white)](https://linux.do)

[English](./README.md) · [简体中文](./README_CN.md)

> This project is recognized by the [LINUX DO](https://linux.do) community.

## Table of Contents

<details>
<summary><strong>Click to expand</strong></summary>

- [Overview](#overview)
- [The Problem It Solves](#the-problem-it-solves)
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Recommended Settings](#recommended-settings)
- [Architecture](#architecture)
- [Files](#files)
- [FAQ](#faq)
- [License](#license)

</details>

## Overview

Claude Code's `/goal` has three typical failure modes in long-running tasks:

1. **Interruption** — hook errors or API exceptions kill the `/goal` loop
2. **Abandonment** — the model wants to quit early due to fatigue, long context, or loss of confidence
3. **Standard downgrade** — the model silently lowers completion criteria ("good enough", "mostly done")

Additionally, **API errors** (socket disconnections from third-party LLM providers, 429/502/503) can kill ANY task — `/goal` or not. hello-goal v2.3.1 catches these globally, before any other check, and auto-recovers.

**hello-goal v2.3.1** uses a single command-type Stop hook with 4-phase cascaded analysis to detect and block premature terminations. All BLOCK reasons are minimal (`"继续"`) to avoid distracting the AI assistant during recovery.

### v2.3 vs v2.2

| | v2.2 | v2.3 |
|---|---|---|
| JSON I/O | `sys.stdout.buffer.write()` + `sys.stdout.flush()` | `os.write(fd=1)` — direct fd write, bypasses Windows encoding layer entirely |
| stderr | Uncontrolled — Python warnings could pollute hook output | Redirected to `os.devnull` at startup |
| Process exit | `sys.exit(0)` — may trigger atexit callbacks | `os._exit(0)` — immediate, zero post-output |
| API defaults | Hardcoded `api.anthropic.com` + `claude-3-5-haiku` | No hardcoded defaults — reads from CC env vars only |
| API key env | `ANTHROPIC_API_KEY` only | Also reads `ANTHROPIC_AUTH_TOKEN` |
| stdin errors | Catches `JSONDecodeError` + `IOError` | Catches all `Exception` (incl. `UnicodeDecodeError`) |
| BLOCK reason | Verbose diagnostic strings (~80 chars) | `"继续"` — 2 characters, minimal |
| JSON fallback | 1 layer | 3 layers: `os.write(1)` → `sys.stdout.buffer` → `print(ascii)` |

### v2.2 vs v2.1

| | v2.1 | v2.2 |
|---|---|---|
| API error recovery | `/goal` only (Phase 1.5) | Global (Phase 0), before /goal check |
| Non-/goal API errors | PASS (task interrupted) | BLOCK (auto-recover) |
| Phase order | /goal → interrupt → API → behavioral+LLM | API → /goal → interrupt → behavioral+LLM |

### v2.1 vs v2.0

| | v2.0 | v2.1 |
|---|---|---|
| Decision model | Structural score hard threshold (≥50%→BLOCK) | All suspicious scores → LLM semantic analysis |
| False positive risk | Behavioral signals can misclassify wind-down as stall | LLM distinguishes genuine completion from abandonment |
| LLM calls | ~10% of turns (fuzzy zone only) | All suspicious turns (ensures correctness) |
| Complexity | 4 phases (Phase 2/3/4 with threshold adjustment) | 3 phases (unified Phase 2: signals + LLM) |

## The Problem It Solves

| Scenario | Without hello-goal | With hello-goal v2.3.1 |
|----------|-------------------|---------------------|
| API error (socket/429/503) in any session | Task permanently interrupted | Phase 0 detects → auto-recover BLOCK |
| `/goal` hook error mid-task | Session terminates | Detects abnormal stop_reason → BLOCK |
| Model fatigue / wants to quit | Native evaluator passes | Structural signals + LLM confirm → BLOCK |
| Model downgrades completion standard | Low-quality "done" | Structural analysis detects stall → BLOCK |
| Post-compaction disorientation | Model forgets goal | PostCompact refreshes detection state |
| Normal session (no API error) | — | Zero interference, immediate pass |

## How It Works

```
Stop Hook fires
  │
  ├─ Phase 0 (Global): API Error Detection
  │   ├─ Match 11 patterns: socket close, 429/503/502/504, rate limit, timeout...
  │   ├─ Sources: stop_reason, assistant message, transcript tail
  │   └─ API error detected → BLOCK (auto-resume, regardless of /goal mode)
  │
  ├─ Phase 1: /goal Detection (CC native markers + user commands + cache-first)
  │   ├─ Signal A: CC native "Goal set:" / "Goal cleared:" markers
  │   ├─ Signal B: User /goal command parsing (backup)
  │   ├─ Signal C: stop_hook_summary entries (confirming only)
  │   └─ Not /goal → PASS (zero interference)
  │
  ├─ Phase 2: Interruption Recovery
  │   └─ stop_reason != "end_turn" → BLOCK
  │
  └─ Phase 3: Behavioral Signals + LLM Semantic Analysis (unified hybrid)
      ├─ Signal 1: No tool calls in last turn        +30%
      ├─ Signal 2: Trend collapse (msg+tool decline)  +25%
      ├─ Signal 3: Stuck loop (3 turns same tools)    +20%
      ├─ Signal 4: Read-only stall (5 turns no writes) +15%
      ├─ score < 0.20 → PASS (no behavioral concern)
      └─ score ≥ 0.20 → LLM semantic analysis (with behavioral context)
          ├─ Lightweight model analyzes last_assistant_message + behavioral signals
          ├─ Distinguishes genuine completion from premature abandonment
          ├─ BLOCK → continue    PASS → allow stop
          └─ API unavailable → conservative BLOCK
  └─ Global Exception Guard: unhandled internal error → BLOCK
```

All BLOCK decisions return reason `"继续"` — minimal, non-distracting feedback to the AI assistant.

### Why not keywords/regex

There are 200+ languages. A model can express "I give up" in any of them. Keyword regex is neither exhaustive nor maintainable.

v2.3.1's behavioral analysis **doesn't read text content** — it scores tool call patterns, message length trends, and turn structure from the transcript. These signals are identical in every language. The LLM semantic analysis provides the final decision on all suspicious turns, handling any language natively.

## Quick Start

### Prerequisites

- [Claude Code](https://claude.ai/code) installed and configured
- Python 3

### Install

```bash
git clone https://github.com/hellowind777/hello-goal.git
cd hello-goal
python setup.py
```

Restart Claude Code. Done.

### Manual Install

Clone the repo and add to `~/.claude/settings.json`:

```json
{
  "enabledPlugins": {
    "hello-goal@hello-goal-marketplace": true
  },
  "extraKnownMarketplaces": {
    "hello-goal-marketplace": {
      "source": {
        "path": "/path/to/hello-goal",
        "source": "directory"
      }
    }
  }
}
```

### Verify

The `setup.py` script validates that all plugin files are in place:

```
[1/3] Installing to ~/.claude/plugins/local-marketplaces/hello-goal-marketplace/plugins/hello-goal ...
[2/3] Registering in settings.json ...
[3/3] Verifying ...
  [OK] hooks/hooks.json
  [OK] scripts/_goal_guard.py
  [OK] .claude-plugin/plugin.json

Installed: .../hello-goal-marketplace
Restart Claude Code to activate.
```

## Usage

**Your GOAL_PROMPT needs no plugin-specific code.** Just describe the task objective and acceptance criteria.

```
/goal follow the prompt
```

The plugin monitors automatically, blocking premature termination and keeping `/goal` running until genuine completion. API errors are also auto-recovered in any session.

## Recommended Settings

```json
"CLAUDE_CODE_STOP_HOOK_BLOCK_CAP": "1000"
```

Claude Code v2.1.143+ enforces a maximum of 8 consecutive Stop hook blocks. Raise this to prevent legitimate long-running goal tasks from being killed.

## Architecture

```
hooks/hooks.json
├── Stop (command, 60s)          ← Core guardian: 4-phase cascaded analysis
├── SessionStart (command, 5s)   ← Stale state cleanup, session init
└── PostCompact (command, 3s)    ← Post-compaction detection cache refresh

scripts/_goal_guard.py (~750 lines, zero dependencies)
├── handle_stop()           ← Phase 0-3 main logic
├── handle_session_start()  ← State cleanup
├── handle_post_compact()   ← Cache refresh with sticky goal_detected
├── _detect_goal_active()   ← Three-tier /goal detection (markers + commands + summary)
├── _structural_score()     ← Behavioral signal weighting (4 signals)
├── _detect_api_error()     ← API error pattern matching (11 patterns, 3 sources)
└── _llm_check()            ← LLM semantic analysis with behavioral context (urllib)
```

## Files

| File | Purpose |
|------|---------|
| `plugins/hello-goal/hooks/hooks.json` | Three-hook registration (Stop + SessionStart + PostCompact) |
| `plugins/hello-goal/scripts/_goal_guard.py` | Hybrid guardian main script |
| `plugins/hello-goal/.claude-plugin/plugin.json` | Plugin metadata (v2.3.1) |
| `.claude-plugin/marketplace.json` | Marketplace manifest |
| `setup.py` | One-click cross-platform installer |

## FAQ

<details>
<summary><strong>Q: Does this interfere with non-/goal sessions?</strong></summary>

**A:** For API errors — no. The plugin catches them globally and auto-recovers, which is exactly what you want (a socket disconnect should not kill your task). For normal non-API-error stops in non-/goal sessions, it passes immediately with zero intervention.
</details>

<details>
<summary><strong>Q: Do I need to modify my GOAL_PROMPT?</strong></summary>

**A:** No. v2.3.1 auto-detects `/goal` state from CC native markers in the transcript. It does not depend on any status file written by your prompt.
</details>

<details>
<summary><strong>Q: How much does the LLM analysis cost?</strong></summary>

**A:** All turns with any behavioral signal (score ≥ 0.20) trigger LLM analysis. Each lightweight model call is ~$0.0005. A 200-turn `/goal` task with behavioral signals on every turn costs about $0.10 total. Turns without signals (score < 0.20) pass instantly with zero LLM cost.
</details>

<details>
<summary><strong>Q: Does this conflict with the native /goal evaluator?</strong></summary>

**A:** No. Both run in parallel — any single BLOCK prevents the stop. This plugin uses a command hook with independent judgment, not dependent on the native prompt hook.
</details>

<details>
<summary><strong>Q: Will it block a genuinely completed task?</strong></summary>

**A:** No. When the task is truly done, the LLM semantic analysis recognizes genuine completion (final report, test results, comprehensive summary) and returns PASS — even if behavioral signals (no tools, trend decline) are elevated. The LLM is explicitly instructed to distinguish task wind-down from premature abandonment.
</details>

<details>
<summary><strong>Q: What if the plugin itself hits an unexpected error?</strong></summary>

**A:** The main handler is wrapped in a global exception guard with 3-layer fallback (`os.write(1)` → `sys.stdout.buffer` → `print(ascii)`). Any unexpected internal error outputs a valid BLOCK decision — keeping the task running safely rather than crashing with a "JSON validation failed" error.
</details>

## License

This project is licensed under the [Apache-2.0 License](./LICENSE).

---

<div align="center">

![GitHub stars](https://img.shields.io/github/stars/hellowind777/hello-goal?style=social)
![GitHub forks](https://img.shields.io/github/forks/hellowind777/hello-goal?style=social)

</div>
