# src/clinic_mcp_server/auth/middleware.py
from __future__ import annotations

from typing import Iterable

from clinic_mcp_server.auth.jwt_hs256 import JwtHS256


class JwtAuthMiddleware:
    """
    Pure ASGI middleware (no Starlette).
    Wraps an ASGI app and enforces Bearer JWT for HTTP requests.
    """

    def __init__(
        self,
        app,
        *,
        jwt: JwtHS256,
        required: bool = True,
        allowlist_paths: Iterable[str] = ("/health",),
    ):
        self.app = app
        self.jwt = jwt
        self.required = required
        self.allowlist_paths = tuple(allowlist_paths)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if (not self.required) or (path in self.allowlist_paths):
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in (scope.get("headers") or [])}
        auth = headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            await send({"type": "http.response.start", "status": 401, "headers": []})
            await send({"type": "http.response.body", "body": b'{"error":"missing bearer token"}'})
            return

        token = auth.split(" ", 1)[1].strip()
        try:
            self.jwt.verify(token)
        except Exception:
            await send({"type": "http.response.start", "status": 401, "headers": []})
            await send({"type": "http.response.body", "body": b'{"error":"invalid token"}'})
            return

        await self.app(scope, receive, send)
