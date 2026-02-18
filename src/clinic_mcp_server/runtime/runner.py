from __future__ import annotations

import uvicorn
from fastmcp import FastMCP

from clinic_mcp_server.auth.jwt_hs256 import JwtHS256
from clinic_mcp_server.auth.middleware import JwtAuthMiddleware
from clinic_mcp_server.runtime.asgi_health import HealthMountApp
from clinic_mcp_server.runtime.demo_token import print_demo_token
from clinic_mcp_server.runtime.settings import ServerSettings
from fastmcp.server.http import create_streamable_http_app

class McpRunner:
    def __init__(self, mcp: FastMCP):
        self.mcp = mcp

    def _wrap_with_health_and_jwt(self, *, settings: ServerSettings, base_asgi) :
        app = HealthMountApp(settings=settings, mounted=base_asgi)

        if settings.jwt_required:
            jwt = JwtHS256(
                settings.jwt_secret,
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
            )
            app = JwtAuthMiddleware(
                app,
                jwt=jwt,
                required=True,
                allowlist_paths=settings.jwt_allowlist_paths,
            )

        return app

    def run(self, settings: ServerSettings) -> None:
        print_demo_token(settings)

        if settings.transport == "stdio":
            self.mcp.run(transport="stdio")
            return

        if settings.transport == "streamable-http":
            base_asgi = self.mcp.http_app(
                transport="streamable-http",
                path=settings.mcp_path
            )
            app = self._wrap_with_health_and_jwt(settings=settings, base_asgi=base_asgi)
            uvicorn.run(app, host=settings.host, port=settings.port, log_level="info", ws="wsproto")
            return

        if settings.transport == "sse":
            base_asgi = self.mcp.http_app(
                transport="sse",
                path=settings.sse_path
            )
            app = self._wrap_with_health_and_jwt(settings=settings, base_asgi=base_asgi)
            uvicorn.run(app, host=settings.host, port=settings.port, log_level="info", ws="wsproto")
            return

        raise ValueError("transport must be one of: stdio | sse | streamable-http")
