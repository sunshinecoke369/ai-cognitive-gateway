# Changelog

## v1.4.0 — 2026-05-18 — O1: Docker Packaging

### Added
- `Dockerfile` — Python 3.12-slim 基础镜像，含 healthcheck
- `docker-compose.yml` — 独立运行网关（mock 模式），零外部依赖
- `docker-compose.ollama.yml` — 可选 Ollama overlay，nvidia GPU 支持
- `.dockerignore` — 排除 __pycache__/ .venv/ data/ logs/ 等

### Infrastructure
- 部署方式: `docker compose up -d --build` 替代 `sync_to_wsl.sh + systemctl`
- 开发模式: `docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d`
- Provider 解耦: 网关可独立运行（mock），Ollama 为可选叠加层

## v1.3.3 — 2026-05-18 — V4 + Decoupling Principle

### Added
- `docs/engineering-roadmap.md` — ADR-014 Provider 解耦合原则
- P3 O1 Docker 方案改为解耦式架构（Gateway 独立容器，Ollama 可选 overlay）
- 架构原则文档化：BaseProvider 接口不绑定任何具体引擎

### Changed
- `app/cache/store.py` — `_normalize_text()` 缓存 key 归一化（小写/去标点/合并空格）

## v1.3.3 — 2026-05-18 — V4: Semantic Cache Normalization

### Changed
- `app/cache/store.py` — `_normalize_text()` 缓存 key 归一化（小写/去标点/合并空格）
- `_hash_key()` 写入和查询使用归一化后的输入，`'Hello!'` 和 `'hello'` 命中同一缓存
- `_normalize_messages()` — messages 中的 content 也做归一化

### Performance
- 预计提升缓存命中率 15-30%（取决于客户端输入一致性）

## v1.3.2 — 2026-05-18 — V1: Phase Timing Metrics

### Added
- `app/gateway/engine.py` — `_log_phase_timing()` 闭包函数，记录每个阶段的耗时
- `perf:phase_timing` 结构化日志（governance / local_preprocess / prompt_build / cloud_schedule / cloud_generate / persist）
- `process_request` + `process_request_stream` 双函数均支持 phase timing

### Observability
- 每个请求输出 6 个时间戳点，可精确分析网关瓶颈
- 结合 V2 连接池优化后，可验证延迟改善效果

## v1.3.1 — 2026-05-18 — V2: HTTP Connection Pool

### Changed
- `app/providers/client.py` (new) — 全局 httpx.AsyncClient（HTTP/2 + keepalive 连接池）
- `app/providers/ollama.py` — `_call_ollama_chat/generate` 改用全局客户端，timeout 改按请求传参
- `app/providers/openai_compatible.py` — `_call_api` + `generate_stream` 改用全局客户端

### Performance
- 预计每请求节省 50-200ms（省去 DNS 解析 + TCP 握手 + TLS 握手）
- 连接池上限 20 连接，keepalive 10 连接，30s 过期
- 支持 HTTP/2 多路复用

## v1.3.0 — 2026-05-18 — Performance Strategy Established

### Added
- `docs/engineering-roadmap.md` — 新增 **P4 Performance & Observability** 阶段（5 项任务）
- 性能架构声明（延迟分布分析、不换语言的决策依据）
- 性能风险登记 R9-R12
- ADR-013: 性能优先优化缓存与连接池，不换语言

### Tasks planned (P4)
- V1: 请求级耗时指标 phase timing
- V2: httpx 全局连接池复用（HTTP/2 + keepalive）
- V3: Prometheus /metrics 端点
- V4: 语义缓存 key 归一化
- V5: 性能基线基准测试

## v1.2.2 — 2026-05-18 — Data Volume Cleanup + Git Init

### Changed
- `.gitignore` — `data/*` + `logs/*` 全量排除，仅保留 `.gitkeep`
- `sync_to_wsl.sh` — 简化排除规则匹配 `.gitignore`
- `docs/engineering-roadmap.md` — 更新至 v1.2（进度 17/28 + Git 完成）

### Fixed
- **D1** — 删除 `L:\` 根目录残留的 `data/api_keys.json` 和 `logs/gateway.log`
- **D2** — `allowed_models.json` 中 `gemma4:e4b` 从 cloud 移至 local
- **D3** — 代码与运行时数据隔离（`.gitignore` + sync 双重保障）

### Infrastructure
- Git 初始化：58 文件，8517 行 → `github.com/sunshinecoke369/ai-cognitive-gateway`
- 推送方式：SSH (ed25519)

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
