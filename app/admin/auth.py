"""
Admin API 认证中间件

保护 /admin/* 端点免于局域网未授权访问。
认证方式：HTTP Header `X-Admin-Key` 或 `Authorization: Bearer <admin-key>`

管理密钥配置：
- 环境变量 `ADMIN_API_KEY`（优先级高）
- 默认值 `admin:gw-console-2026`（建议在 .env 中覆盖）
"""

import os

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# 从环境变量读取，兜底默认值
_ADMIN_KEY = os.environ.get("ADMIN_API_KEY", "admin:gw-console-2026")


class AdminAuthMiddleware(BaseHTTPMiddleware):
    """验证所有 /admin/ 请求的 Bearer Token / X-Admin-Key"""

    async def dispatch(self, request: Request, call_next):
        # /health、控制台页面、静态资源 跳过认证
        skip_paths = ("/admin/static/", "/admin/console", "/health")
        if request.url.path.startswith(skip_paths):
            return await call_next(request)

        if request.url.path.startswith("/admin/"):
            auth = request.headers.get("Authorization", "")
            x_key = request.headers.get("X-Admin-Key", "")

            token = ""
            if auth.startswith("Bearer "):
                token = auth.removeprefix("Bearer ").strip()
            elif x_key:
                token = x_key.strip()

            if token != _ADMIN_KEY:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid admin key. Provide via Authorization: Bearer <key> or X-Admin-Key header."},
                )

        return await call_next(request)
