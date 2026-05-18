"""
速率限制中间件

基于内存的滑动窗口计数器，适用单 Worker 部署。
限流策略：
  /chat           → 60 次/分钟/IP
  /v1/chat/*      → 30 次/分钟/API Key
  /v1/messages    → 30 次/分钟/API Key
  /admin/*        → 10 次/分钟/IP
  /health         → 不限

WARNING: 不跨 uvicorn worker（必须 workers=1）。多 Worker 需迁移到 Redis。
"""

import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class SlidingWindowCounter:
    """滑动窗口计数器，窗口大小 60 秒"""

    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> tuple[bool, int]:
        """检查是否允许请求。返回 (allowed, remaining)"""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        # 清理过期记录
        timestamps = self._requests[key]
        self._requests[key] = [t for t in timestamps if t > cutoff]

        curr_count = len(self._requests[key])
        if curr_count >= self.max_requests:
            return False, 0

        self._requests[key].append(now)
        return True, self.max_requests - curr_count - 1


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI 速率限制中间件"""

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        # 分级限流器
        self._admin_limiter = SlidingWindowCounter(max_requests=10)
        self._chat_limiter = SlidingWindowCounter(max_requests=60)
        self._v1_limiter = SlidingWindowCounter(max_requests=30)
        self._global_limiter = SlidingWindowCounter(max_requests=120)

    def _get_client_key(self, request: Request) -> str:
        """从请求中提取客户端标识（IP 或 API Key）"""
        client_ip = request.client.host if request.client else "unknown"
        auth = request.headers.get("Authorization", "")
        api_key = auth.removeprefix("Bearer ").strip() if auth else ""
        return api_key or client_ip

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path

        # /health 不限流
        if path == "/health":
            return await call_next(request)

        client_key = self._get_client_key(request)

        # 路径分级限流
        if path.startswith("/admin/"):
            allowed, remaining = self._admin_limiter.allow(client_key)
            limit = 10
        elif path.startswith("/v1/"):
            allowed, remaining = self._v1_limiter.allow(client_key)
            limit = 30
        elif path == "/chat":
            allowed, remaining = self._chat_limiter.allow(client_key)
            limit = 60
        else:
            allowed, remaining = self._global_limiter.allow(client_key)
            limit = 120

        if not allowed:
            headers = {
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + 60),
                "Retry-After": "60",
            }
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later.", "limit": limit, "remaining": 0},
                headers=headers,
            )

        # 通过，注入速率限制响应头
        response: Response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
