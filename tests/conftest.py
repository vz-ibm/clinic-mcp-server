"""Shared fixtures for MCP integration tests (stdio / streamable-http / sse)."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from clinic_mcp_server.auth.jwt_hs256 import JwtHS256

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


# ---------- Helpers ----------

def wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                if sock.connect_ex((host, port)) == 0:
                    return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def _server_env(tmp_path: Path) -> dict[str, str]:
    """
    Environment for starting the server subprocess.

    - Uses temp sqlite file per test run
    - Sets deterministic JWT secret for tests
    """
    env = os.environ.copy()
    env["CLINIC_DB_PATH"] = str(tmp_path / "clinic_test.db")
    env["JWT_SECRET"] = "dev-secret-change-me"
    env["JWT_REQUIRED"] = "true"
    env["JWT_ALLOWLIST_PATHS"] = "/health"
    return env

@pytest.fixture
def demo_jwt_token() -> str:
    jwt = JwtHS256("dev-secret-change-me")
    return jwt.generate_demo_token(valid_seconds=3600)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------- STDIO session ----------

@pytest.fixture
def stdio_session(tmp_path: Path):
    """Async context manager for an MCP client session connected via stdio."""

    @asynccontextmanager
    async def _session() -> AsyncGenerator[ClientSession]:
        server_params = StdioServerParameters(
            command="uv",
            args=[
                "run",
                "python",
                "-m",
                "clinic_mcp_server.main",
                "run",
                "--transport",
                "stdio",
            ],
            env=_server_env(tmp_path),
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    return _session()


# ---------- HTTP server fixtures ----------

@pytest.fixture
def http_server(tmp_path: Path):
    """Start Streamable HTTP MCP server and return base URL."""
    host = "127.0.0.1"
    port = 3001

    env = _server_env(tmp_path)

    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "python",
            "-m",
            "clinic_mcp_server.main",
            "run",
            "--transport",
            "streamable-http",
            "--host",
            host,
            "--port",
            str(port),
        ],
        env=env,
    )

    try:
        if not wait_for_port(host, port, timeout=10.0):
            if proc.poll() is not None:
                raise RuntimeError(f"HTTP server exited with code {proc.returncode}")
            raise RuntimeError(f"HTTP server failed to start on port {port}")

        yield f"http://{host}:{port}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()




# ---------- HTTP sessions ----------

@pytest.fixture
def http_session(http_server, demo_jwt_token):
    @asynccontextmanager
    async def _session() -> AsyncGenerator[ClientSession]:
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {demo_jwt_token}"},
            timeout=10.0,
        ) as client:
            async with streamable_http_client(f"{http_server}/mcp", http_client=client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session

    return _session()




# -------------- SSE sessions -------------------
@pytest.fixture
def sse_server(tmp_path: Path):
    host = "127.0.0.1"
    port = 3002

    env = _server_env(tmp_path)
    # Important: SSE has NO JWT in this demo
    env["JWT_REQUIRED"] = "false"

    proc = subprocess.Popen(
        ["uv", "run", "python", "-m", "clinic_mcp_server.main", "run","--transport", "sse", "--host", host, "--port", str(port)],
        env=env,
    )

    try:
        if not wait_for_port(host, port, timeout=10.0):
            if proc.poll() is not None:
                raise RuntimeError(f"SSE server exited with code {proc.returncode}")
            raise RuntimeError("SSE server failed to start")
        yield f"http://{host}:{port}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@pytest.fixture
def sse_session(sse_server):
    @asynccontextmanager
    async def _session() -> AsyncGenerator[ClientSession]:
        async with sse_client(f"{sse_server}/sse") as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    return _session()

