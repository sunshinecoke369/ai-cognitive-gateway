"""
Prometheus 指标端点

暴露网关运行时指标供 Prometheus + Grafana 采集。
配合 V1 phase timing 日志实现延迟可视化。

端点：GET /metrics（Prometheus 文本格式）
"""

from fastapi import APIRouter, Response

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY

    # ── 请求计数 ──
    requests_total = Counter(
        "gateway_requests_total",
        "Total requests processed",
        ["source", "model", "status"],
    )

    # ── 各阶段延迟（秒） ──
    latency_histogram = Histogram(
        "gateway_latency_seconds",
        "Request latency by phase",
        ["phase"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )

    # ── 并发请求数 ──
    in_flight_gauge = Gauge(
        "gateway_requests_in_flight",
        "Concurrent requests currently processing",
    )

    # ── 缓存 ──
    cache_hits = Counter(
        "gateway_cache_hits_total",
        "Total cache hits",
    )

    # ── 治理拦截 ──
    governance_blocked = Counter(
        "gateway_governance_blocked_total",
        "Total requests blocked by governance",
        ["reason"],
    )

    HAS_PROMETHEUS = True

except ImportError:
    HAS_PROMETHEUS = False


metrics_router = APIRouter(tags=["metrics"])


@metrics_router.get("/metrics")
async def metrics():
    """Prometheus 指标端点（文本格式）。"""
    if not HAS_PROMETHEUS:
        return Response(
            content="# prometheus_client not installed\n",
            media_type="text/plain; version=0.0.4",
        )
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain; version=0.0.4",
    )
