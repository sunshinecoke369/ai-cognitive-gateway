FROM python:3.12-slim

LABEL org.opencontainers.image.title="AI Cognitive Gateway"
LABEL org.opencontainers.image.description="Unified Control Plane for LLM Requests"
LABEL org.opencontainers.image.version="1.3.3"

WORKDIR /app

# 系统依赖（仅 healthcheck 需要 curl）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY . .

# 运行时数据卷
VOLUME ["/app/data", "/app/logs"]

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["python", "main.py", "serve"]
