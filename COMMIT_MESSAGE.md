# Commit Message / 提交信息

feat: v2.0.3 —— 插件改名 + API 错误自动恢复

## 实质性变更（对比 v2.0.1）

### 插件全面改名
- goal-hook → hello-goal：目录、配置、脚本、文档、市场清单全量重命名
- 仓库 URL 更新为 https://github.com/hellowind777/hello-goal
- 所有内部标识符、错误消息前缀、状态文件名统一使用新名称

### API 错误自动恢复 (Phase 1.5)
- 新增第三方大模型 API 错误模式匹配层
- 覆盖 10 种常见异常：socket close, 429/503/502/504, rate limit, timeout...
- 三源检测：stop_reason + assistant 消息 + transcript 尾部
- 检测到 API 错误后自动 BLOCK，/goal 无需人工干预恢复

### 守护层级
- 三层级联 → 四层级联：Phase 0 → 1 → 1.5 → 2 → 3 → 4

---

feat: v2.0.3 —— Plugin rename + API error auto-recovery

## Substantive changes (vs v2.0.1)

### Complete plugin rename
- goal-hook → hello-goal: full rename across dirs, configs, scripts, docs, marketplace
- Repo URL updated to https://github.com/hellowind777/hello-goal

### API error auto-recovery (Phase 1.5)
- New pattern matching layer between Phase 1 and Phase 2
- Covers 10 common third-party API error patterns
- Three-source detection: stop_reason, assistant message, transcript tail
- Auto-BLOCK on detection for seamless /goal recovery

### Guard layer
- Three-layer → four-layer cascaded analysis
