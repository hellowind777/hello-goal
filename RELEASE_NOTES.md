# Release Notes / 发布记录

## v2.3.1 (2026-06-27)

### JSON 输出加固 + reason 精简 + DeepSeek 兼容 —— Windows I/O 层重构与多 API 提供商适配

对比 v2.2.0 的实质性变更：

**JSON 输出 I/O 层重构（Windows 可靠性修复）：**

- `_write_json()` 输出路径从 `sys.stdout.buffer.write()` + `sys.stdout.flush()` 改为 `os.write(fd=1, raw_bytes)`。直接写文件描述符 1，彻底绕过 Python 的 `sys.stdout` / `sys.stdout.buffer` 多层封装，消除 Windows 上 `TextIOWrapper` 编码层与底层 `BufferedWriter` 之间潜在的缓冲不同步问题。此为 v2.2.0 的 "Stop hook error: JSON validation failed" 报告的根本性修复。
- 启动时立即将 `sys.stderr` 重定向到 `os.devnull`，防止 `urllib.request` 等标准库的 DeprecationWarning 污染 hook 系统的 JSON 输出流。
- 进程退出方式从 `sys.exit(0)` 改为 `os._exit(0)`，避免 atexit 回调、finally 块和 `__del__` 清理逻辑产生额外 stdout 输出。

**多 API 提供商兼容（移除硬编码默认值）：**

- `ANTHROPIC_BASE_URL` 默认值从 `"https://api.anthropic.com"` 改为 `""`（空字符串，不设默认值）。API URL 缺失时 `_llm_check()` 返回 `None`，走保守 BLOCK 而非尝试连接错误端点。
- `LLM_MODEL` 默认值从硬编码 `"claude-3-5-haiku-20241022"` 改为从环境变量 `ANTHROPIC_DEFAULT_HAIKU_MODEL` 读取，缺失时为空。不同 API 提供商（DeepSeek、Anthropic 等）模型名不同，不再假设固定模型。
- API 密钥读取兼容 `ANTHROPIC_AUTH_TOKEN` 环境变量（原仅读 `ANTHROPIC_API_KEY`）。
- `_llm_check()` 新增三个前导防护：`ANTHROPIC_BASE_URL`、`LLM_MODEL` 任一缺失均立即返回 `None`，避免在配置不完整时发起 API 调用。

**stdin 异常捕获扩展：**

- `_read_stdin()` 异常捕获从 `(json.JSONDecodeError, IOError)` 扩展为全 `Exception`，覆盖 Windows 上因 cp936/GBK 编码导致的 `UnicodeDecodeError`。任何 stdin 读取失败均以空上下文兜底，不让 hook 因输入问题崩溃。

**BLOCK reason 精简：**

- 所有 `_block()` 调用的 reason 参数统一为 `"继续"`（两字）。原设计的详细诊断信息（"检测到 API 错误 (assistant 消息匹配 \b429\b)。任务自动恢复，继续执行。" 等）会作为 hook feedback 注入 AI 上下文，产生认知干扰。精简为两字后，AI 不被冗余错误细节分散注意力。

**三层 JSON 输出兜底：**

- JSON 输出异常降级链：`os.write(fd=1)` → `sys.stdout.buffer.write()` + `sys.stdout.flush()` → `print(json.dumps(data, ensure_ascii=True))`。每层都覆盖更极端的失败场景（fd 1 关闭、buffer 不可用），确保任意环境下始终能产出一行合法 JSON。

**额外加固：**

- 主入口 `main()` 最底层兜底直接 `os.write(1, b'{...}')`，跳过所有函数调用链。
- 移除已废弃的 `_setup_encoding()` 函数（`sys.stdout.reconfigure()` 在 Windows 上与新的 `os.write(fd=1)` 路径存在冲突风险）。

**版本号同步：**

- `_goal_guard.py` 模块文档版本号 2.2.0 → 2.3.1
- `plugin.json` 版本号 2.2.0 → 2.3.1
- `marketplace.json` 版本号 2.2.0 → 2.3.1
- `README.md` / `README_CN.md` 版本号 2.2.0 → 2.3.1
- `01-hero-banner.svg` / `architecture.svg` 版本号 2.2.0 → 2.3.1

---

### JSON Output Hardening + Reason Simplification + DeepSeek Compatibility — Windows I/O Layer Refactor and Multi-Provider Adaptation

Substantive changes compared to v2.2.0:

**JSON Output I/O Layer Refactor (Windows reliability fix):**

- `_write_json()` output path changed from `sys.stdout.buffer.write()` + `sys.stdout.flush()` to `os.write(fd=1, raw_bytes)`. Writing directly to file descriptor 1 completely bypasses Python's `sys.stdout` / `sys.stdout.buffer` multi-layer abstraction, eliminating potential buffer desynchronization between the `TextIOWrapper` encoding layer and the underlying `BufferedWriter` on Windows. This is the root-cause fix for the "Stop hook error: JSON validation failed" reports in v2.2.0.
- At startup, `sys.stderr` is immediately redirected to `os.devnull`, preventing DeprecationWarnings from standard library modules (e.g. `urllib.request`) from polluting the hook system's JSON output stream.
- Process exit changed from `sys.exit(0)` to `os._exit(0)`, avoiding any extra stdout output from atexit callbacks, finally blocks, or `__del__` cleanup logic.

**Multi-Provider API Compatibility (removed hardcoded defaults):**

- `ANTHROPIC_BASE_URL` default changed from `"https://api.anthropic.com"` to `""` (empty, no default). When the API URL is absent, `_llm_check()` returns `None` and falls through to conservative BLOCK rather than attempting a connection to the wrong endpoint.
- `LLM_MODEL` default changed from hardcoded `"claude-3-5-haiku-20241022"` to reading from the `ANTHROPIC_DEFAULT_HAIKU_MODEL` environment variable. If absent, the value is empty. Different API providers (DeepSeek, Anthropic, etc.) use different model names; no single model name is assumed.
- API key reading now also checks `ANTHROPIC_AUTH_TOKEN` (previously only `ANTHROPIC_API_KEY`).
- `_llm_check()` gains three pre-guards: if `ANTHROPIC_BASE_URL` or `LLM_MODEL` is missing, immediately returns `None` to avoid making API calls with incomplete configuration.

**stdin Exception Handling Expanded:**

- `_read_stdin()` exception catching expanded from `(json.JSONDecodeError, IOError)` to full `Exception`, covering `UnicodeDecodeError` caused by cp936/GBK encoding mismatches on Windows. Any stdin read failure falls through to an empty context, preventing hook crashes from input issues.

**BLOCK Reason Simplified:**

- All `_block()` call reason parameters unified to `"继续"` (2 characters, "continue"). The previous verbose diagnostic strings (e.g., "Detected API error (assistant message match \b429\b). Auto-recovering task.") were injected as hook feedback into the AI context, causing cognitive distraction. The two-character minimal form eliminates this noise.

**Three-Layer JSON Output Fallback:**

- JSON output exception degradation chain: `os.write(fd=1)` → `sys.stdout.buffer.write()` + `sys.stdout.flush()` → `print(json.dumps(data, ensure_ascii=True))`. Each layer handles progressively more extreme failure scenarios (fd 1 closed, buffer unavailable), ensuring a valid JSON line is always produced in any environment.

**Additional Hardening:**

- The `main()` entry point's deepest fallback directly calls `os.write(1, b'{...}')`, bypassing all function call chains.
- Removed the obsolete `_setup_encoding()` function (`sys.stdout.reconfigure()` conflicted with the new `os.write(fd=1)` path on Windows).

**Version Sync:**

- `_goal_guard.py` module docstring version 2.2.0 → 2.3.1
- `plugin.json` version 2.2.0 → 2.3.1
- `marketplace.json` version 2.2.0 → 2.3.1
- `README.md` / `README_CN.md` version 2.2.0 → 2.3.1
- `01-hero-banner.svg` / `architecture.svg` version 2.2.0 → 2.3.1

---

## v2.2.0 (2026-06-23)

### API 错误全局自动恢复 —— 无论是否 /goal 模式均响应

对比 v2.1.2 的实质性变更：

**API 错误检测提升为全局 Phase 0：**

- `handle_stop()` 执行顺序重排：原 Phase 1.5（API 错误模式匹配）移至 Phase 0，**优先于 /goal 检测**。此前 API 错误恢复仅在 /goal 会话中生效，非 /goal 会话遇到 socket 断开、429、502、503 等第三方大模型瞬时故障时直接 PASS 导致任务永久中断。
- 新逻辑：Phase 0 检测到 API 错误 → BLOCK → 任务自动恢复继续执行，无论当前是否处于 /goal 模式。Phase 1 才是 /goal 检测（非 /goal → PASS），Phase 2/3 为原有的 /goal 专属守护。
- `/goal` 模式下的 API 错误恢复行为不变，仍能自动 BLOCK 恢复。

**Stop Hook 新 Phase 顺序：**

| Phase | 范围 | 检测内容 | 动作 |
|-------|------|---------|------|
| Phase 0 | 全局 | API 错误模式匹配（socket/429/502/503 等 11 种） | BLOCK |
| Phase 1 | /goal | /goal 活跃检测 | 非 /goal → PASS |
| Phase 2 | /goal | stop_reason 异常 | BLOCK |
| Phase 3 | /goal | 行为信号 + LLM 语义分析 | 混合判定 |

**版本号同步：**

- `_goal_guard.py` 模块文档版本号 2.1.2 → 2.2.0
- `plugin.json` 版本号 2.1.2 → 2.2.0
- `marketplace.json` 版本号 2.1.2 → 2.2.0

---

### Global API Error Recovery — Responds Regardless of /goal Mode

Substantive changes compared to v2.1.2:

**API error detection promoted to global Phase 0:**

- `handle_stop()` execution order reorganized: former Phase 1.5 (API error pattern matching) moved to Phase 0, **before /goal detection**. Previously, API error recovery only worked during /goal sessions; non-/goal sessions encountering socket disconnections, 429, 502, 503, and other third-party LLM transient errors would PASS, causing permanent task interruption.
- New logic: Phase 0 detects API error → BLOCK → task auto-resumes execution, regardless of whether /goal mode is active. Phase 1 handles /goal detection (non-/goal → PASS), Phases 2/3 provide the original /goal-specific guarding.
- API error recovery behavior in /goal mode is unchanged, still auto-BLOCKs and resumes.

**New Stop Hook Phase ordering:**

| Phase | Scope | Detection | Action |
|-------|-------|-----------|--------|
| Phase 0 | Global | API error pattern matching (11 patterns: socket/429/502/503 etc.) | BLOCK |
| Phase 1 | /goal | /goal active detection | non-/goal → PASS |
| Phase 2 | /goal | abnormal stop_reason | BLOCK |
| Phase 3 | /goal | behavioral signals + LLM semantic analysis | hybrid decision |

**Version sync:**

- `_goal_guard.py` module docstring version 2.1.2 → 2.2.0
- `plugin.json` version 2.1.2 → 2.2.0
- `marketplace.json` version 2.1.2 → 2.2.0

---

## v2.1.2 (2026-06-22)

### Stop Hook 全局异常兜底 —— 杜绝 JSON 验证失败导致 /goal 循环中断

对比 v2.1.1 的实质性变更：

**Stop Hook 全局异常兜底：**

- `_goal_guard.py` 的 `main()` 新增 `try/except Exception` 全局异常捕获。任何未预期的内部异常（文件并发竞争、磁盘 I/O 错误、状态文件损坏等边缘场景）不再输出 Python traceback 到 stdout，而是输出合法的 `{"decision": "block", "reason": "..."}` JSON，确保 CC hook runner 始终能正确解析。
- 根本解决"Stop hook error: JSON validation failed"导致 `/goal` 循环意外中断的问题——即使脚本内部发生极端错误，保守策略也会 BLOCK 让 /goal 继续执行而非误 PASS 终止。

**版本号与架构图同步：**

- `01-hero-banner.svg`、`architecture.svg` 版本号从 v2.0.3 更新为 v2.1.2，与代码版本一致。
- `architecture.svg` 删除已废弃的 `≥50% → BLOCK` 硬阈值和 Phase 4 熔断器描述，更新为 v2.1 统一混合判定模型（score ≥ 0.20 → LLM 语义分析）。

**清理：**

- 删除过期的 `COMMIT_MESSAGE.md` 和源码 `__pycache__/` 缓存。
- 修复 git 分支上游追踪丢失的问题。

---

### Stop Hook Global Exception Guard —— Eliminate JSON Validation Failures Breaking /goal Loops

Substantive changes compared to v2.1.1:

**Stop Hook Global Exception Guard:**

- `_goal_guard.py` `main()` now wraps all handler execution in `try/except Exception`. Any unexpected internal exception (file race conditions, disk I/O errors, state file corruption, and other edge cases) no longer outputs a Python traceback to stdout — instead it outputs valid `{"decision": "block", "reason": "..."}` JSON that the CC hook runner can always parse correctly.
- Fundamentally fixes the "Stop hook error: JSON validation failed" issue that would unexpectedly break the `/goal` loop. Even in extreme internal error scenarios, the conservative strategy BLOCKs to keep /goal running rather than incorrectly PASSing and terminating.

**Version & Architecture Diagram Sync:**

- `01-hero-banner.svg` and `architecture.svg` version labels updated from v2.0.3 to v2.1.2, matching the code version.
- `architecture.svg` removes deprecated `≥50% → BLOCK` hard threshold and Phase 4 circuit breaker descriptions, updated to the v2.1 unified hybrid decision model (score ≥ 0.20 → LLM semantic analysis).

**Cleanup:**

- Removed stale `COMMIT_MESSAGE.md` and source `__pycache__/` cache.
- Fixed broken git branch upstream tracking.

---

## v2.1.1 (2026-06-21)

### Goal 检测重写 + 统一混合判定 + 非 /goal 会话零误判

对比 v2.0.3 的实质性变更：

**Goal 检测全面重写 —— 零误判：**

- 检测机制从"用户 `/goal` 命令正则解析 + `stop_hook_summary` 独立触发"重写为以 **CC 原生 `Goal set:` / `Goal cleared:` 标记为主信号**的三级体系。`Goal set:` 是 CC 内部系统消息，普通对话中绝不可能出现，从根源消除了误判。
- 新增**缓存优先三阶段检测**：Phase 1 缓存快速路径（已确认非 /goal 会话零 transcript 读取直接返回）、Phase 2 时间序判定（按 `last_set` vs `last_clear` 索引处理反复进出 /goal）、Phase 3 全量扫描（仅首次检测 / PostCompact / 状态失效触发）。
- **5 条目复检**：Phase 1 每次 Stop 仅读 5 条检查是否重新进入 /goal，发现 `Goal set:` 立即清除缓存走完整检测，解决"同一会话 /goal clear 后重新 /goal new_task"被永久误判为非活跃的 bug。
- **PostCompact 粘性先验**：compact 后保留 `goal_detected`，配合 `stop_hook_summary` 存活检测确认 goal 仍活跃，不再丢失跟踪。
- `stop_hook_summary` 从独立 OR 触发条件降级为**仅确认信号**，必须配合 `Goal set:` 标记或粘性先验知识才生效。
- 支持同一会话反复进出 /goal：人工 clear 停止干预，意外中断继续守护，原生评估器完成则尊重裁决。

**统一混合判定模型 —— 消除行为信号盲区：**

- 去掉 v2.0.3 的 `BLOCK_THRESHOLD` 硬阈值（score ≥ 50% → 直接 BLOCK 绕过 LLM）。**所有 score ≥ 0.20 的行为信号统一经 LLM 语义分析最终裁决**，消除三大盲区：
  - 降速写最终总结报告 → 不再被误判为趋势塌缩 (0.55)
  - 同类批量操作后退出 → 不再被误判为停滞循环 (0.50)
  - 大量只读分析后整理报告 → 不再被误判为只读停滞 (0.70)
- `_llm_check` 增加 **`flags` 参数**，将行为信号上下文传入 LLM prompt，让 Haiku 结合"末轮无工具调用""趋势下降"等结构化信息做语义判断。
- LLM prompt 新增**任务正常收尾判定引导**："if behavioral signals look like normal task wind-down (final report, comprehensive summary) and text indicates genuine completion, reply PASS"。

**LLM 语义分析加固：**

- 输出判定从 `"BLOCK" in text.upper()` 改为 **`startswith("BLOCK")` / `startswith("PASS")` 精确匹配**，消除对 UNBLOCK / BLOCKED / DO NOT BLOCK 的误匹配。
- 无法解析的响应返回 `None`，调用方保守 BLOCK。

**非 /goal 会话零干预保障：**

- 修复了 `stop_hook_summary` 作为独立 OR 条件时，插件自身 Stop hook 输出被 CC 记录后形成自触发无限循环的 bug。
- 修复了 `/goal\b` 正则中 `\b` 对 `/goal-oriented` 等文本误匹配的潜在误判（信号 A 作为主信号后此路径不再触发）。

**其他：**

- 移除 v2.0.3 中途引入的熔断器（连续 block ≥ 5 次强制 pass），避免破坏需要大量轮次的合法 /goal 长任务。
- `.gitignore` 修正 `__pycache__/` 匹配路径。
- 版本号 2.0.3 → 2.1.1。

---

### Goal Detection Rewrite + Unified Hybrid Decision + Zero False Trigger in Non-Goal Sessions

Substantive changes compared to v2.0.3:

**Goal detection fully rewritten — zero false positives:**

- Detection mechanism rewritten from "user `/goal` command regex parsing + `stop_hook_summary` standalone trigger" to a **three-tier system with CC native `Goal set:` / `Goal cleared:` markers as primary signal**. `Goal set:` is an internal CC system message that can never appear in normal conversation, eliminating false positives at the root.
- New **cache-first three-phase detection**: Phase 1 cache fast path (confirmed non-/goal sessions return immediately with zero transcript read), Phase 2 temporal ordering (tracks `last_set` vs `last_clear` index for repeated goal entry/exit), Phase 3 full scan (triggered only on first detection / PostCompact / state invalidation).
- **5-entry re-check**: Phase 1 reads only 5 transcript entries per Stop to check for re-entry into /goal. Finding `Goal set:` clears cache and falls through to full detection, fixing the bug where `/goal clear` followed by `/goal new_task` was permanently misclassified.
- **PostCompact sticky prior**: `goal_detected` preserved after compact, combined with `stop_hook_summary` liveness check to confirm goal still active without losing tracking.
- `stop_hook_summary` downgraded from standalone OR trigger to **confirming signal only**, requiring `Goal set:` marker or sticky prior knowledge to take effect.
- Supports repeated goal entry/exit within the same session: manual clear stops intervention, unexpected interruption continues guarding, native evaluator completion is respected.

**Unified hybrid decision model — eliminates behavioral signal blind spots:**

- Removed v2.0.3's `BLOCK_THRESHOLD` hard threshold (score ≥ 50% → direct BLOCK bypassing LLM). **All behavioral signals (score ≥ 0.20) now go through LLM semantic analysis for final decision**, eliminating three blind spots:
  - Writing final summary report → no longer misclassified as trend collapse (0.55)
  - Exiting after batch operations → no longer misclassified as stuck loop (0.50)
  - Compiling analysis after extensive reading → no longer misclassified as read-only stall (0.70)
- `_llm_check` adds **`flags` parameter**, passing behavioral signal context into LLM prompt so Haiku can combine structured information ("no tool calls in last turn", "trend declining") with semantic judgment.
- LLM prompt adds **task wind-down recognition guidance**: "if behavioral signals look like normal task wind-down (final report, comprehensive summary) and text indicates genuine completion, reply PASS".

**LLM semantic analysis hardening:**

- Output parsing changed from `"BLOCK" in text.upper()` to **`startswith("BLOCK")` / `startswith("PASS")` exact matching**, eliminating false matches on UNBLOCK / BLOCKED / DO NOT BLOCK.
- Unparseable responses return `None`, caller conservatively BLOCKs.

**Zero interference guarantee for non-/goal sessions:**

- Fixed the bug where `stop_hook_summary` as standalone OR condition caused the plugin's own Stop hook output to be recorded by CC, creating a self-triggering infinite loop.
- Fixed potential false match of `/goal\b` regex on text like `/goal-oriented` (signal A as primary renders this path untriggered).

**Other:**

- Removed circuit breaker (≥5 consecutive blocks → force pass) introduced mid-development, preventing disruption of legitimate long-running /goal tasks requiring many turns.
- `.gitignore` fixed `__pycache__/` matching path.
- Version 2.0.3 → 2.1.1.

---

对比 v2.0.1 的实质性变更：

**插件全面改名：**

- **goal-hook → hello-goal** —— 插件目录、配置文件、脚本、文档、市场清单全量重命名，仓库 URL 同步更新为 `https://github.com/hellowind777/hello-goal`。
- 所有内部标识符、错误消息前缀、状态文件名统一使用新名称。
- setup.py 安装路径适配新名称。

**API 错误自动恢复 (Phase 1.5)：**

- 新增第三方大模型 API 错误模式匹配层，在 Phase 1（中断恢复）和 Phase 2（行为结构评分）之间插入。
- 覆盖 10 种常见 API 异常模式：socket close、429/503/502/504、rate limit、overloaded、connection reset/timeout/refused、fetch failed、network error。
- 三源检测：stop_reason 字段 → assistant 消息文本 → transcript 尾部 system 错误字段。
- 检测到 API 错误后自动 BLOCK，/goal 无需人工干预即可恢复继续。

**守护层级更新：**

- 原"三层级联"扩展为"四层级联"：Phase 0 (/goal 检测) → Phase 1 (中断恢复) → Phase 1.5 (API 错误恢复) → Phase 2 (行为评分) → Phase 3 (LLM 语义) → Phase 4 (循环防护)。
- `_goal_guard.py` 新增 `_match_api_error()` 和 `_detect_api_error()` 函数，零额外依赖。

---

### Plugin Rename + API Error Auto-Recovery

Substantive changes compared to v2.0.1:

**Complete plugin rename:**

- **goal-hook → hello-goal** — Full rename of plugin directory, configs, scripts, docs, and marketplace manifest. Repository URL updated to `https://github.com/hellowind777/hello-goal`.
- All internal identifiers, error message prefixes, and state file names use the new name.
- setup.py installation paths adapted.

**API error auto-recovery (Phase 1.5):**

- New third-party LLM API error pattern matching layer, inserted between Phase 1 (interruption recovery) and Phase 2 (structural scoring).
- Covers 10 common API error patterns: socket close, 429/503/502/504, rate limit, overloaded, connection reset/timeout/refused, fetch failed, network error.
- Three-source detection: stop_reason field → assistant message text → transcript tail system error fields.
- Auto-BLOCK on API error detection, /goal resumes without manual intervention.

**Guard layer update:**

- "Three-layer cascade" expanded to "four-layer cascade": Phase 0 (/goal detection) → Phase 1 (interruption recovery) → Phase 1.5 (API error recovery) → Phase 2 (structural scoring) → Phase 3 (LLM semantic) → Phase 4 (loop protection).
- `_goal_guard.py` adds `_match_api_error()` and `_detect_api_error()` functions, zero additional dependencies.

---

## v2.0.1 (2026-06-21)

### 架构全面重构 —— Hybrid Guardian

将插件从"被动状态文件检查器"全面重构为"主动混合守护系统"，实现 `/goal` 任务的全程自动监控。对比 v1.0.9 的实质性变更：

**架构变更：**

- **零提示词侵入** —— 不再需要 GOAL_PROMPT 写入 `.goal_status.json`。插件从 transcript 自动检测 `/goal` 状态，通过双信号交叉验证（`/goal` 命令 + 原生评估器 `stop_hook_summary` 痕迹）。提示词只需描述任务目标，无需任何插件相关代码。
- **行为结构分析** —— 实现语言无关的四信号加权体系：末轮零工具调用 / 趋势塌缩 / 停滞循环 / 只读停滞。纯分析 transcript 的 JSON 结构（工具调用模式、消息长度趋势、轮次结构），不读文字内容，任意语言通用。
- **LLM 语义兜底** —— 仅当行为信号处于模糊区间（20%-50%）时调用 Haiku 做语义确认。90% 轮次仅需 <1ms 结构分析。API 不可用时回退到保守 BLOCK。
- **三钩子架构** —— 新增 SessionStart（清理过期状态）+ PostCompact（压缩后刷新检测缓存），与 Stop（核心守卫）形成完整生命周期覆盖。
- **中断恢复** —— `stop_reason != "end_turn"` 直接 BLOCK，覆盖 API 错误、hook 异常、max_tokens 等中断场景。
- **会话感知状态管理** —— 使用 `CLAUDE_PLUGIN_DATA` 持久化会话状态，支持 `/goal` 检测缓存、连续 BLOCK 阈值提升、过期状态自动清理。

**删除的机制：**
- 移除 `.goal_status.json` 状态文件依赖（整个旧架构的核心）
- 移除 `scripts/_goal_check.py`（替换为 `_goal_guard.py`）
- 移除 transcript 关键词标记匹配（`_GOAL_CYCLE_RE`）
- 移除 HOW_TO_TERMINATE 自终止指令

**实现细节：**
- 新增: `_goal_guard.py`（~300 行，零依赖，仅 Python stdlib）
- LLM 调用通过 `urllib` 直连 Anthropic API，继承 `ANTHROPIC_API_KEY` 环境变量
- 删除: `_goal_check.py`（195 行旧实现）
- 更新: `hooks.json` 注册三个事件（Stop + SessionStart + PostCompact）

---

### Complete Architecture Rewrite —— Hybrid Guardian

Comprehensive rewrite from "passive file state checker" to "active hybrid guardian system" for automatic `/goal` task monitoring. Substantive changes compared to v1.0.9:

**Architecture changes:**

- **Zero prompt intrusion** — No longer requires GOAL_PROMPT to write `.goal_status.json`. Plugin auto-detects `/goal` state from transcript via dual-signal cross-validation (`/goal` command + native evaluator `stop_hook_summary` traces). Prompts only need to describe task objectives — zero plugin-specific code required.
- **Behavioral structure analysis** — Language-agnostic four-signal weighted scoring: no tool calls in last turn / trend collapse / stuck loop / read-only stall. Analyzes transcript JSON structure only (tool call patterns, message length trends, turn structure), never reads text content. Works in any language.
- **LLM semantic fallback** — Haiku semantic confirmation called only in ambiguous signal zone (20%-50%). 90% of turns complete in <1ms with structural analysis alone. Conservative BLOCK on API failure.
- **Three-hook architecture** — Added SessionStart (stale state cleanup) + PostCompact (post-compaction detection cache refresh), forming complete lifecycle coverage with Stop (core guardian).
- **Interruption recovery** — `stop_reason != "end_turn"` triggers immediate BLOCK, covering API errors, hook exceptions, max_tokens, and other interruption scenarios.
- **Session-aware state management** — Uses `CLAUDE_PLUGIN_DATA` for persistent session state, supporting `/goal` detection caching, consecutive BLOCK threshold elevation, and automatic stale state cleanup.

**Removed mechanisms:**
- `.goal_status.json` state file dependency (core of old architecture)
- `scripts/_goal_check.py` (replaced by `_goal_guard.py`)
- Transcript keyword marker matching (`_GOAL_CYCLE_RE`)
- HOW_TO_TERMINATE self-termination instruction

**Implementation details:**
- Added: `_goal_guard.py` (~300 lines, zero dependencies, Python stdlib only)
- LLM calls via `urllib` direct to Anthropic API, inheriting `ANTHROPIC_API_KEY` env var
- Removed: `_goal_check.py` (195-line old implementation)
- Updated: `hooks.json` registers three events (Stop + SessionStart + PostCompact)

---

## v1.0.9 (2026-06-21)

### Transcript 存活检测 —— 解决 /goal 结束后 hook 无限阻塞

**核心修复：**

- 新增 transcript 存活检测：Stop hook 读取 transcript JSONL 尾部，检查最后一条 assistant 消息是否包含 `/goal` 周期标志词。无标志词 → 会话已离开 `/goal` 模式 → 自动清理残留状态文件并放行。不再需要等待超时即可判断。
- 残留文件超时从 168h 降至 8h，作为 transcript 不可读时的兜底安全网。
- 修复 Windows GBK 编码导致 hook stop 时 emoji 输出 `UnicodeEncodeError`（v1.0.8 附录修复）。

---

## v1.0.8 (2026-06-20)

### README 全面重写

文档变更，无代码改动。

---

## v1.0.7 (2026-06-20)

### 标准 CC Marketplace 目录结构

- 重构仓库为标准 Claude Code marketplace 布局：`plugins/hello-goal/`
- 移除 `setup.bat` 和 `setup.ps1`，`setup.py` 为唯一安装脚本

---

## v1.0.6 (2026-06-20)

### Hook 输出修复

- 修复 Stop hook 输出为合法 JSON schema（放行 `{}`，阻止 `{"decision":"block",...}`）
- 插件安装到 CC 插件目录而非直指仓库
- setup.py 处理 Windows junction 删除

---

## v1.0.5 (2026-06-20)

### 输出格式与安装路径修复

- Stop hook 输出格式规范化
- 安装路径迁移到 CC 插件目录

---

## v1.0.4 (2026-06-20)

### setup.py 跨平台安装

- `setup.py` 替代 `setup.ps1`/`setup.bat`

---

## v1.0.3 (2026-06-20)

### 一键安装脚本 + 隐私修复

- 新增 setup.py/setup.bat/setup.ps1 安装脚本
- README 移除个人路径
