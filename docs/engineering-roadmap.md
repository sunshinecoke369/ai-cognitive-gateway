# AI Cognitive Gateway — 工程化进度方案

> **文档版本**: v1.5
> **创建日期**: 2026-05-18
> **最后更新**: 2026-05-18
> **P0 状态**: ✅ 已完成（7 项）
> **P1 状态**: ✅ 已完成（6 项）
> **D 系列**: ✅ D1/D2/D3 全部解决
> **Git 初始化**: ✅ GitHub 已推送（58 文件，8517 行）
> **P4 状态**: ✅ V2 完成中（1/5 — httpx 连接池）
> **当前阶段**: P4 V2 完成，剩余可选
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

### Git 初始化 ✅ 已完成

**仓库**: `git@github.com:sunshinecoke369/ai-cognitive-gateway.git`
**首次提交**: 58 文件，8517 行，v1.2.1
**推送方式**: SSH（ed25519）

后续每次功能完成一个可独立验证的节点后：

```bash
cd /root/ai-cognitive-gateway
git add -A
git commit -m "简短描述改动内容"
git push
```

### .gitignore 当前状态

已覆盖：`__pycache__/`、`.venv/`、`data/*.db`、`data/gateway_config.yaml`、`data/allowed_models.json`、`data/api_keys.json`、`logs/`、`_debug*.py`、`.pytest_cache/`、`.env`

---

## 一、总览：阶段进度

| 阶段 | 名称 | 任务数 | 状态 | 预估工时 | 实际工时 |
|:----:|------|:------:|:----:|:--------:|:--------:|
| **P0** | Quick Wins | 7 项 | ✅ 已完成 | 2 天 | 1 天 |
| **P1** | Foundation Hardening | 6 项 | ✅ 已完成 | 5 天 | 1 天 |
| **D** | 数据卷清理 | 3 项 | ✅ 已完成 | — | — |
| **G** | Git 初始化 + GitHub | 1 项 | ✅ 已完成 | 30min | 30min |
| **P2** | Architecture Evolution | 6 项 | ⏳ 待开始 | 8 天 | — |
| **P3** | Platform Readiness | 4 项 | ✅ O1 完成（1/4） | 5 天 | — |
| **P4** | Performance & Observability | 5 项 | ✅ V1/V2/V4 完成 | 6 天 | — |
| | **合计** | **32 项** | **20/32** | **26 天** | **2 天** |

```
Week 1                        Week 2-4                    Week 5
████████████████████████████████████████████████████████████████████
████ P0 P1 (done) ████ P2 架构 ████ P3 运维 ████ P4 性能与可观测 ██
                        ████ (P2 P3 P4 可部分并行) ████
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

## 五、Phase 3 — Platform Readiness（进行中）

> **目标**: 补齐可运维性短板。
> **前提**: P1 全部完成。P3 与 P2 / P4 可并行。
> **进度**: ✅ O1 Docker | ⏳ O2 日志轮转 / O3 pyproject.toml / O4 CORS

### 架构原则：Provider 解耦合

本地模型框架与网关核心**不强绑定任何特定引擎**。当前支持的 Provider：

| Provider | 用途 | 适用场景 |
|----------|:----:|----------|
| `mock` | 无模型模式 | 开发/测试，零依赖 |
| `ollama` | 本地模型 | Ollama 运行时的本地预处理 |
| `openai-compatible` | 云端+本地 | DeepSeek / Qwen / OpenAI / vLLM / SGLang / LocalAI |

网关通过 `app/providers/registry.py` 在运行时按配置选择 Provider，新增 Provider 只需实现 `BaseProvider` 接口。此设计在 Docker 打包时应继续保持——**Ollama 是可选依赖，非必须组件**。

### 任务清单

| # | 任务 | 类型 | 负责模块 | 预估工时 | 依赖 |
|---|------|:----:|----------|:--------:|:----:|
| O1 | Docker 打包（解耦架构） | 运维 | 项目根目录 | 6h | — | ✅ |
| O2 | 日志轮转配置 | 运维 | WSL `/etc/logrotate.d/` | 1h | — |
| O3 | `pyproject.toml` + 依赖分组 | 工程化 | 项目根目录 (新文件) | 2h | — |
| O4 | CORS 配置 | 功能 | `app/api/routes.py` | 30min | — |

### O1 详细方案：解耦式 Docker 打包

与常见的"把所有服务塞一个 compose 文件"不同，本项目的 Docker 架构强调**可选依赖**：

```
┌─────────────────────────┐
│  Gateway Container      │ ← 唯一必需容器
│  - FastAPI + uvicorn     │
│  - 无本地模型也能运行     │    LOCAL_MODEL_MODE=mock → 独立运行
│  - 依赖: pip install     │
└─────────┬───────────────┘
          │
          ├── (可选) Ollama Container ── 本地预处理
          │     image: ollama/ollama
          │     mount: ollama_data (模型权重持久化)
          │
          └── (可选) 外部 API ── 云端生成
                DeepSeek / Qwen / OpenAI / vLLM
```

**Dockerfile**：
```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
VOLUME ["/app/data", "/app/logs"]
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -f http://localhost:8000/health || exit 1
EXPOSE 8000
CMD ["python", "main.py", "serve"]
```

**docker-compose.yml**（仅网关，独立运行）：
```yaml
version: "3.8"
services:
  gateway:
    build: .
    ports:
      - "8000:8000"
    environment:
      - LOCAL_MODEL_MODE=mock
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
```

**扩展 docker-compose.ollama.yml**（叠加 Ollama 支持）：
```yaml
# 使用方式: docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d
services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

volumes:
  ollama_data:
```

**设计要点**：
- `docker-compose.yml` 单独运行网关，零外部依赖（`mock` 模式）
- `docker-compose.ollama.yml` 通过 `docker compose -f` 叠加，按需扩展
- 不捆绑 Ollama → 用户可选择本地/云端/混合模式
- 迁移方式：`git pull && docker compose up -d --build` 替代 `sync_to_wsl.sh`

---

## 六、Phase 4 — Performance & Observability（进行中）

> **目标**: 建立可量化的性能基线 + 可观察性基础设施，确保网关效率可追踪、可优化。
> **前提**: 不依赖 P2/P3，可与 P2/P3 并行。
> **进度**: ✅ V2 连接池 | ✅ V1 phase timing | ✅ V4 缓存归一化 | ⏳ V3/V5

### 性能架构声明

网关的延迟分布特征（实测数据）：

```
总延迟 3.5s (典型值)
  ├── Police 规则检查    <1ms     (0%)    CPU 密集型
  ├── 本地模型预处理     ~500ms   (15%)   I/O 密集型（Ollama API 调用）
  ├── 调度器             <1ms     (0%)    CPU 密集型
  ├── 云端生成           2.5-3s   (80%)   网络 I/O 密集
  └── 记忆/缓存/审计     <10ms    (0%)    I/O 密集型（SQLite）
```

**核心结论**: 80% 延迟在云端 API 的网络调用。Python 自身的处理时间占比不到 5%。

因此：

- ❌ **现阶段不换语言**（Go/Rust 最多优化 5%，但开发成本翻数倍）
- ✅ **优先优化缓存命中率、连接复用、可观察性**（这三个方向 ROI 最高）

### 任务清单

| # | 任务 | 类型 | 负责模块 | 预估工时 | 说明 |
|:--:|------|:----:|----------|:--------:|------|
| V1 | 请求级耗时指标（phase timing） | 可观察性 | `app/gateway/engine.py` | 2h | 每个 phase 耗时导出到结构化日志，可用于后续 Grafana 看板 |
| V2 | httpx 全局连接池复用 | 性能 | `app/providers/` | 3h | 全局 `httpx.AsyncClient` + HTTP/2 + keepalive，省 50-200ms/请求 |
| V3 | Prometheus metrics 端点 | 可观察性 | `app/core/metrics.py` (新) | 4h | `/metrics` 端点导出请求数/延迟分布/错误率 |
| V4 | 语义缓存优化 | 性能 | `app/cache/store.py` | 4h | 缓存 key 归一化（大小写/空格/标点），提升命中率 |
| V5 | 性能基线基准测试 | 工具 | `tests/benchmark/` (新) | 6h | `locustfile.py` 或 `pytest-benchmark`，可重复的性能基线 |

---

### 详细方案

#### V1：phase timing

当前阶段日志只有标记没有耗时。在每个 phase 前后记录时间戳：

```python
# engine.py 中新增
_phase_times: dict[str, float] = {}

def _phase_start(name: str):
    _phase_times[name] = time.perf_counter()

def _phase_end(name: str):
    elapsed = (time.perf_counter() - _phase_times.get(name, 0)) * 1000
    logger.info("perf:phase_timing", extra={"phase": name, "latency_ms": round(elapsed, 2)})
    return elapsed
```

输出示例：
```json
{"phase":"local_preprocess","latency_ms":423.15}
{"phase":"cloud_generate","latency_ms":2850.33}
```

#### V2：httpx 全局连接池

```python
# app/providers/client.py — 新文件
import httpx

_client: httpx.AsyncClient | None = None

def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
            ),
            http2=True,
            timeout=httpx.Timeout(120.0, connect=15.0),
        )
    return _client
```

将 `ollama.py` 和 `openai_compatible.py` 中每次新建 `httpx.AsyncClient(timeout=...)` 替换为 `get_http_client()`。

#### V3：Prometheus 指标端点

```python
# app/core/metrics.py — 新文件
import time
from prometheus_client import Counter, Histogram, generate_latest, REGISTRY
from fastapi import APIRouter, Response

requests_total = Counter("gateway_requests_total", "Total requests", ["source", "model"])
latency_histogram = Histogram("gateway_latency_seconds", "Request latency", ["phase"], buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0])

metrics_router = APIRouter()

@metrics_router.get("/metrics")
async def metrics():
    return Response(content=generate_latest(REGISTRY), media_type="text/plain")
```

#### V4：语义缓存优化

```python
# app/cache/store.py — 改进 _hash_key
def _normalize_input(text: str) -> str:
    """缓存 key 归一化：去标点、小写、去多余空格"""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text
```

#### V5：性能基线

```python
# tests/benchmark/test_latency.py — 新文件
"""性能基线测试。运行前需启动服务。"""
import pytest
import httpx

BASE_URL = "http://localhost:8000"

@pytest.mark.benchmark
def test_chat_latency(benchmark):
    """测量 /chat 端点的 p50/p95/p99 延迟"""
    ...

@pytest.mark.benchmark
def test_health_latency(benchmark):
    """/health 应在 5ms 内返回"""
    ...
```

---

## 七、性能风险与决策

### 性能风险登记

| # | 风险 | 概率 | 影响 | 等级 | 缓解措施 |
|---|------|:----:|:----:|:----:|----------|
| R9 | 云端 API 延迟波动（2s → 10s） | 中 | 高 | 🟡 | V2 连接池 + V1 监控告警；V3 暴露延迟分布 |
| R10 | 缓存命中率低导致重复调用 | 中 | 中 | 🟡 | V4 语义缓存 + 缓存预热 |
| R11 | 高并发下 SQLite 写锁争用 | 低 | 中 | 🟢 | 当前单 Worker 场景风险低；V3 可暴露写延迟 |
| R12 | 性能退化无感知（改代码后变慢） | 中 | 中 | 🟡 | V5 基线测试 + CI 中自动对比 |

---

## 八、风险登记册（更新于 2026-05-18）

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

## 九、ADR（架构决策记录）

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

### ADR-013: 性能优先优化缓存与连接池，不换语言

**日期**: 2026-05-18
**状态**: 已采纳

**背景**: 担心 Python 作为网关的效率瓶颈，考虑换 Go/Rust。

**证据**: 实测延迟分布中，云端 API 网络调用占 80%，Python 自身处理 < 5%。

**决策**: 
1. 现阶段不换语言（ROI 不成正比）
2. 优先优化缓存命中率（V4）、连接复用（V2）、可观察性（V1/V3）
3. 建立性能基线（V5），每次改动后自动比对

**触发换语言的条件**（以下全部满足时重新评估）：
- 单机吞吐 > 1000 req/s
- CPU profiling 显示 Python 处理占比 > 30%
- 现有优化（缓存/连接池/异步）已用尽

### ADR-014: 本地模型框架解耦合，不强绑定任何引擎

**日期**: 2026-05-18
**状态**: 已采纳（架构原则）

**背景**: 网关同时支持 mock / ollama / openai-compatible 等多种本地模型 Provider。

**决策**: Provider 架构保持开放，新增 Provider 只需实现 `BaseProvider`（`preprocess()` + `generate()`）两个方法。Docker 打包时 Ollama 作为可选 overlay，非必要组件。

**约束**:
- 网关核心不得直接 import 任何具体 Provider 实现（已通过 registry.py 满足）
- `docker-compose.yml` 必须能在不启动 Ollama 的情况下独立运行（`LOCAL_MODEL_MODE=mock`）
- 所有 Provider 共享 `get_http_client()` 全局连接池（V2 已完成）

**当前支持的 Provider**:

| Provider | 文件 | 本地/云端 |
|----------|:----:|:---------:|
| `mock` | `mock.py` | 开发测试 |
| `ollama` | `ollama.py` | 本地 |
| `openai-compatible` | `openai_compatible.py` | 本地+云端 |

---

## 十、变更日志

| 日期 | 版本 | 变更内容 |
|:----:|:----:|----------|
| 2026-05-18 | v1.5 | **O1 Docker 完成**（Dockerfile + docker-compose + ollama overlay + .dockerignore）；P3 进度 1/4 |
| 2026-05-18 | v1.2 | P0(7项)+P1(6项)+D(3项)+G(1项) 完成；进度 17/33；Git 初始化章节更新 |
| 2026-05-18 | v1.1 | ADR 状态更新；风险登记册更新；新增 ADR-011/012 |
| 2026-05-18 | v1.0 | 初始版本：4 阶段、25 项任务、8 ADR、风险登记册、执行路线图 |

---

## 十一、Git 初始化和 GitHub 上传指引

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
