# Commit Message / 提交信息

release: v2.3.1 —— JSON输出加固(os.write fd=1) + reason精简 + DeepSeek兼容 + 版本号/文档/架构图同步

- _write_json(): sys.stdout.buffer.write() → os.write(fd=1)，彻底绕过 Windows I/O 编码层
- 启动时抑制 stderr → os.devnull，防止 Python 警告污染 hook 输出
- sys.exit(0) → os._exit(0)，避免 atexit 回调产生额外输出
- 移除 ANTHROPIC_BASE_URL / LLM_MODEL 硬编码默认值，仅从环境变量读取
- 兼容 ANTHROPIC_AUTH_TOKEN 环境变量
- _read_stdin() 异常捕获扩展为全 Exception（覆盖 UnicodeDecodeError）
- 所有 BLOCK reason 统一精简为 "继续"（两字），不干扰 AI 推理
- 三层 JSON 输出兜底: os.write(1) → sys.stdout.buffer → print(ascii)
- _llm_check() 新增 URL/Model 缺失防护
- main() 最底层兜底直接 os.write(1, b'{...}')
- 版本号 2.2.0 → 2.3.1（plugin.json + marketplace.json + _goal_guard.py）
- README.md / README_CN.md / RELEASE_NOTES.md 更新
- 01-hero-banner.svg / architecture.svg 版本号同步

---

release: v2.3.1 — JSON output hardening (os.write fd=1) + reason simplification + DeepSeek compatibility

- _write_json(): replaced sys.stdout.buffer.write() with os.write(fd=1), bypassing Windows I/O encoding layer
- stderr redirected to os.devnull at startup to prevent Python warnings from polluting hook output
- sys.exit(0) → os._exit(0) to avoid atexit callback noise
- Removed hardcoded defaults for ANTHROPIC_BASE_URL and LLM_MODEL; read from env vars only
- API key reading also checks ANTHROPIC_AUTH_TOKEN
- _read_stdin() catches all Exception (including UnicodeDecodeError)
- All BLOCK reasons unified to "继续" (2 chars, minimal), eliminating AI cognitive distraction
- Three-layer JSON output fallback: os.write(1) → sys.stdout.buffer → print(ascii)
- _llm_check() guards for missing URL/Model
- main() deepest fallback directly os.write(1, b'{...}')
- Version 2.2.0 → 2.3.1 (plugin.json + marketplace.json + _goal_guard.py)
- README.md / README_CN.md / RELEASE_NOTES.md updated
- 01-hero-banner.svg / architecture.svg version sync
