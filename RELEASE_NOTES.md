# Release Notes / 发布记录

## v2.0.3 (2026-06-21)

### 插件改名 + API 错误自动恢复

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
