"""
延迟断言测试 — 作为 pytest 套件的一部分运行。

这些测试验证关键端点的响应时间在预期范围内。
与 tests/benchmark/run.py（统计基准）互补。

使用方法:
  # 启动服务后:
  python -m pytest tests/benchmark/test_latency.py -v
"""

import time
from httpx import AsyncClient, ASGITransport
import pytest


# 各端点延迟上限（毫秒），超出即视为回归
LATENCY_THRESHOLDS_MS = {
    "/health": 20,           # 健康检查应极快
    "/v1/models": 20,        # 模型列表缓存
    "/metrics": 100,         # Prometheus 指标
    "/chat_mock": 1000,      # mock 模式的聊天请求
    "/memory": 50,           # 记忆列表
}


@pytest.mark.asyncio
async def test_health_latency(setup_test_db):
    """/health 应在 20ms 内返回。"""
    from app.api.routes import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        t0 = time.perf_counter()
        resp = await client.get("/health")
        elapsed = (time.perf_counter() - t0) * 1000
        assert resp.status_code == 200
        assert elapsed < LATENCY_THRESHOLDS_MS["/health"], (
            f"/health took {elapsed:.1f}ms, threshold {LATENCY_THRESHOLDS_MS['/health']}ms"
        )


@pytest.mark.asyncio
async def test_v1_models_latency(setup_test_db):
    """/v1/models 应在 20ms 内返回。"""
    from app.api.routes import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        t0 = time.perf_counter()
        resp = await client.get("/v1/models")
        elapsed = (time.perf_counter() - t0) * 1000
        assert resp.status_code == 200
        assert elapsed < LATENCY_THRESHOLDS_MS["/v1/models"], (
            f"/v1/models took {elapsed:.1f}ms, threshold {LATENCY_THRESHOLDS_MS['/v1/models']}ms"
        )


@pytest.mark.asyncio
async def test_metrics_latency(setup_test_db):
    """/metrics 应在 100ms 内返回。"""
    from app.api.routes import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        t0 = time.perf_counter()
        resp = await client.get("/metrics")
        elapsed = (time.perf_counter() - t0) * 1000
        assert resp.status_code == 200
        assert elapsed < LATENCY_THRESHOLDS_MS["/metrics"], (
            f"/metrics took {elapsed:.1f}ms, threshold {LATENCY_THRESHOLDS_MS['/metrics']}ms"
        )
