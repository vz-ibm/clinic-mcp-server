from __future__ import annotations

import json

import pytest

from clinic_mcp_server.auth.jwt_hs256 import JwtHS256
from clinic_mcp_server.auth.middleware import JwtAuthMiddleware


class DummyApp:
    def __init__(self):
        self.called = False
        self.last_scope = None

    async def __call__(self, scope, receive, send):
        self.called = True
        self.last_scope = scope
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def _run_asgi(app, scope):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return sent


def _get_body(sent) -> bytes:
    bodies = [m.get("body", b"") for m in sent if m.get("type") == "http.response.body"]
    return b"".join(bodies)


@pytest.mark.asyncio
async def test_allowlist_bypasses_auth():
    jwt = JwtHS256("secret")
    dummy = DummyApp()
    mw = JwtAuthMiddleware(dummy, jwt=jwt, required=True, allowlist_paths=["/health"])

    scope = {"type": "http", "method": "GET", "path": "/health", "query_string": b"", "headers": []}
    sent = await _run_asgi(mw, scope)

    assert dummy.called is True
    assert sent[0]["status"] == 200


@pytest.mark.asyncio
async def test_missing_bearer_returns_401():
    jwt = JwtHS256("secret")
    dummy = DummyApp()
    mw = JwtAuthMiddleware(dummy, jwt=jwt, required=True, allowlist_paths=[])

    scope = {"type": "http", "method": "POST", "path": "/mcp", "query_string": b"", "headers": []}
    sent = await _run_asgi(mw, scope)

    assert dummy.called is False
    assert sent[0]["status"] == 401
    body = _get_body(sent)
    assert json.loads(body.decode())["error"] == "missing bearer token"


@pytest.mark.asyncio
async def test_invalid_token_returns_401():
    jwt = JwtHS256("secret")
    dummy = DummyApp()
    mw = JwtAuthMiddleware(dummy, jwt=jwt, required=True, allowlist_paths=[])

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "query_string": b"",
        "headers": [(b"authorization", b"Bearer not-a-real-token")],
    }
    sent = await _run_asgi(mw, scope)

    assert dummy.called is False
    assert sent[0]["status"] == 401
    body = _get_body(sent)
    assert json.loads(body.decode())["error"] == "invalid token"


@pytest.mark.asyncio
async def test_valid_token_calls_downstream():
    jwt = JwtHS256("secret")
    token = jwt.generate_demo_token(valid_seconds=60)

    dummy = DummyApp()
    mw = JwtAuthMiddleware(dummy, jwt=jwt, required=True, allowlist_paths=[])

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "query_string": b"",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
    }
    sent = await _run_asgi(mw, scope)

    assert dummy.called is True
    assert sent[0]["status"] == 200
