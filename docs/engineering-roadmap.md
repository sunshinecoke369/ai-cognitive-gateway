# AI Cognitive Gateway — 工程化进度方案

> **文档版本**: v1.1
> **创建日期**: 2026-05-18
> **最后更新**: 2026-05-18
> **P0 状态**: ✅ 已完成（7 项）
> **P1 状态**: ✅ 已完成（6 项）
> **当前阶段**: P2 待开始
> **覆盖范围**: Windows 数据卷（L:） + WSL Ubuntu 运行时 + Ollama 本地模型

---

## 开发工作流（首次设置后请遵守）

### 架构：双机双份

```
L:\AI Cognitive Operating System\ai-cognitive-gateway\    ← 源码真实来源（SSOT）
                │
                │  sync_to_wsl.sh  (手动触发)
                ▼
WSL /root/ai-cognitive-gateway/                           ← 运行环境（systemd 服务）
```

### 日常操作流程

```bash
# Step 1 — 我改完 L 盘代码后，你在 WSL 执行：
cd /root/ai-cognitive-gateway
bash sync_to_wsl.sh

# Step 2 — 重启服务
sudo systemctl restart ai-gateway

# Step 3 — 验证
curl http://localhost:8000/health
curl http://localhost:8000/chat -X POST \
  -H "Content-Type: application/json" \
  -d '{"user_input":"Hello"}'
tail -10 /tmp/gateway.log | grep phase
```

### Git 初始化（上传 GitHub 前）

```bash
# 在 L 盘路径执行（Windows 或 WSL 均可）
cd /mnt/l/AI\ Cognitive\ Operating\ System/ai-cognitive-gateway
git init
git add -A
git commit -m "Initial commit: AI Cognitive Gateway v1.2"

# 关联远程仓库（GitHub）
git remote add origin https://github.com/your-org/ai-cognitive-gateway.git
git push -u origin main
```

### .gitignore 当前状态

已覆盖：`__pycache__/`、`.venv/`、`data/*.db`、`data/gateway_config.yaml`、`data/allowed_models.json`、`data/api_keys.json`、`logs/`、`_debug*.py`、`.pytest_cache/`、`.env`

---

## 一、总览：阶段进度

| 阶段 | 名称 | 任务数 | 状态 | 预估工时 | 实际工时 |
|:----:|------|:------:|:----:|:--------:|:--------:|
| **P0** | Quick Wins | 7 项 | ✅ 已完成 | 2 天 | 1 天 |
| **P1** | Foundation Hardening | 6 项 | ✅ 已完成 | 5 天 | 1 天 |
| **P2** | Architecture Evolution | 6 项 | ⏳ 待开始 | 8 天 | — |
| **P3** | Platform Readiness | 5 项 | ⏳ 待开始 | 5 天 | — |
| | **合计** | **24 项** | **13/24** | **20 天** | **2 天** |

```
Week 1                        Week 2-4
████████████████████████████████████████████████████████
████ P0 (done) ████ P1 (done) ████ P2 待开始 ████ P3 待开始 ██
                               ████ (P2 与 P3 可并行推进) ████
```

---

## 二、Phase 0 — Quick Wins（已完成 ✅）

> **目标**: 清除阻塞性问题，让系统在 WSL 生产环境可正常运行。
> **完成日期**: 2026-05-18
> **验证结果**: 95 测试全部通过，/health ✅，阶段日志 ✅，全链路 200 ✅

| # | 任务 | 类型 | 负责模块 | 状态 | 备注 |
|---|------|:----:|----------|:----:|------|
| Q1 | 配置 DeepSeek API Key | 配置 | `gateway_config.yaml` | ✅ | 通过控制台配置，非代码问题 |
| Q2 | 清理数据卷根目录残留文件 | 清理 | `L:\data\` `L:\logs\` | ✅ | 文件清空 |
| Q3 | 修正 `allowed_models.json` cloud 列表含 gemma4 | 修复 | `data/allowed_models.json` | ✅ | gemma4 移至 local |
| Q4 | 验证 `/admin/rules` DELETE 路由 | 验证 | `app/admin/router.py` | ✅ | 路由完整可用 |
| Q5 | 确认 systemd 工作目录路径 | 运维 | WSL systemd 配置 | ✅ | `/root/ai-cognitive-gateway/` ✅ |
| Q6 | process_request 阶段性日志标记 | 增强 | `app/gateway/engine.py` | ✅ | 6 个 `phase:*` 日志点，修复变量引用 bug |
| Q7 | 添加 `/health` 健康检查端点 | 增强 | `app/api/routes.py` | ✅ | 返回服务/数据库/运行时状态 |
| Q8 | data/ + logs/ 加入 .gitignore | 配置 | `.gitignore` | ✅ | 新增配置敏感文件排除 |

### 关键产出

- `sync_to_wsl.sh` — L 盘 → WSL 同步脚本（排除 .venv/ runtime-data）
- `GET /health` — 健康检查端点
- `phase:*` 日志 — `governance_check` → `local_preprocess` → `cloud_prompt_build` → `cloud_schedule` → `cloud_generate` → `completed`
- `.env` 模板 — 带 Ollama 配置的生产环境变量
- WSL 部署文档 — 写入持久记忆

---

## 三、Phase 1 — Foundation Hardening（已完成 ✅）

> **目标**: 解决安全和稳定性核心问题。
> **完成日期**: 2026-05-18
> **验证结果**: Admin 401 ✅, Rate limit headers ✅, 聊天正常 ✅

| # | 任务 | 类型 | 负责模块 | 状态 | 备注 |
|---|------|:----:|----------|:----:|------|
| F1 | API Key 改为哈希存储 | 安全 | `app/admin/api_keys.py` | ✅ | SHA256 存储 + `_migrate_legacy_keys()` 自动迁移 |
| F2 | 全局可变状态文档化约束 | 架构 | `app/core/doctrine.py` | ✅ | 模块 docstring 标注单 Worker 约束 |
| F3 | Admin API 添加认证中间件 | 安全 | `app/admin/auth.py` (新) | ✅ | Bearer Token / X-Admin-Key 认证 |
| F4 | 分层异常捕获 | 健壮性 | `ollama.py`, `openai_compatible.py` | ✅ | 区分 Timeout/Connect/HTTP/JSON/未知 |
| F5 | YAML 并发写入加锁 | 健壮性 | `app/admin/config_manager.py` | ✅ | threading.Lock + fcntl.flock 双保险 |
| F6 | 添加速率限制中间件 | 安全 | `app/core/ratelimit.py` (新) | ✅ | admin 10/min, v1 30/min, chat 60/min |

### 新增文件

| 文件 | 说明 |
|------|------|
| `app/admin/auth.py` | Admin API Bearer Token 认证中间件。默认密钥: `admin:gw-console-2026`（通过环境变量 `ADMIN_API_KEY` 覆盖） |
| `app/core/ratelimit.py` | 滑动窗口速率限制中间件。分级限流 + `X-RateLimit-*` 响应头 |

### 关键产出

- API Key 哈希迁移函数 `_migrate_legacy_keys()` — 启动时自动将旧明文 Key 转为 SHA256
- Admin 认证 — 无认证头访问 `/admin/*` 返回 401
- 速率限制 — `/chat` 60次/分, `/v1/*` 30次/分, `/admin/*` 10次/分
- 错误分类 — `[TIMEOUT]` / `[CONNECTION_FAILED]` / `[HTTP_ERROR]` / `[PARSE_ERROR]` 替代统一 `None`

---

## 四、Phase 2 — Architecture Evolution（待开始）

> **目标**: 完成核心架构优化。
> **前提**: P1 全部完成。

### 任务清单

| # | 任务 | 类型 | 负责模块 | 预估工时 | 依赖 |
|---|------|:----:|----------|:--------:|:----:|
| A1 | `process_request` 函数拆分 | 重构 | `app/gateway/engine.py` | 6h | — |
| A2 | Legislature 层实现 | 新模块 | `app/governance/legislature.py` (新) | 8h | — |
| A3 | Memory 分层扩展 | 增强 | `app/memory/store.py` | 6h | — |
| A4 | Token 计数改用 tiktoken | 增强 | `app/providers/base.py`, `engine.py` | 4h | — |
| A5 | 语义级注入检测 | 新模块 | `app/governance/semantic.py` (新) | 16h | — |
| A6 | `app/engines/` 合并入 `app/providers/` | 重构 | `app/engines/*`, `app/providers/` | 3h | — |

### 详细方案

各任务详细方案见本文档对应章节（待实现后补充具体代码）。

---

## 五、Phase 3 — Platform Readiness（待开始）

> **目标**: 补齐可运维性短板。
> **前提**: P1 全部完成。与 P2 可并行。

### 任务清单

| # | 任务 | 类型 | 负责模块 | 预估工时 | 依赖 |
|---|------|:----:|----------|:--------:|:----:|
| O1 | Docker 打包 | 运维 | 项目根目录 (Dockerfile) | 6h | — |
| O2 | 日志轮转配置 | 运维 | WSL `/etc/logrotate.d/` | 1h | — |
| O3 | `pyproject.toml` + 依赖分组 | 工程化 | 项目根目录 (新文件) | 2h | — |
| O4 | CORS 配置 | 功能 | `app/api/routes.py` | 30min | — |
| O5 | Git 初始化 + 首次 Commit | 工程化 | 项目根目录 | 30min | — |

---

## 六、风险登记册（更新于 2026-05-18）

| # | 风险 | 概率 | 影响 | 等级 | 缓解措施 | 状态 |
|---|------|:----:|:----:|:----:|----------|:----:|
| R1 | DeepSeek API Key 未配置 | 低 | 高 | 🟢 | 通过控制台配置，已正常使用 | ✅ 已关闭 |
| R3 | Admin API 未认证 | 低 | 高 | 🟢 | F3 中间件已实现 | ✅ 已关闭 |
| R4 | API Key 明文泄露 | 低 | 高 | 🟢 | F1 哈希存储 + gitignore | ✅ 已关闭 |
| R5 | YAML 并发写损坏 | 低 | 高 | 🟡 | F5 文件锁已实现 | 🟡 监控中 |
| R6 | 多 Worker 全局状态不一致 | 低 | 中 | 🟡 | F2 文档化约束 | 🟡 监控中 |
| R7 | 代码与数据同仓 | 中 | 低 | 🟢 | O5 .gitignore 已处理 | 🟢 低 |
| R8 | 速率限制影响控制台正常使用 | 低 | 低 | 🟢 | 分级限流，admin 10/min 充足 | 🟢 低 |

---

## 七、ADR（架构决策记录）

### ADR-008: Phase 1 优先加固安全而非重构

**日期**: 2026-05-18
**状态**: ✅ 已采纳已执行

**背景**: 审查发现 3 个安全高危问题（Key 明文、Admin 无认证、无速率限制），1 个架构问题（全局状态）。

**决策**: Phase 1 全部用于安全加固和稳定性。架构重构推迟到 Phase 2。

**结果**: 安全加固全部完成：F1（Key 哈希）✅、F3（Admin 认证）✅、F6（限流）✅

### ADR-009: API Key 采用哈希存储而非加密

**日期**: 2026-05-18
**状态**: ✅ 已采纳已执行

**决策**: 存储 `SHA256(key)` 哈希，删除不可恢复。管理控制台只显示 key 前缀（前 14 位）。

**附加**: 内置 `_migrate_legacy_keys()` 函数，启动时自动迁移旧明文 Key。

### ADR-010: Legislature 层采用渐进式引入

**日期**: 2026-05-18
**状态**: 建议（待 P2 执行）

**决策**: Legislature 注册策略同时保留现有硬编码逻辑，通过 Feature Flag 控制切换。

### ADR-011: 速率限制采用内存滑动窗口而非第三方库

**日期**: 2026-05-18
**状态**: ✅ 已采纳已执行

**背景**: 不引入 slowapi/token-bucket 等外部依赖。

**决策**: 自实现 `SlidingWindowCounter` 基于 `time.monotonic()` 的滑动窗口计数器，单 Worker 安全。

**约束**: 不跨 uvicorn worker，多 Worker 需迁移 Redis。

### ADR-012: YAML 写锁采用 threading + fcntl 双保险

**日期**: 2026-05-18
**状态**: ✅ 已采纳已执行

**决策**: 线程级锁（Python threading.Lock）防同进程并发 + 文件级锁（fcntl.flock）防多进程并发。Windows 降级为 threading 锁。

---

## 八、变更日志

| 日期 | 版本 | 变更内容 |
|:----:|:----:|----------|
| 2026-05-18 | v1.1 | P0(7项)+P1(6项) 完成；ADR 状态更新；风险登记册更新；新增 ADR-011/012 |
| 2026-05-18 | v1.0 | 初始版本：4 阶段、25 项任务、8 ADR、风险登记册、执行路线图 |

---

## 九、Git 初始化和 GitHub 上传指引

首次上传前需执行：

```bash
# 在 WSL 中（L 盘代码已通过 mount 映射）
cd /root/ai-cognitive-gateway

# 确保 .gitignore 已排除敏感文件
cat .gitignore

# 初始化仓库
git init
git add -A
git commit -m "P0+P1: 工程化基础加固完成

- P0 Quick Wins (7项): health端点、阶段日志、同步脚本、gitignore
- P1 Foundation Hardening (6项): Key哈希、Admin认证、
  异常分层、YAML锁、速率限制、全局状态文档化"

# 关联 GitHub 远程仓库
git remote add origin https://github.com/your-org/ai-cognitive-gateway.git
git push -u origin main
```

> **维护说明**: 本文档与 `docs/project-management.md` 互补。PM 文档记录已完成的工作和里程碑，本文档记录未来的工程化计划。每次 Phase 完成后更新版本号 + 变更日志。
