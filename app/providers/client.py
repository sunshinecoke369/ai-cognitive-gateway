"""
httpx 全局 HTTP 客户端（连接池 + HTTP/2 + keepalive）

使用方式：
  from app.providers.client import get_http_client
  client = get_http_client()
  resp = await client.post(url, json=payload, headers=headers, timeout=30.0)

注意：
- 全局单例，避免每次请求新建连接（省去 DNS 解析 + TCP 握手 + TLS 握手）
- 支持 HTTP/2（多路复用减少延迟）
- keepalive 连接池最多 10 个并发连接
- 超时在每次调用时通过 timeout 参数指定，不绑定客户端
"""

import httpx
from app.core.logging import logger

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
                keepalive_expiry=30.0,
            ),
            http2=True,
            timeout=httpx.Timeout(120.0, connect=15.0),
        )
        logger.info("global httpx client initialized", extra={
            "http2": True,
            "max_connections": 20,
            "max_keepalive": 10,
        })
    return _client


async def close_http_client():
    """关闭全局客户端（在应用关闭时调用）"""
    global _client
    if _client:
        await _client.aclose()
        _client = None
        logger.info("global httpx client closed")
