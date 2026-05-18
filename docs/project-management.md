# AI Cognitive Gateway — 项目管理文档

> **文档版本**: v2.1
> **最后更新**: 2026-05-15
> **维护者**: 项目负责人
> **发布建议**: 上传 GitHub 前移除所有 `[INTERNAL]` 标记项

---

## 一、项目仪表盘（Dashboard）

| 指标 | 当前值 |
|------|--------|
| **当前阶段** | 工程化 P0/P1 完成，P2 待开始 |
| **总体进度** | **100%** (MVP+Phase2+Phase3) + **100%** (P0+P1) |
| **最近里程碑完成** | 2026-05-18 — P1 Foundation Hardening 完成 |
| **下一里程碑目标** | P2 Architecture Evolution / P3 Platform Readiness |

### 当前关键风险（≤3 个）

| # | 风险 | 等级 | 缓解措施 |
|---|------|:---:|------|
| R1 | 8GB 显存限制本地模型只能运行 ≤4B 参数量化模型 | 🟡 中 | gemma4:e4b（4B）已验证可行；更大模型需云端兜底 |
| R2 | 无 | — | — |
| R3 | 无 | — | — |

---

## 二、里程碑与路线图

### MVP 阶段里程碑

#### M1 — 基础网关可运行 ✅

| 项目 | 内容 |
|------|------|
| **目标** | 单通道请求 → 本地预处理 → 治理检测 → 云端生成 → 返回 |
| **验证标准** | `POST /chat` 返回完整 GatewayResponse；Police 规则命中时拦截 |
| **完成日期** | 2026-05-10 |
| **产出** | `engine.py`, `governance/`, `providers/`, `memory/`, `audit.py`, `database.py` |

#### M2 — 管理控制台完成 ✅

| 项目 | 内容 |
|------|------|
| **目标** | Web 控制台：概览仪表盘、模型配置、API Key 管理、治理规则、请求来源统计 |
| **验证标准** | `/console` 8 个一级选项卡全部可达；Key 生成/禁用/删除可用；配置保存即时生效 |
| **完成日期** | 2026-05-11 |
| **产出** | `admin/router.py`, `admin/config_manager.py`, `admin/api_keys.py`, `admin/static/index.html` |

#### M3 — 本地模型集成验证 + 多模型调度 ✅

| 项目 | 内容 |
|------|------|
| **目标** | 验证 Ollama 本地模型端到端稳定性；激活记忆/审计 UI；实现云端多模型意图调度 |
| **验证标准** | 冒烟测试全端点 200；`/v1/*` 无 Key → 401；记忆/审计 UI 可交互；多模型 YAML 结构生效 |
| **完成日期** | 2026-05-12 |
| **产出** | 记忆管理 UI、审计日志 UI、`scheduler.py`（意图路由+标签匹配+权重评分）、`config_manager.py` 多模型读写、控制台多模型增删 UI、`/memory/compress` 端点、`/config/cloud/models` CRUD 端点 |

#### M4 — 质量加固与发布就绪 ✅

| 项目 | 内容 |
|------|------|
| **目标** | 测试覆盖从 81 → 95；YAML schema 校验；allowed_models 自动同步；概览页一键复制；调度器故障降级链；Ollama keep_alive 移植性配置；云端模型编辑 UI；增强错误日志 |
| **验证标准** | 95 用例全部通过；非法配置写入友好报错；控制台每个模型行有编辑/禁用/删除按钮 |
| **完成日期** | 2026-05-12 |
| **产出** | 95 测试用例；`_validate_cloud_models()`；`_sync_allowed_models()`；`📋` 复制按钮；`get_fallback_chain()` + engine 遍历链；`keep_alive: -1` + ollama.py 传参；编辑模式 UI；`ConnectError` 日志分离 |

---

## Phase 2 — 增强 ✅

#### B — `/v1/models` 模型能力标签 ✅

| 项目 | 内容 |
|------|------|
| **目标** | `/v1/models` 返回 `capabilities: {streaming, vision, tool_calling, reasoning}`，IDE 据此过滤模型列表 |
| **完成日期** | 2026-05-13 |
| **产出** | `openai_compat.py` — `_model_capabilities()` 自动识别多模态/推理模型 |

#### C — 治理规则热管理 ✅

| 项目 | 内容 |
|------|------|
| **目标** | 控制台可直接添加/启用/禁用/删除 Police 规则，替换只读表格 |
| **完成日期** | 2026-05-13 |
| **产出** | `governance/engine.py` — `delete_rule()`；`admin/router.py` — POST/PUT/DELETE `/admin/rules`；UI — 添加表单 + 禁用/删除按钮 |

#### D — Token 趋势图表 ✅

| 项目 | 内容 |
|------|------|
| **目标** | 概览仪表盘近 24h Token 用量柱状图 |
| **完成日期** | 2026-05-13 |
| **产出** | `/admin/token-trend?hours=24` 按小时聚合端点；概览页 `token-chart` 柱状图 (hover 数值) |

---

## Phase 3 — 功能增强 ✅

#### F — `/v1/completions` 代码补全 FIM 端点 ✅

| 项目 | 内容 |
|------|------|
| **目标** | 支持 IDE 代码补全的 `/v1/completions` 端点，实现 Fill-In-the-Middle (FIM) |
| **完成日期** | 2026-05-15 |
| **产出** | `openai_compat.py` — `CompletionRequest`, `_build_fim_prompt()`, `_call_cloud_completion()`, `/v1/completions` 端点；`/v1/models` capabilitie 新增 `fim: true` |

#### H — 请求缓存层 ✅

| 项目 | 内容 |
|------|------|
| **目标** | 相同输入命中缓存直接返回，减少云端 Token 消耗 |
| **完成日期** | 2026-05-15 |
| **产出** | `app/cache/store.py` — `cache_get/set/invalidate/stats/cleanup`；`database.py` — `response_cache` 表；`engine.py` — 请求前查缓存 + 请求后写缓存；控制台「缓存管理」选项卡；`/admin/cache/*` 端点 |

#### J — 反馈闭环 ✅

| 项目 | 内容 |
|------|------|
| **目标** | 用户评价回答 👍/👎，自动调整记忆权重，形成强化学习闭环 |
| **完成日期** | 2026-05-15 |
| **产出** | `app/feedback/store.py` — `save_feedback/get_feedback*/get_feedback_stats`；`database.py` — `feedback` 表；`/v1/feedback` 端点；控制台「用户反馈」选项卡；`/admin/feedback/*` 端点；好评+0.1 / 差评-0.1 记忆 Importance 调整 |

#### I — 流式响应优化 ✅

| 项目 | 内容 |
|------|------|
| **目标** | 真 SSE 流式逐 Token 推送，替代伪流式（一次返回后拆分） |
| **完成日期** | 2026-05-15 |
| **产出** | `openai_compatible.py` — `generate_stream()` 使用 `httpx.stream` + `aiter_lines()` 逐行解析上游 SSE；`base.py` — `generate_stream()` 默认回退（逐字符）；`engine.py` — `process_request_stream()` 异步生成器（治理 → 本地预处理 → 云端流式 → 后处理）；`openai_compat.py` — `_openai_stream_wrapper`（OpenAI SSE 格式）+ `_anthropic_stream_wrapper`（Anthropic SSE 格式）；15 用例全部通过 |

#### G — 多模态请求支持 ✅

| 项目 | 内容 |
|------|------|
| **目标** | `/v1/chat/completions` 接受 `image_url`，自动路由到视觉模型，转发到 Gemini/GPT-4o 等 |
| **完成日期** | 2026-05-15 |
| **产出** | `base.py` — `extract_text_from_messages` 支持 array content + `has_images_in_messages`；`scheduler.py` — 视觉路由（has_images → vision tag +10/-5）；`engine.py` — 传递 messages 给 scheduler；`openai_compat.py` — `/v1/chat/completions`+`/v1/messages` 自动视觉路由 + `normalize_messages_for_model` 改用 `_model_capabilities` 判定 + `/v1/models` 本地模型视觉标签；24 用例全部通过 |

---

## 三、当前迭代任务清单

### ✅ 全部完成

| # | 任务 | 状态 |
|---|------|:---:|
| T1 | DNS 稳定化（WSL 宿主机重启修复） | ✅ |
| T2 | `README.md` 完善部署指引 (394 行) | ✅ |
| T3 | IDE 全链路连通验证 | ✅ |
| T6 | `/v1/models` 返回模型能力标签 | ✅ |
| T7 | Dashboard Token 用量图表 | ✅ |
| T8 | 治理规则控制台添加/编辑/禁用 | ✅ |
| T9 | `/v1/completions` FIM 代码补全端点 | ✅ |
| T10 | 请求缓存层 (cache_get/set/invalidate) | ✅ |
| T11 | 反馈闭环 (👍/👎 + 记忆权重调整) | ✅ |
| T12 | 控制台「缓存管理」「用户反馈」选项卡 | ✅ |
| T13 | 新功能 9 用例测试通过 | ✅ |
| T14 | 真流式 SSE 逐 Token 推送 | ✅ |
| T15 | 流式响应 15 用例全部通过 | ✅ |
| T16 | 多模态请求 image_url 支持 | ✅ |
| T17 | 自动视觉模型路由 | ✅ |
| T18 | 多模态 24 用例全部通过 | ✅ |

---

## 四、下一步计划

### 当前状态

| 项 | 状态 |
|------|:---:|
| 全部 MVP 里程碑 (M1-M4) | ✅ |
| Phase 2 增强 (B/C/D) | ✅ |
| 95 测试用例 | ✅ |
| README 部署文档 (394 行) | ✅ |
| DNS 稳定化 | ✅ 宿主机重启修复 |
| IDE 连通验证 | ✅ |

### 发布就绪标准 ✅ 全部达标

1. ~~DNS 修复~~ ✅ `api.deepseek.com` 持续可达
2. ~~IDE 验证~~ ✅ `/v1/chat/completions` 200 OK + 正常回答
3. `mvp-done` tag → Git（等待执行）

### Phase 3 候选方向

| # | 方向 | 说明 | 工作量 |
|---|------|------|:---:|
| **A** | 本地模型替换 | qwen2.5/llama3.2 替代 gemma4 提升中文意图识别准确度 | 中 |
| **E** | Docker 打包 | `Dockerfile` + `docker-compose.yml` 一键部署，彻底解决 WSL 环境问题 | 中 |
| **F** | 代码补全 FIM endpoint | `/v1/completions` (fill-in-the-middle) 支持 IDE 代码补全 | 中 |
| **G** | 多模态请求支持 | `/v1/chat/completions` 接受 `image_url` → 转发到 Gemini/GPT-4o | 小 |
| **H** | 请求缓存层 | 相同输入返回缓存结果，减少云端 Token 消耗 | 中 |
| **I** | 流式响应优化 | SSE 逐 Token 推送替代当前伪流式（一次返回后拆分） | 大 |
| **J** | 反馈闭环 | 用户对回答的 👍/👎 反馈 + 记忆权重调整 | 小 |

---

## 五、技术决策记录（ADR）

### ADR-001: MVP 不使用 RAG / 多 Agent 编排

**日期**: 2026-05  
**状态**: 已采纳  
**背景**: MVP 目标为验证"本地预处理 + 治理 + 云端生成"的网关范式，RAG 和多 Agent 编排属于上层编排能力。  
**决策**: MVP 阶段 Pipeline 固定为单通道线性编排（Local → Police → Judge → Memory → Cloud）。  
**后果**: 
- 优势：实现简单，出问题易定位
- 代价：无法支持多步推理或工具调用；Phase 2 需重构 Pipeline 为有向图

### ADR-002: 管理控制台治理规则可交互

**日期**: 2026-05-13  
**状态**: 已采纳（Phase 2 更新）  
**背景**: MVP 阶段规则只读展示，Phase 2 增加控制台交互。  
**决策**: 控制台"治理规则"选项卡增加添加/启用/禁用/删除按钮；后端增加 `POST/PUT/DELETE /admin/rules` 端点；规则变更即时生效。  
**后果**: 管理员无需直接操作 API，控制台即可完成规则全生命周期管理。

### ADR-003: 本地模型输出必须做降级校验

**日期**: 2026-05-10  
**状态**: 已采纳  
**背景**: Ollama 模型（gemma4:e4b）返回的 JSON 格式不可靠，可能出现字符串代替对象、字段缺失等情况。  
**决策**: 所有 `preprocess()` 返回值在消费前必须通过 `isinstance(xxx_cfg, dict)` 类型守卫；解析失败自动降级为 `degraded=True` 并透传原始输入。  
**后果**: 网关不会因本地模型故障而崩溃；降级后安全检测仍对原始输入生效。

### ADR-004: 配置使用 YAML + 热加载而非纯环境变量

**日期**: 2026-05-10  
**状态**: 已采纳  
**背景**: 环境变量适合简单键值对，但本地/云端模型各有 5+ 个嵌套字段。  
**决策**: 使用 `data/gateway_config.yaml` 存储配置，控制台 API 写入 YAML → `_load_config()` 带文件 mtime 缓存实现热加载。`.env` 仅保留基础字段（host/port/log_level）。  
**后果**: 
- 优势：控制台即时生效，无需重启
- 代价：YAML 写入非原子（但单 writer 场景安全）

### ADR-005: API Key 认证采用分层严格策略

**日期**: 2026-05-11  
**状态**: 已采纳  
**背景**: 需要区分 IDE/Agent 来源用于审计，同时不能破坏旧调用方和控制台使用。  
**决策**: 
- `/v1/chat/completions` + `/v1/messages` → strict=True（无 Key 返回 401）
- `/chat` → 宽松（无 Key 降级 anonymous）
- `/v1/models` `/console` `/admin/*` → 无鉴权
**后果**: IDE 必须配 Key 才能调用；控制台和 `/chat` 测试入口保持可用

### ADR-006: 云端多模型调度采用意图路由 + 标签匹配 + 权重评分

**日期**: 2026-05-12  
**状态**: 已采纳  
**背景**: MVP 阶段只有一个云端模型槽位，无法利用多个模型的不同优势（DeepSeek 便宜但不擅长中文推理，Qwen 中文强，GPT 通用强）。  
**决策**: 
- YAML 结构从 `cloud: {provider, api_url, api_key, default_model}` 改为 `cloud: {default, models: {name: {provider, api_url, api_key, tags, weight, enabled}}}`
- 新增 `scheduler.py`：读 `LocalModelOutput`（意图/语言/风险等级），按标签匹配和权重评分选择最佳模型
- 控制台支持多模型列表管理（添加/删除/启停/默认切换）
**后果**: 
- 优势：可同时配置多个供应商模型；按请求特征自动分流；故障时可手动切到备用模型
- 代价：调度器增加约 5ms 延迟；标签匹配依赖 `LocalModelOutput` 准确度；故障降级链已在 M4 实现

### ADR-007: `/v1/models` 返回模型能力标签

**日期**: 2026-05-13  
**状态**: 已采纳  
**背景**: IDE 需要知道模型是否支持 streaming/vision/tool_calling/reasoning 来正确过滤和展示模型列表。  
**决策**: `/v1/models` 每个模型增加 `capabilities` 字段；云端模型按名称关键词自动识别（`gpt-4o`→vision，`deepseek-reasoner`→reasoning）；本地模型统一标记 `tool_calling: false`。  
**后果**: IDE 模型选择器可正确区分多模态/推理模型与普通文本模型。

---

## 六、风险与等待项

### 当前已知风险

| 风险 | 概率 | 影响 | 状态 |
|------|:---:|------|:---:|
| gemma4:e4b 中文意图识别准确度不足 | 中 | 低 | 监控中，降级后兜底 |
| WSL DNS 解析丢失 | — | — | ✅ 已解决 — 宿主机 Win10 重启恢复 |
| [INTERNAL] | — | — | — |

### 等待项

| 事项 | 等待内容 | 预期时间 |
|------|----------|----------|
| Qwen 3B 本地模型对比测试 | 拉取并运行 qwen2.5:3b 对比 gemma4:e4b 的延迟/准确度 | M3 阶段 |
| [INTERNAL] | — | — |

---

## 七、变更日志

| 日期 | 版本 | 作者 | 变更内容 |
|------|------|------|----------|
| 2026-05-13 | v2.0 | PM | Phase 2 B/C/D 完成；全部任务清空 (100%)；ADR-002 更新为规则可交互；ADR-007 新增模型能力标签；Phase 3 10 候选方向；DNS 风险关闭；Dashboard 100% |
| 2026-05-12 | v1.3 | PM | T2 README 完成 (394 行)；新增下一步计划 + Phase 2 方向；重编号章节 |
| 2026-05-12 | v1.2 | PM | M4 完成；Dashboard 更新至 98%；任务清单刷新为剩余 3 项；风险更新为 WSL DNS |
| 2026-05-18 | v3.0 | ENG | **P0+P1 工程化 13 项全部完成**：/health 端点、阶段日志、sync脚本、gitignore、Key哈希、Admin认证、异常分层、YAML锁、速率限制 |
| 2026-05-12 | v1.1 | PM | M3 完成；新增 M4 里程碑；Dashboard 更新至 95%；任务清单刷新；ADR-006 多模型调度；风险列表更新 |
| 2026-05-11 | v1.0 | PM | 初始版本：Dashboard / 里程碑 / 任务清单 / 5 ADR / 风险与等待项 |

---

> **维护说明**: 本文档通过 AI 辅助生成与维护。每次 `/status` 命令触发自动更新仪表盘。手动更新章节使用 "更新项目管理文档" 指令。
