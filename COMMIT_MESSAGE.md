# Commit Message / 提交信息

feat(core): 全类型 API 错误触发 + DeepSeek V4 兼容 (v2.3.6)

- API 错误模式从 ~10 扩展到 ~85（9 大类），含 DeepSeek V4 专属模式
- _llm_check DeepSeek V4 thinking mode 适配：自动禁用 thinking + 回退提取
- API 可达性状态缓存（120s TTL）：LLM 失败后跳过重复调用
- 状态文件目录多级回退（CLAUDE_PLUGIN_DATA→ROOT→TEMP→脚本目录）
- max_tokens 10→100，thinking block 回退提取
- CHANGELOG.md 首次创建
- 版本号 v2.3.6 全量同步

---

feat(core): All-type API error trigger + DeepSeek V4 compatibility (v2.3.6)

- API error patterns expanded from ~10 to ~85 (9 categories) including DeepSeek V4 specific
- _llm_check DeepSeek V4 thinking mode fix: auto-disable thinking + fallback extraction
- API availability state cache (120s TTL): skip LLM after failure
- State file directory multi-level fallback (CLAUDE_PLUGIN_DATA→ROOT→TEMP→script dir)
- max_tokens 10→100, thinking block fallback extraction
- CHANGELOG.md created
- Version v2.3.6 synced across all files
