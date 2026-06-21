<div align="center">
  <img src="./readme_images/01-hero-banner.svg" alt="hello-goal" width="800">
</div>

# hello-goal v2.0

Hybrid Guardian for Claude Code `/goal` tasks. Automatically prevents premature termination via behavioral structure analysis + LLM semantic fallback. Language-agnostic. Zero prompt modification required.

[![Version](https://img.shields.io/badge/version-2.0.3-orange.svg)](./RELEASE_NOTES.md)
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

**hello-goal v2.0** uses a single command-type Stop hook with four-layer cascaded analysis to detect and block these premature terminations, keeping the `/goal` loop running until the task is genuinely complete.

### v2.0 vs v1.x

| | v1.x | v2.0 |
|---|---|---|
| Detection | Prompt writes `.goal_status.json` | Auto-detected from transcript |
| Prompt intrusion | Status file write code required | **Zero** — prompt focuses only on task goal |
| Abandonment detection | None | Structural analysis + LLM semantic fallback |
| Language support | Marker matching only | All languages (structural analysis is language-agnostic) |
| Hooks | 1 Stop hook | 3 hooks (Stop + SessionStart + PostCompact) |
| API error recovery | None | Automatic pattern matching on third-party API errors |

## The Problem It Solves

| Scenario | Without hello-goal | With hello-goal v2.0 |
|----------|-------------------|---------------------|
| `/goal` hook error mid-task | Session terminates | Detects abnormal stop_reason → BLOCK |
| Third-party API error (429/503/etc.) | `/goal` loop dies | Pattern match → auto-recover BLOCK |
| Model fatigue / wants to quit | Native evaluator passes | Structural signals + LLM confirm → BLOCK |
| Model downgrades completion standard | Low-quality "done" | Structural analysis detects stall → BLOCK |
| Post-compaction disorientation | Model forgets goal | PostCompact refreshes detection state |
| Normal non-`/goal` session | — | Zero interference, immediate pass |

## How It Works

```
Stop Hook fires
  │
  ├─ Phase 0: /goal Detection (dual-signal cross-validation)
  │   ├─ Signal A: /goal command found in transcript
  │   ├─ Signal B: Native /goal evaluator traces in transcript
  │   └─ Not /goal → PASS (zero interference)
  │
  ├─ Phase 1: Interruption Recovery
  │   └─ stop_reason != "end_turn" → BLOCK
  │
  ├─ Phase 1.5: API Error Auto-Recovery
  │   ├─ Match patterns: socket close, 429/503/502/504, rate limit, timeout...
  │   ├─ Sources: stop_reason, assistant message, transcript tail
  │   └─ API error detected → BLOCK (auto-resume /goal)
  │
  ├─ Phase 2: Structural Scoring (<1ms, language-agnostic)
  │   ├─ Signal 1: No tool calls in last turn        +30%
  │   ├─ Signal 2: Trend collapse (msg+tool decline)  +25%
  │   ├─ Signal 3: Stuck loop (3 turns same tools)    +20%
  │   ├─ Signal 4: Read-only stall (5 turns no writes) +15%
  │   ├─ ≥50% → BLOCK    <20% → PASS
  │   └─ Otherwise → Phase 3
  │
  ├─ Phase 3: LLM Semantic Fallback (ambiguous zone only, ~10% of turns)
  │   ├─ Haiku analyzes last_assistant_message
  │   ├─ Abandonment/downgrade intent? → BLOCK
  │   └─ API unavailable → conservative BLOCK
  │
  └─ Phase 4: Loop Protection
      └─ stop_hook_active → threshold raised to 70%
```

### Why not keywords/regex

There are 200+ languages. A model can express "I give up" in any of them. Keyword regex is neither exhaustive nor maintainable.

v2.0's structural analysis **doesn't read text content** — it analyzes tool call patterns, message length trends, and turn structure from the transcript. These signals are identical in every language. The LLM semantic fallback only runs in the ~10% ambiguous zone and handles any language natively.

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

The plugin monitors automatically, blocking premature termination and keeping `/goal` running until genuine completion.

## Recommended Settings

```json
"CLAUDE_CODE_STOP_HOOK_BLOCK_CAP": "1000"
```

Claude Code v2.1.143+ enforces a maximum of 8 consecutive Stop hook blocks. Raise this to prevent legitimate long-running goal tasks from being killed.

## Architecture

```
hooks/hooks.json
├── Stop (command, 12s)          ← Core guardian: four-layer cascaded analysis
├── SessionStart (command, 5s)   ← Stale state cleanup, session init
└── PostCompact (command, 3s)    ← Post-compaction detection cache refresh

scripts/_goal_guard.py (~400 lines, zero dependencies)
├── handle_stop()           ← Phase 0-4 main logic
├── handle_session_start()  ← State cleanup
├── handle_post_compact()   ← Cache refresh
├── _structural_score()     ← Behavioral signal weighting
├── _detect_api_error()     ← API error pattern matching and auto-recovery
├── _llm_check()            ← LLM semantic fallback (urllib, inherits ANTHROPIC_API_KEY)
└── _detect_goal_active()   ← Dual-signal /goal detection
```

## Files

| File | Purpose |
|------|---------|
| `plugins/hello-goal/hooks/hooks.json` | Three-hook registration (Stop + SessionStart + PostCompact) |
| `plugins/hello-goal/scripts/_goal_guard.py` | Hybrid guardian main script |
| `plugins/hello-goal/.claude-plugin/plugin.json` | Plugin metadata (v2.0.3) |
| `.claude-plugin/marketplace.json` | Marketplace manifest |
| `setup.py` | One-click cross-platform installer |

## FAQ

<details>
<summary><strong>Q: Does this interfere with non-/goal sessions?</strong></summary>

**A:** No. The hook first detects whether `/goal` is active. Non-`/goal` sessions pass immediately — zero overhead, zero interference.
</details>

<details>
<summary><strong>Q: Do I need to modify my GOAL_PROMPT?</strong></summary>

**A:** No. v2.0 auto-detects `/goal` state from the transcript. It does not depend on any status file written by your prompt.
</details>

<details>
<summary><strong>Q: How much does the LLM fallback cost?</strong></summary>

**A:** Only ~10% of turns trigger the LLM call (ambiguous structural signal zone). Each call is ~$0.0005. A 200-turn `/goal` task costs about $0.01 total.
</details>

<details>
<summary><strong>Q: Does this conflict with the native /goal evaluator?</strong></summary>

**A:** No. Both run in parallel — any single BLOCK prevents the stop. This plugin uses a command hook with independent judgment, not dependent on the native prompt hook.
</details>

<details>
<summary><strong>Q: Will it block a genuinely completed task?</strong></summary>

**A:** No. All four analysis layers have PASS conditions. When the task is truly done, structural signals remain below threshold and the LLM confirms genuine completion — the hook passes.
</details>

## License

This project is licensed under the [Apache-2.0 License](./LICENSE).

---

<div align="center">

![GitHub stars](https://img.shields.io/github/stars/hellowind777/hello-goal?style=social)
![GitHub forks](https://img.shields.io/github/forks/hellowind777/hello-goal?style=social)

</div>
