import pytest

from clinic_mcp_server.auth.jwt_hs256 import JwtHS256


def test_generate_and_verify_success():
    jwt = JwtHS256("secret")
    token = jwt.generate_demo_token(valid_seconds=60)
    claims = jwt.verify(token)
    assert claims["sub"] == "demo-user"
    assert "exp" in claims


def test_verify_bad_signature_fails():
    jwt = JwtHS256("secret")
    token = jwt.generate_demo_token(valid_seconds=60)
    # tamper token slightly
    parts = token.split(".")
    assert len(parts) == 3
    parts[1] = parts[1][::-1]  # corrupt payload b64
    bad = ".".join(parts)
    with pytest.raises(ValueError):
        jwt.verify(bad)


def test_verify_expired_fails():
    jwt = JwtHS256("secret")
    token = jwt.generate_demo_token(valid_seconds=-1)  # already expired
    with pytest.raises(ValueError, match="expired"):
        jwt.verify(token, leeway_seconds=0)


def test_audience_mismatch_fails():
    jwt_gen = JwtHS256("secret", audience="clinic")
    token = jwt_gen.generate_demo_token(valid_seconds=60)
    jwt_check = JwtHS256("secret", audience="other")
    with pytest.raises(ValueError, match="audience"):
        jwt_check.verify(token)


def test_issuer_mismatch_fails():
    jwt_gen = JwtHS256("secret", issuer="issuer-a")
    token = jwt_gen.generate_demo_token(valid_seconds=60)
    jwt_check = JwtHS256("secret", issuer="issuer-b")
    with pytest.raises(ValueError, match="issuer"):
        jwt_check.verify(token)
