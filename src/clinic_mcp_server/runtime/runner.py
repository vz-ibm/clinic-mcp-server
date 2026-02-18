from __future__ import annotations

from fastmcp import FastMCP
import uvicorn

from clinic_mcp_server.auth.jwt_hs256 import JwtHS256
from clinic_mcp_server.auth.middleware import JwtAuthMiddleware
from clinic_mcp_server.runtime.settings import ServerSettings


class McpRunner:
    def __init__(self, mcp: FastMCP):
        self.mcp = mcp

    def run(self, settings: ServerSettings) -> None:
        if settings.transport == "stdio":
            self.mcp.run(transport="stdio")
            return

        if settings.transport == "streamable-http":
            base_asgi = self.mcp.http_app()

            jwt = JwtHS256(
                settings.jwt_secret,
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
            )
            app = JwtAuthMiddleware(
                base_asgi,
                jwt=jwt,
                required=True,  # force JWT ON for HTTP demo
                allowlist_paths=settings.jwt_allowlist_paths,
            )

            uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
            return

        if settings.transport == "sse":
            # SSE runs via FastMCP internal server in your version; no JWT demo here
            self.mcp.run(transport="sse", host=settings.host, port=settings.port)
            return

        raise ValueError("transport must be one of: stdio | sse | streamable-http")
