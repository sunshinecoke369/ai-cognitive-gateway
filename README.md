# AI Cognitive Gateway

AI 认知网关操作系统 — 位于用户、Agent、IDE、云端模型之间的统一控制中枢。

> **工程化状态**: P0 Quick Wins ✅ | P1 Foundation Hardening ✅ | [完整路线图](docs/engineering-roadmap.md)
> **测试**: 95 用例全部通过 | **版本**: v1.2.1 | [变更日志](CHANGELOG.md)

---

## 核心能力

- **本地预处理** — Ollama 本地模型提取意图、风险、摘要，故障自动降级
- **安全治理** — Police（正则）→ Judge（三级裁决）→ 语义检测（可选）三层防线
- **多模型调度** — 按意图/语言/标签/权重自动选择最佳云端模型，故障降级链
- **全链路审计** — 不可变 JSONL + SQLite 双写审计日志
- **请求缓存** — 相同输入直接命中缓存，减少 Token 消耗
- **反馈闭环** — 用户 👍/👎 评价自动调整记忆权重
- **多模态支持** — `image_url` 自动路由到视觉模型
- **流式响应** — 真 SSE 逐 Token 推送
- **FIM 补全** — `/v1/completions` Fill-In-the-Middle 代码补全

---

## 目录

- [快速开始](#快速开始)
- [开发工作流](#开发工作流)
- [生产部署](#生产部署)
- [安全配置](#安全配置)
- [IDE 接入](#ide-接入)
- [管理控制台](#管理控制台)
- [多模型配置](#多模型配置)
- [CLI 命令](#cli-命令)
- [API 端点](#api-端点)
- [文档索引](#文档索引)
- [测试](#测试)
- [故障排查](#故障排查)

---

## 快速开始

### 1. 环境要求

- Python 3.11+
- (可选) Ollama 用于本地模型预处理
- (可选) 至少一个 OpenAI 兼容 API 端点（DeepSeek、阿里云百炼、OpenAI）

### 2. 安装

```bash
git clone https://github.com/your-org/ai-cognitive-gateway.git
cd ai-cognitive-gateway

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 3. 最小配置

```bash
# 默认 Mock 模式，无需本地模型和云端 API 即可运行
cp .env.example .env
python main.py serve
```

验证：`curl http://localhost:8000/v1/models`

### 4. 接入真实模型

通过管理控制台（推荐）或编辑 `data/gateway_config.yaml` 配置：

```yaml
local:
  provider: ollama
  api_url: http://192.168.1.13:11434
  default_model: gemma4:e4b
  timeout_seconds: 90
  max_tokens: 2048
  keep_alive: -1

cloud:
  default: deepseek-v4-flash
  models:
    deepseek-v4-flash:
      provider: openai-compatible
      api_url: https://api.deepseek.com
      api_key: sk-your-deepseek-key
      timeout_seconds: 120
      weight: 5
      tags: [fast, cheap, coding]
      enabled: true
```

---

## 开发工作流

本项目使用 **双机双份** 工作流：

```
L:\AI Cognitive Operating System\ai-cognitive-gateway\    ← 源码真实来源（SSOT）
                │
                │  bash sync_to_wsl.sh  (手动触发)
                ▼
WSL /root/ai-cognitive-gateway/                           ← 运行环境（systemd 服务）
```

每次代码改动后：

```bash
cd /root/ai-cognitive-gateway
bash sync_to_wsl.sh
sudo systemctl restart ai-gateway
curl http://localhost:8000/health          # 健康检查
```

`data/` 和 `logs/` 目录被自动排除在同步之外，控制台配置不会丢失。

---

## 生产部署

### Systemd 服务（Linux / WSL）

```ini
# /etc/systemd/system/ai-gateway.service
[Unit]
Description=AI Cognitive Gateway
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/ai-cognitive-gateway
ExecStart=/root/ai-cognitive-gateway/.venv/bin/python main.py serve
Restart=on-failure
RestartSec=5
StandardOutput=append:/tmp/gateway.log
StandardError=append:/tmp/gateway.log

# 注意：全局状态（Override/Capability/Shutdown）不跨 Worker 共享
# 不支持 uvicorn --workers > 1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-gateway
sudo systemctl start ai-gateway
```

常用命令：

```bash
systemctl status ai-gateway        # 查看状态
sudo systemctl restart ai-gateway  # 重启
journalctl -u ai-gateway -f        # 实时日志
```

### WSL 注意事项

1. **Ollama 通信**：如果 Ollama 运行在 Windows 宿主机，`api_url` 使用宿主机 IP（`ip route | grep default | awk '{print $3}'`）
2. **DNS 问题**：详见 [故障排查 — DNS](#dns-解析失败)
3. **开机自启**：WSL 不随 Windows 自动启动。如需自动启动，在 Windows 任务计划程序中创建启动任务运行 `wsl -d Ubuntu-24.04`

---

## 安全配置

### Admin API 认证

所有 `/admin/*` 端点需要 Bearer Token：

```bash
# 无认证 → 401
curl http://localhost:8000/admin/config

# 带认证 → 200
curl http://localhost:8000/admin/config \
  -H "Authorization: Bearer admin:gw-console-2026"
```

默认密钥 `admin:gw-console-2026`，建议通过环境变量 `ADMIN_API_KEY` 覆盖。

### API Key 安全

API Key 以 SHA256 哈希存储（`data/api_keys.json`），不再保留明文。
生成时只返回一次，管理控制台只显示 Key 前缀。

### 速率限制

| 端点 | 限流策略 |
|------|----------|
| `/chat` | 60 次/分钟/IP |
| `/v1/chat/completions` | 30 次/分钟/API Key |
| `/v1/messages` | 30 次/分钟/API Key |
| `/admin/*` | 10 次/分钟/IP |

所有受限端点返回 `X-RateLimit-Limit` / `X-RateLimit-Remaining` 响应头。

---

## IDE 接入

网关兼容 OpenAI `/v1/chat/completions` 和 Anthropic `/v1/messages` 协议。

### 配置 IDE

在 IDE（Cursor / Trae / VS Code）的模型设置中填写：

| 字段 | 值 |
|------|------|
| **Base URL** | `http://localhost:8000/v1` |
| **API Key** | 从控制台 → API Keys 生成 |
| **Model** | `auto` 或指定的云端模型名 |
| **Provider** | OpenAI / OpenAI Compatible |

### 认证模式

| 端点 | 无 Key | 有 Key |
|------|:---:|:---:|
| `/v1/chat/completions` | **401** | 200 |
| `/v1/messages` | **401** | 200 |
| `/chat` | 200 | 200 |
| `/v1/models` | 200 | 200 |
| `/health` | 200 | 200 |
| `/console` | 200 | 200 |

### 验证

```bash
# OpenAI 协议
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-api-key>" \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello"}]}'

# Anthropic 协议
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-api-key>" \
  -d '{"model":"auto","max_tokens":100,"messages":[{"role":"user","content":"Hello"}]}'
```

---

## 管理控制台

浏览器打开 `http://localhost:8000/console`。

| 选项卡 | 功能 |
|------|------|
| **概览** | 网关信息、IDE 接入配置、运行指标 |
| **本地模型** | 本地模型配置（Provider / URL / 模型名 / 超时） |
| **云端模型** | 多模型管理 — 添加/编辑/删除/启用/禁用/设置默认 |
| **API Keys** | 生成、启用、禁用、删除 API Key |
| **治理规则** | 查看/添加/启用/禁用/删除安全规则 |
| **请求来源** | 24h 客户端请求统计 |
| **缓存管理** | 查看缓存统计，按模型或全部清理 |
| **用户反馈** | 查看 👍/👎 反馈及关联请求 |
| **记忆管理** | 查看/搜索/清理本地模型生成的记忆条目 |
| **审计日志** | 按事件类型筛选审计记录 |

---

## 多模型配置

### 调度策略

本地模型预处理后，`scheduler.py` 按以下优先级选择云端模型：

1. **视觉路由** — `has_images` → `tags: [vision]` 的模型 +10 分
2. **意图匹配** — `intent: code` → `tags: [coding]` 的模型 +5 分
3. **语言匹配** — `language: zh` → `tags: [chinese]` 的模型 +4 分
4. **权重加成** — 基础分 = 配置的 `weight` 值
5. **故障降级** — 当前模型超时/报错 → 自动尝试排名次优的模型

### 通过 API 管理

```bash
# 列出所有模型
curl http://localhost:8000/admin/config/cloud/models \
  -H "Authorization: Bearer admin:gw-console-2026"

# 添加模型
curl -X POST http://localhost:8000/admin/config/cloud/models \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer admin:gw-console-2026" \
  -d '{"name":"deepseek-v4-flash","provider":"openai-compatible","api_url":"https://api.deepseek.com","api_key":"sk-...","weight":5,"tags":["fast","coding"]}'

# 设置默认
curl -X POST "http://localhost:8000/admin/config/cloud/default?name=qwen-plus" \
  -H "Authorization: Bearer admin:gw-console-2026"
```

---

## CLI 命令

```bash
python main.py serve              # 启动 API 服务
python main.py history            # 查看请求历史
python main.py history --id xxx   # 查看指定请求详情
python main.py history --limit 50 # 最近 50 条
python main.py memory             # 查看记忆条目
python main.py memory --limit 20  # 最近 20 条
python main.py rules              # 查看治理规则
python main.py token              # 查看 Token 用量统计
```

---

## API 端点

### 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | **服务健康检查**（数据库+模型+运行时状态） |

### 核心 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 核心请求入口（无 Key 宽松模式） |
| GET | `/history` | 请求历史 |
| GET | `/history/{id}` | 请求详情 |
| GET | `/memory` | 记忆列表 |
| GET | `/memory/context` | 记忆上下文摘要 |
| POST | `/memory/compress` | 清理低价值记忆（threshold 参数） |

### OpenAI / Anthropic 兼容

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/chat/completions` | OpenAI 协议（需 API Key） |
| POST | `/v1/messages` | Anthropic 协议（需 API Key） |
| POST | `/v1/completions` | FIM 代码补全（需 API Key） |
| GET | `/v1/models` | 模型列表（含能力标签） |

### 治理 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/governance/rules` | 治理规则列表 |
| POST | `/governance/rules` | 添加规则 |
| PUT | `/governance/rules/{id}/toggle` | 启用/禁用规则 |
| GET | `/token-usage` | Token 用量统计 |
| POST | `/v1/feedback` | 提交 👍/👎 反馈 |

### 管理 API（需 Admin 认证）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/overview` | 网关运行概览 |
| GET | `/admin/config` | 完整配置（密钥脱敏） |
| POST | `/admin/config/local` | 更新本地模型配置 |
| GET | `/admin/config/cloud/models` | 云端模型列表 |
| POST | `/admin/config/cloud/models` | 添加云端模型 |
| PUT | `/admin/config/cloud/models/{name}` | 更新云端模型 |
| DELETE | `/admin/config/cloud/models/{name}` | 删除云端模型 |
| POST | `/admin/config/cloud/default` | 设置默认模型 |
| POST | `/admin/config/reload` | 热加载配置 |
| GET | `/admin/api-keys` | API Key 列表 |
| POST | `/admin/api-keys` | 生成 Key |
| GET | `/admin/clients` | 请求来源统计 |
| GET | `/admin/override` | Human Override 状态 |
| POST | `/admin/override/activate` | 激活 Override |
| POST | `/admin/override/deactivate` | 关闭 Override |
| POST | `/admin/shutdown` | 暂停新请求 |
| GET | `/admin/capabilities` | Capability 列表 |
| POST | `/admin/capabilities/grant` | 授予 Capability |
| GET | `/admin/rules` | 治理规则（管理用） |
| DELETE | `/admin/rules/{rule_id}` | 删除规则 |
| GET | `/admin/cache/stats` | 缓存统计 |
| GET | `/admin/token-trend` | Token 趋势 |
| GET | `/admin/feedback` | 用户反馈列表 |
| GET | `/audit` | 审计日志 |

---

## 文档索引

| 文档 | 说明 |
|------|------|
| [工程化路线图](docs/engineering-roadmap.md) | 阶段计划、任务清单、ADR、风险登记册 |
| [项目管理](docs/project-management.md) | 里程碑、仪表盘、变更日志 |
| [变更日志](CHANGELOG.md) | 版本历史 |
| [AI Gateway Doctrine](../AI%20Cognitive%20Gateway%20Doctrine.md) | 核心架构原则（站外） |
| [项目规划](../ai_cognitive_gateway_os_项目规划.md) | 长期规划（站外） |

---

## 测试

```bash
cd ~/ai-cognitive-gateway
.venv/bin/python -m pytest tests/test_api.py -q
```

当前覆盖：**95 用例**，涵盖聊天 API、模型选择、认证边界、治理规则、
API Key CRUD、配置管理（多模型）、调度器、审计日志、流式响应、多模态。

---

## 故障排查

### DNS 解析失败（WSL）

WSL2 的 `/etc/resolv.conf` 在重启后会被覆盖，导致域名无法解析：

```bash
# 1. 阻止自动生成
sudo bash -c 'cat > /etc/wsl.conf << EOF
[boot]
systemd=true

[network]
generateResolvConf = false
EOF'

# 2. 手动设置 DNS
sudo rm /etc/resolv.conf
sudo bash -c 'echo "nameserver 114.114.114.114" > /etc/resolv.conf'
sudo bash -c 'echo "nameserver 8.8.8.8" >> /etc/resolv.conf'
sudo chattr +i /etc/resolv.conf

# 3. 重启 WSL（在 Windows PowerShell 中）
# wsl --shutdown
# wsl -d Ubuntu-24.04
```

### 请求失败

1. 检查阶段日志：`grep phase /tmp/gateway.log | tail -10`
2. 检查错误类型：日志区分 `[TIMEOUT]` / `[CONNECTION_FAILED]` / `[HTTP_ERROR]`
3. 检查服务状态：`curl http://localhost:8000/health`
4. 检查 DNS：`ping api.deepseek.com`

### 本地模型变慢

已自动修复。网关每次 Ollama 请求携带 `"keep_alive": -1`，模型永不被卸载。

### 检查服务状态

```bash
systemctl status ai-gateway
tail -20 /tmp/gateway.log
curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health
```
