<div align="center">
  <img src="./readme_images/01-hero-banner.svg" alt="hello-goal" width="800">
</div>

# hello-goal v2.0

混合守护插件 —— `/goal` 任务自动监控，防止非正常终止。行为结构分析 + LLM 语义兜底 + API 错误自动恢复。语言无关，零提示词侵入。

[![Version](https://img.shields.io/badge/version-2.0.3-orange.svg)](./RELEASE_NOTES.md)
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

**hello-goal v2.0** 以单一 command-type Stop hook 实现四层级联守护，自动检测并阻止上述非正常终止，让 `/goal` 循环持续到任务真正完成。

### v2.0 vs v1.x

| | v1.x | v2.0 |
|---|---|---|
| 检测方式 | 提示词写入 `.goal_status.json` 状态文件 | 自动从 transcript 检测 `/goal` 状态 |
| 提示词侵入 | 需要嵌入状态写入代码 | **零侵入**，提示词只管任务目标 |
| 放弃检测 | 无 | 行为结构分析 + LLM 语义兜底 |
| 语言支持 | 仅标记匹配 | 全语言（行为分析是语言无关的） |
| 钩子数量 | 1 个 Stop hook | 3 个（Stop + SessionStart + PostCompact） |
| API 错误恢复 | 无 | 自动模式匹配第三方 API 异常 |

## 解决了什么问题

| 场景 | 无 hello-goal | 有 hello-goal v2.0 |
|------|-------------|------------------|
| `/goal` 中 hook 报错中断 | 会话终止 | 检测 stop_reason 异常 → BLOCK 继续 |
| 第三方 API 错误（429/503 等） | `/goal` 循环中断 | 模式匹配 → 自动恢复 BLOCK |
| 模型疲劳想放弃 | 原生评估器放行 | 行为结构信号 + LLM 语义确认 → BLOCK |
| 模型降级完成标准 | 低质量"完成" | 结构分析检测到停滞 → BLOCK |
| 上下文压缩后迷失 | 模型忘记目标 | PostCompact 刷新检测状态 |
| 非 `/goal` 普通会话 | — | 零干预，pass 直接放行 |

## 工作原理

```
Stop Hook 触发
  │
  ├─ Phase 0: /goal 检测（双信号交叉验证）
  │   ├─ 信号A: transcript 中有 /goal 命令
  │   ├─ 信号B: transcript 中有原生 /goal 评估器痕迹
  │   └─ 非 /goal → PASS（零干预）
  │
  ├─ Phase 1: 中断恢复
  │   └─ stop_reason != "end_turn" → BLOCK
  │
  ├─ Phase 1.5: API 错误自动恢复
  │   ├─ 匹配模式: socket close, 429/503/502/504, rate limit, timeout...
  │   ├─ 来源: stop_reason, assistant 消息, transcript 尾部
  │   └─ 检测到 API 错误 → BLOCK（/goal 自动恢复继续）
  │
  ├─ Phase 2: 行为结构评分（<1ms，语言无关）
  │   ├─ 信号1: 末轮零工具调用      +30%
  │   ├─ 信号2: 趋势塌缩（消息&工具下降） +25%
  │   ├─ 信号3: 停滞循环（3轮相同工具）  +20%
  │   ├─ 信号4: 只读停滞（5轮无写入）    +15%
  │   ├─ ≥50% → BLOCK    <20% → PASS
  │   └─ 其他 → Phase 3
  │
  ├─ Phase 3: LLM 语义兜底（仅模糊区间，~10% 轮次）
  │   ├─ Haiku 分析 last_assistant_message
  │   ├─ 放弃/降级意图? → BLOCK
  │   └─ API 不可用 → 保守 BLOCK
  │
  └─ Phase 4: 循环防护
      └─ stop_hook_active → 阈值提升至 70%
```

### 为什么不用关键词/正则

世界上有 200+ 种语言，模型可以用任意语言表达"放弃"。关键词正则既不可穷举也不可维护。

v2.0 的行为结构分析**不读文字内容**——只分析 transcript 中的工具调用模式、消息长度趋势、轮次结构。这些信号在任何语言中完全相同。LLM 语义兜底仅在结构信号模糊时调用，天然理解任意语言。

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

插件全程自动监控，检测到非正常终止时自动阻止并让 /goal 继续。

## 推荐设置

```json
"CLAUDE_CODE_STOP_HOOK_BLOCK_CAP": "1000"
```

Claude Code v2.1.143+ 强制限制 Stop hook 最多连续阻止 8 次。提高此值可防止正常的长任务被误杀。

## 架构说明

```
hooks/hooks.json
├── Stop (command, 12s)          ← 核心守护：四层级联分析
├── SessionStart (command, 5s)   ← 清理过期状态，初始化会话
└── PostCompact (command, 3s)    ← 压缩后刷新检测缓存

scripts/_goal_guard.py (~400 行, 零依赖)
├── handle_stop()           ← Phase 0-4 主逻辑
├── handle_session_start()  ← 状态清理
├── handle_post_compact()   ← 缓存刷新
├── _structural_score()     ← 行为结构信号加权
├── _detect_api_error()     ← API 错误模式匹配与自动恢复
├── _llm_check()            ← LLM 语义兜底（urllib，继承 ANTHROPIC_API_KEY）
└── _detect_goal_active()   ← 双信号 /goal 检测
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `plugins/hello-goal/hooks/hooks.json` | 三钩子注册（Stop + SessionStart + PostCompact） |
| `plugins/hello-goal/scripts/_goal_guard.py` | 混合守护主脚本 |
| `plugins/hello-goal/.claude-plugin/plugin.json` | 插件元数据（v2.0.3） |
| `.claude-plugin/marketplace.json` | 市场清单 |
| `setup.py` | 一键跨平台安装脚本 |

## FAQ

<details>
<summary><strong>Q: 会影响非 /goal 会话吗？</strong></summary>

**A:** 不会。hook 先检测 /goal 是否活跃。非 /goal 会话直接 pass，零开销零干扰。
</details>

<details>
<summary><strong>Q: 需要修改提示词吗？</strong></summary>

**A:** 不需要。v2.0 完全自动从 transcript 检测 /goal 状态，不依赖提示词写入任何文件。
</details>

<details>
<summary><strong>Q: LLM 语义兜底会增加多少成本？</strong></summary>

**A:** 仅约 10% 的轮次触发 LLM 调用（行为信号模糊区间），每次 ~$0.0005。200 轮 /goal 任务总成本约 $0.01。
</details>

<details>
<summary><strong>Q: 和原生 /goal 内置 hook 冲突吗？</strong></summary>

**A:** 不冲突。两者并行运行，任一 BLOCK 即阻止停止。本插件以 command hook 独立判断，不依赖原生 prompt hook。
</details>

<details>
<summary><strong>Q: 任务真的完成了，会被误拦吗？</strong></summary>

**A:** 不会。四层分析都有 PASS 判断。任务正常完成时，行为信号低于阈值且 LLM 确认真完成，hook 放行。
</details>

## 许可证

本项目采用 [Apache-2.0 许可证](./LICENSE)。

---

<div align="center">

![GitHub stars](https://img.shields.io/github/stars/hellowind777/hello-goal?style=social)
![GitHub forks](https://img.shields.io/github/forks/hellowind777/hello-goal?style=social)

</div>
