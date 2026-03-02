from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class ServerSettings:
    transport: str
    host: str
    port: int
    mcp_path: str
    sse_path: str

    jwt_required: bool
    jwt_secret: str
    jwt_audience: str | None
    jwt_issuer: str | None
    jwt_allowlist_paths: tuple[str, ...]

    @staticmethod
    def load(transport: str, host: str, port: int) -> ServerSettings:
        allowlist = os.getenv("JWT_ALLOWLIST_PATHS", "/health")
        allowlist_paths = tuple(p.strip() for p in allowlist.split(",") if p.strip())

        jwt_required_default = transport in {"streamable-http"}

        return ServerSettings(
            transport=transport,
            host=host,
            port=port,
            mcp_path=os.getenv("MCP_PATH", "/mcp"),
            sse_path=os.getenv("SSE_PATH", "/sse"),
            jwt_required=_env_bool("JWT_REQUIRED", jwt_required_default),
            jwt_secret=os.getenv("JWT_SECRET", "dev-secret-change-me"),
            jwt_audience=os.getenv("JWT_AUDIENCE") or None,
            jwt_issuer=os.getenv("JWT_ISSUER") or None,
            jwt_allowlist_paths=allowlist_paths,
        )
