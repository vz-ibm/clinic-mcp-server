from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional


class JwtHS256:
    """
    Minimal HS256 JWT implementation without external deps.
    Good for demos. For production use PyJWT + key rotation.
    """

    def __init__(self, secret: str, audience: Optional[str] = None, issuer: Optional[str] = None):
        self.secret = secret
        self.audience = audience
        self.issuer = issuer

    @staticmethod
    def _b64url_encode(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    @staticmethod
    def _b64url_decode(data: str) -> bytes:
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + padding)

    def _sign(self, signing_input: bytes) -> str:
        sig = hmac.new(self.secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        return self._b64url_encode(sig)

    def generate_demo_token(self, valid_seconds: int = 24 * 3600) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        now = int(time.time())
        payload: Dict[str, Any] = {
            "sub": "demo-user",
            "role": "demo",
            "iat": now,
            "exp": now + valid_seconds,
        }
        if self.audience:
            payload["aud"] = self.audience
        if self.issuer:
            payload["iss"] = self.issuer

        header_b64 = self._b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_b64 = self._b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        sig_b64 = self._sign(signing_input)
        return f"{header_b64}.{payload_b64}.{sig_b64}"

    def verify(self, token: str, leeway_seconds: int = 30) -> Dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")

        header = json.loads(self._b64url_decode(parts[0]).decode("utf-8"))
        payload = json.loads(self._b64url_decode(parts[1]).decode("utf-8"))
        signature_b64 = parts[2]
        signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")

        if header.get("alg") != "HS256":
            raise ValueError("Only HS256 supported in this demo")

        expected = self._sign(signing_input)
        if not hmac.compare_digest(expected, signature_b64):
            raise ValueError("Invalid JWT signature")

        now = int(time.time())
        exp = payload.get("exp")
        if isinstance(exp, int) and now > exp + leeway_seconds:
            raise ValueError("JWT expired")

        nbf = payload.get("nbf")
        if isinstance(nbf, int) and now < nbf - leeway_seconds:
            raise ValueError("JWT not active yet")

        if self.audience is not None and payload.get("aud") != self.audience:
            raise ValueError("JWT audience mismatch")

        if self.issuer is not None and payload.get("iss") != self.issuer:
            raise ValueError("JWT issuer mismatch")

        return payload
