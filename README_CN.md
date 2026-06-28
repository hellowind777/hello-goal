<div align="center">
  <img src="./readme_images/01-hero-banner.svg" alt="hello-goal" width="800">
</div>

# hello-goal v2.3.5

全局 API 恢复 + 混合守护插件。API 错误（socket 断开、429、502、503）无论是否 /goal 模式均自动恢复。所有 hook stdout 输出均为硬编码合法 JSON —— LLM 语义分析仅影响内部决策分支，绝不触及 stdout。语言无关，零外部依赖。纯 Python 标准库。

[![Version](https://img.shields.io/badge/version-2.3.5-orange.svg)](./RELEASE_NOTES.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE)
[![LINUX DO](https://img.shields.io/badge/LINUX_DO-recognized-0A84FF?logo=linux&logoColor=white)](https://linux.do)

[English](./README.md) · [简体中文](./README_CN.md)

> 本项目已获得 [LINUX DO](https://linux.do) 社区认可。

## 目录

<details>
<summary><strong>点击展开</strong></summary>

- [概览](#概览)
- [解决了什么问题](#解决了什么问题)
- [工作原理](#工作原理)
- [快速开始](#快速开始)
- [使用方式](#使用方式)
- [推荐设置](#推荐设置)
- [架构说明](#架构说明)
- [文件说明](#文件说明)
- [FAQ](#faq)
- [许可证](#许可证)

</details>

## 概览

Claude Code 的 `/goal` 功能在长任务中有三类典型失败模式：

1. **中断退出** —— hook 错误、API 异常导致 `/goal` 循环意外终止
2. **主动放弃** —— 模型因疲劳、上下文过长、信心丧失而提前想结束
3. **标准降级** —— 模型悄悄降低完成标准（"差不多了"、"基本可以了"）

此外，**API 错误**（第三方大模型 socket 断开、429/502/503）会中断**任何**任务——无论是否 /goal 模式。hello-goal 在全局 Phase 0 优先拦截，自动恢复。

**hello-goal v2.3.3** 以单一 command-type Stop hook 实现四层级联守护。所有 stdout 输出均为**硬编码合法 JSON**（`print()` 走 `sys.stdout` 通道）—— LLM 语义分析仅决定走哪个内部分支，绝不直接或间接触及 hook stdout。此架构从根因消除因 LLM 生 JSON 导致的 "JSON validation failed" 错误。

### 设计原则：硬编码 JSON 输出

```
LLM 语义分析 → True / False / None（纯内部决策）
                    ↓
  _block("继续")          或         _pass()
                    ↓
  print('{"decision":"block","reason":"继续"}')  或  print('{}')
                    ↓
        ↑ 硬编码 JSON —— 绝不经过 LLM 生成 ↑
```

不同于 CC 原生 /goal 评估器（使用 DeepSeek 等第三方大模型时可能输出非 JSON 文本），hello-goal 的 hook stdout 始终为代码写死的确定性 JSON。`_llm_check()` 的 LLM 响应文本仅在内部分析（`startswith("BLOCK")` / `startswith("PASS")` 精确匹配），绝不触及 stdout。

### v2.3 vs v2.2

| | v2.2 | v2.3 |
|---|---|---|
| JSON 输出 | `sys.stdout.buffer.write()` + `sys.stdout.flush()` | `print(json.dumps(...))` 走 `sys.stdout` —— CC 稳定捕获 |
| 输出原则 | 冗长 reason 字符串作为 hook 反馈 | 硬编码 JSON —— LLM 输出永不触及 stdout |
| 编码设置 | `sys.stdout.reconfigure(encoding="utf-8")` | 同 —— 启动时通过 `_setup_encoding()` 恢复 |
| 进程退出 | `sys.exit(0)` | `sys.exit(0)` |
| API 默认值 | 硬编码 `api.anthropic.com` + `claude-3-5-haiku` | 无硬编码默认值 — 仅从 CC 环境变量读取 |
| API 密钥 | 仅读 `ANTHROPIC_API_KEY` | 兼容 `ANTHROPIC_AUTH_TOKEN` |
| stdin 异常 | 捕获 `JSONDecodeError` + `IOError` | 捕获所有 `Exception`（含 `UnicodeDecodeError`） |
| BLOCK reason | 冗长诊断字符串（~80 字符） | `"继续"` — 2 字，极简 |
| Hook timeout | 60s | 30s |
| 原生评估器共存 | 并行，可能冲突 | 并行 — 硬编码 JSON 确保独立校验 |

### v2.2 vs v2.1

| | v2.1 | v2.2 |
|---|---|---|
| API 错误恢复 | 仅 /goal 模式（Phase 1.5） | 全局（Phase 0），优先于 /goal 检测 |
| 非 /goal 的 API 错误 | PASS（任务中断） | BLOCK（自动恢复） |
| Phase 顺序 | /goal → 中断 → API → 行为+LLM | API → /goal → 中断 → 行为+LLM |

### v2.1 vs v2.0

| | v2.0 | v2.1 |
|---|---|---|
| 判定模型 | 行为信号硬阈值（≥50%→BLOCK） | 所有可疑信号统一经 LLM 语义分析 |
| 误判风险 | 降速写总结可能被误判为趋势塌缩 | LLM 区分任务正常收尾和提前放弃 |
| LLM 调用量 | ~10% 轮次（仅模糊区间） | 所有有行为信号的轮次（确保正确性） |
| 复杂度 | 4 阶段（Phase 2/3/4 + 阈值调整） | 3 阶段（统一 Phase 2：信号+LLM） |

## 解决了什么问题

| 场景 | 无 hello-goal | 有 hello-goal v2.3.5 |
|------|-------------|------------------|
| 任意会话 API 错误（socket/429/503） | 任务永久中断 | Phase 0 检测 → 自动恢复 BLOCK |
| `/goal` 中 hook 报错中断 | 会话终止 | 检测 stop_reason 异常 → BLOCK 继续 |
| 模型疲劳想放弃 | 原生评估器放行 | 行为信号 + LLM 语义确认 → BLOCK |
| 模型降级完成标准 | 低质量"完成" | 行为信号触发 LLM 分析 → BLOCK |
| 上下文压缩后迷失 | 模型忘记目标 | PostCompact 刷新检测状态 |
| 普通会话（无 API 错误） | — | 零干预，PASS 直接放行 |

## 工作原理

```
Stop Hook 触发
  │
  ├─ Phase 0 (全局): API 错误检测
  │   ├─ 匹配 11 种模式: socket close, 429/503/502/504, rate limit, timeout...
  │   ├─ 来源: stop_reason, assistant 消息, transcript 尾部
  │   └─ 检测到 API 错误 → BLOCK（自动恢复，无论是否 /goal 模式）
  │
  ├─ Phase 1: /goal 检测（CC 原生标记 + 用户命令 + 缓存优先）
  │   ├─ 信号A: CC 原生 "Goal set:" / "Goal cleared:" 标记
  │   ├─ 信号B: 用户 /goal 命令解析（备用）
  │   ├─ 信号C: stop_hook_summary 条目（仅确认）
  │   └─ 非 /goal → PASS（零干预）
  │
  ├─ Phase 2: 中断恢复
  │   └─ stop_reason != "end_turn" → BLOCK
  │
  └─ Phase 3: 行为信号 + LLM 语义分析 —— 统一混合判定
      ├─ 信号1: 末轮零工具调用      +30%
      ├─ 信号2: 趋势塌缩（消息&工具下降） +25%
      ├─ 信号3: 停滞循环（3轮相同工具）  +20%
      ├─ 信号4: 只读停滞（5轮无写入）    +15%
      ├─ score < 0.20 → PASS（无行为信号）
      └─ score ≥ 0.20 → LLM 语义分析（含行为上下文）
          ├─ 轻量模型分析 last_assistant_message + 行为信号
          ├─ 区分任务正常收尾与提前放弃
          ├─ BLOCK → 继续    PASS → 放行
          └─ API 不可用 → 保守 BLOCK
  └─ 全局异常兜底：未预期内部异常 → BLOCK
```

所有 BLOCK 决策均返回 reason `"继续"` — 极简反馈，不干扰 AI 推理。

所有 stdout 输出使用 `print()` 走 `sys.stdout` 通道。LLM 语义分析结果仅决定走哪个分支 —— 最终 JSON 由代码写死。

### 为什么不用关键词/正则

世界上有 200+ 种语言，模型可以用任意语言表达"放弃"。关键词正则既不可穷举也不可维护。

v2.3.3 的行为分析**不读文字内容**——只对 transcript 中的工具调用模式、消息长度趋势、轮次结构打分。这些信号在任何语言中完全相同。LLM 语义分析对所有可疑轮次做最终裁决，天然理解任意语言。

## 快速开始

### 前置条件

- 已安装 [Claude Code](https://claude.ai/code)
- Python 3

### 安装

```bash
git clone https://github.com/hellowind777/hello-goal.git
cd hello-goal
python setup.py
```

重启 Claude Code。完成。

### 手动安装

克隆仓库后，在 `~/.claude/settings.json` 中添加：

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

### 验证

`setup.py` 会自动验证所有文件就位：

```
[1/3] 安装到 ~/.claude/plugins/local-marketplaces/hello-goal-marketplace/plugins/hello-goal ...
[2/3] 注册到 settings.json ...
[3/3] 验证 ...
  [OK] hooks/hooks.json
  [OK] scripts/_goal_guard.py
  [OK] .claude-plugin/plugin.json

已安装: .../hello-goal-marketplace
重启 Claude Code 激活。
```

## 使用方式

**提示词不需要任何插件相关代码。** 只需描述任务目标和验收条件。

```
/goal 按提示词执行
```

插件全程自动监控，检测到非正常终止时自动阻止并让 /goal 继续。API 错误在任意会话中均自动恢复。

## 推荐设置

```json
"CLAUDE_CODE_STOP_HOOK_BLOCK_CAP": "1000"
```

Claude Code v2.1.143+ 强制限制 Stop hook 最多连续阻止 8 次。提高此值可防止正常的长任务被误杀。

## 架构说明

```
hooks/hooks.json
├── Stop (command, 30s)          ← 核心守护：四层级联分析
├── StopFailure (command, 3s)    ← 安全网：原生评估器 JSON 失败 → 自动 BLOCK
├── SessionStart (command, 5s)   ← 清理过期状态，初始化会话
└── PostCompact (command, 3s)    ← 压缩后刷新检测缓存

scripts/_goal_guard.py (~730 行, 零依赖)
├── handle_stop()           ← Phase 0-3 主逻辑
├── handle_session_start()  ← 状态清理
├── handle_post_compact()   ← 缓存刷新（保留 goal_detected 粘性先验）
├── _detect_goal_active()   ← 三级 /goal 检测（原生标记 + 命令 + summary）
├── _structural_score()     ← 行为结构信号加权（4 信号）
├── _detect_api_error()     ← API 错误模式匹配（11 种模式，3 来源）
└── _llm_check()            ← LLM 语义分析（含行为上下文，urllib）

scripts/_goal_failure.py (6 行, 零依赖)
└── StopFailure 兜底        ← 任何 hook 失败时无条件 BLOCK
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `plugins/hello-goal/hooks/hooks.json` | 四钩子注册（Stop + StopFailure + SessionStart + PostCompact） |
| `plugins/hello-goal/scripts/_goal_guard.py` | 混合守护主脚本（全功能分析） |
| `plugins/hello-goal/scripts/_goal_failure.py` | StopFailure 安全网（6 行，无条件 BLOCK） |
| `plugins/hello-goal/.claude-plugin/plugin.json` | 插件元数据（v2.3.5） |
| `.claude-plugin/marketplace.json` | 市场清单 |
| `setup.py` | 一键跨平台安装脚本 |

## FAQ

<details>
<summary><strong>Q: 会影响非 /goal 会话吗？</strong></summary>

**A:** 对 API 错误——会响应，但这正是你需要的行为（socket 断开不应中断你的任务）。对正常结束的非 API 错误 Stop，插件立即 PASS，零干预。
</details>

<details>
<summary><strong>Q: 需要修改提示词吗？</strong></summary>

**A:** 不需要。v2.3.3 通过 CC 原生标记从 transcript 自动检测 /goal 状态，不依赖提示词写入任何文件。
</details>

<details>
<summary><strong>Q: LLM 语义分析会增加多少成本？</strong></summary>

**A:** 所有有行为信号（score ≥ 0.20）的轮次触发 LLM 分析。每次轻量模型调用约 $0.0005。200 轮 /goal 任务若每轮都有行为信号，总成本约 $0.10。无行为信号的轮次（score < 0.20）立即放行，零 LLM 成本。
</details>

<details>
<summary><strong>Q: 和原生 /goal 内置 hook 冲突吗？</strong></summary>

**A:** 两者作为独立的 stop hook 并行运行。当原生评估器输出非 JSON 文本（使用 DeepSeek 等第三方大模型时常见）时，CC 会报告 "Stop hook error: JSON validation failed"。hello-goal v2.3.5 通过 **StopFailure 安全网** 解决此问题：一个独立的 6 行 hook 脚本，仅在 Stop hook 失败时触发，无条件返回 BLOCK 让任务继续。这确保原生评估器的 JSON 错误无法永久中断 /goal 任务。
</details>

<details>
<summary><strong>Q: 任务真的完成了，会被误拦吗？</strong></summary>

**A:** 不会。任务正常完成时，LLM 语义分析能识别真正的完成（最终报告、测试结果、全面总结）并返回 PASS —— 即使行为信号（无工具、趋势下降）看起来可疑。LLM 被明确指示区分任务正常收尾和提前放弃。
</details>

<details>
<summary><strong>Q: 插件自身出错了怎么办？</strong></summary>

**A:** 主入口包含全局异常兜底。任何未预期的内部异常通过 `print()` 输出硬编码的 BLOCK 决策让任务继续执行，不会因 Python 错误导致 "JSON validation failed" 中断任务。
</details>

## 许可证

本项目采用 [Apache-2.0 许可证](./LICENSE)。

---

<div align="center">

![GitHub stars](https://img.shields.io/github/stars/hellowind777/hello-goal?style=social)
![GitHub forks](https://img.shields.io/github/forks/hellowind777/hello-goal?style=social)

</div>
