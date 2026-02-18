import os

from clinic_mcp_server.runtime.settings import ServerSettings


def test_settings_defaults_stdio(monkeypatch):
    monkeypatch.delenv("JWT_REQUIRED", raising=False)
    s = ServerSettings.load(transport="stdio", host="127.0.0.1", port=8080)
    assert s.transport == "stdio"
    assert s.jwt_required is False  # default for stdio


def test_settings_defaults_http(monkeypatch):
    monkeypatch.delenv("JWT_REQUIRED", raising=False)
    s = ServerSettings.load(transport="sse", host="0.0.0.0", port=8080)
    assert s.jwt_required is True  # default for HTTP


def test_settings_env_overrides(monkeypatch):
    monkeypatch.setenv("JWT_REQUIRED", "false")
    monkeypatch.setenv("JWT_SECRET", "abc")
    monkeypatch.setenv("JWT_ALLOWLIST_PATHS", "/health,/public")
    monkeypatch.setenv("JWT_AUDIENCE", "clinic")
    monkeypatch.setenv("JWT_ISSUER", "issuer1")

    s = ServerSettings.load(transport="streamable-http", host="h", port=1)
    assert s.jwt_required is False
    assert s.jwt_secret == "abc"
    assert s.jwt_allowlist_paths == ("/health", "/public")
    assert s.jwt_audience == "clinic"
    assert s.jwt_issuer == "issuer1"
