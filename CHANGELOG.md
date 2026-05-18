# Changelog

## v1.2.1 — 2026-05-18 — Engineering P0+P1

### Added
- `GET /health` 健康检查端点（服务/数据库/运行时状态）
- `sync_to_wsl.sh` L 盘 → WSL 同步脚本
- `app/admin/auth.py` — Admin API Bearer Token 认证中间件
- `app/core/ratelimit.py` — 滑动窗口速率限制中间件
- `docs/engineering-roadmap.md` — 工程化进度方案文档
- `CHANGELOG.md` — 变更日志

### Changed
- `app/gateway/engine.py` — 加入 `phase:*` 阶段性日志标记（6 个阶段）
- `app/admin/api_keys.py` — API Key 改为 SHA256 哈希存储，内置 `_migrate_legacy_keys()`
- `app/providers/ollama.py` — 异常分层（Timeout/Connect/HTTP/JSON/未知）
- `app/providers/openai_compatible.py` — 异常分层（同上）
- `app/admin/config_manager.py` — YAML 写锁（threading + fcntl 双保险）
- `app/core/doctrine.py` — 全局状态文档化约束注释
- `app/api/routes.py` — 注册 AdminAuth + RateLimit 中间件
- `.gitignore` — 新增配置文件排除规则
- `docs/engineering-roadmap.md` — 更新 P0/P1 完成状态

### Fixed
- `process_request()` — `effective_input` 变量在赋值前被引用导致的 NameError

### Security
- API Key 不再以明文存储（SHA256 哈希）
- Admin API 需 Bearer Token 认证（默认: `admin:gw-console-2026`，可通过 `ADMIN_API_KEY` 环境变量覆盖）
- 速率限制：admin 10/min, v1 30/min, chat 60/min

## v1.2.0 — 2026-05-15 — Phase 3 Complete

### Added
- `/v1/completions` FIM 代码补全端点 (Fill-In-the-Middle)
- `app/cache/store.py` — 请求缓存层 (cache_get/set/invalidate/stats/cleanup)
- `app/feedback/store.py` — 用户反馈闭环 (👍/👎 + 记忆权重调整)
- 多模态请求支持 (`image_url` → 自动路由到视觉模型)
- 真 SSE 流式逐 Token 推送 (`generate_stream()`)

## v1.1.0 — 2026-05-13 — Phase 2 Complete

### Added
- `/v1/models` 返回模型能力标签 (vision/reasoning/tool_calling)
- 治理规则热管理（控制台添加/启用/禁用/删除）
- Token 趋势图表（概览仪表盘 24h 柱状图）

## v1.0.0 — 2026-05-12 — MVP Complete

### Added
- 基础网关管线：本地预处理 → 治理检测 → 云端生成 → 返回
- Police + Judge 三层治理（7 条默认规则）
- Capability 系统（9 种能力，grant/suspend/revoke）
- API Key 认证（`sk-gw-*` 格式）
- 管理控制台（8 个选项卡）
- 多模型调度（意图/语言/标签/权重评分）
- 95 测试用例
