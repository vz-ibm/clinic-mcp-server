# src/clinic_mcp_server/runtime/demo_token.py
from __future__ import annotations

from clinic_mcp_server.auth.jwt_hs256 import JwtHS256
from clinic_mcp_server.runtime.settings import ServerSettings


def _client_host(host: str) -> str:
    """Convert bind-all addresses into a client-friendly host for examples."""
    if host in ("0.0.0.0", "::", "[::]"):
        return "127.0.0.1"
    return host


def _base_url(host: str, port: int) -> str:
    return f"http://{_client_host(host)}:{port}"


def _banner(title: str) -> str:
    line = "=" * 80
    return f"\n{line}\n{title}\n{line}"


def print_demo_token(settings: ServerSettings) -> None:
    """
    Print startup instructions and (optionally) a demo JWT token.

    Demo policy:
    - streamable-http: JWT is supported -> print token (if jwt_required) and curl example
    - sse: JWT is NOT used in this demo -> print SSE curl example WITHOUT token
    - stdio: no HTTP -> print nothing

    Also:
    - Never print 0.0.0.0 as a client address; use 127.0.0.1 for examples.
    """
    if not getattr(settings, "print_demo_token", True):
        return

    transport = (settings.transport or "").strip().lower()

    # STDIO: nothing to print (no HTTP endpoint)
    if transport == "stdio":
        return

    base = _base_url(settings.host, settings.port)
    endpoint_path = getattr(settings, "endpoint_path", "/mcp")
    endpoint = f"{base}{endpoint_path}"
    
    if settings.jwt_required:

        jwt = JwtHS256(
        settings.jwt_secret,
        audience=getattr(settings, "jwt_audience", None),
        issuer=getattr(settings, "jwt_issuer", None),
        )
        token = jwt.generate_demo_token()

        print("🔐 copy - paste to export JWT token (HS256):")
        print(f"export TOKEN=\"{token}\"")
        print("-" * 80)
    else:
        print("JWT: disabled (JWT_REQUIRED=false).")
       


    # SSE: no JWT in this demo
    if transport == "sse":
        print(_banner("📡 MCP Server (SSE)"))
        print(endpoint)
        print("-" * 80)
        return

    # Streamable HTTP: JWT demo
    if transport == "streamable-http":
        print(_banner("🌐 MCP Server (Streamable HTTP)"))
        print(endpoint)
        print("-" * 80)
        return
      

    # Unknown transport: don't crash startup
    print(_banner("ℹ️ MCP Server"))
    print(f"Unknown transport: {settings.transport}")
    print("Endpoint:")
    print(endpoint)
    print("=" * 80 + "\n")
