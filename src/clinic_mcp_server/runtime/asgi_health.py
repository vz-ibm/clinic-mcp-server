from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict

from clinic_mcp_server.runtime.settings import ServerSettings

ASGIApp = Callable[
    [Dict[str, Any], Callable[[], Awaitable[Dict[str, Any]]], Callable[[Dict[str, Any]], Awaitable[None]]],
    Awaitable[None],
]


class HealthMountApp:
    """
    Minimal ASGI app:
      - GET /health -> 200 OK JSON
      - everything else -> delegated to mounted ASGI app (FastMCP)
    """

    def __init__(self, *, settings: ServerSettings, mounted: ASGIApp):
        self._settings = settings
        self._mounted = mounted

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self._mounted(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()

        if path == "/health" and method == "GET":
            payload = {
                "status": "ok",
                "transport": self._settings.transport,
                "host": self._settings.host,
                "port": self._settings.port,
                "mcp_path": self._settings.mcp_path,
                "sse_path": self._settings.sse_path,
                "jwt_required": self._settings.jwt_required,
                "jwt_allowlist_paths": list(self._settings.jwt_allowlist_paths),
            }
            body = json.dumps(payload).encode("utf-8")

            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"cache-control", b"no-store"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self._mounted(scope, receive, send)
