"""Opaque dashboard sessions and authenticated OAuth bundle encryption."""

import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken


class SessionSecurityError(Exception):
    """Raised when session storage or cryptographic validation fails."""


SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


class SessionCipher:
    def __init__(self, key: str):
        if not key:
            raise SessionSecurityError("session encryption key missing")
        try:
            raw = base64.urlsafe_b64decode(key.encode("ascii"))
            if len(raw) != 32:
                raise ValueError
            self._fernet = Fernet(key.encode("ascii"))
        except (ValueError, TypeError, UnicodeError):
            raise SessionSecurityError("session encryption key invalid") from None
        self._hash_key = hashlib.sha256(b"skullboard-session-hmac\0" + raw).digest()

    def hash_id(self, session_id: str) -> str:
        if not SESSION_ID_RE.fullmatch(session_id or ""):
            raise SessionSecurityError("session id invalid")
        return hmac.new(self._hash_key, session_id.encode(), hashlib.sha256).hexdigest()

    def encrypt(self, bundle: dict) -> str:
        return self._fernet.encrypt(json.dumps(bundle, separators=(",", ":")).encode()).decode()

    def decrypt(self, value: str) -> dict:
        try:
            data = json.loads(self._fernet.decrypt(value.encode(), ttl=None))
        except (InvalidToken, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            raise SessionSecurityError("session bundle invalid") from None
        if not isinstance(data, dict) or not data.get("access_token") or not data.get("discord_user_id"):
            raise SessionSecurityError("session bundle incomplete")
        return data


def new_session(cipher: SessionCipher, user_id: str, access_token: str, refresh_token: str,
                expires_at: datetime, csrf_token: str) -> tuple[str, dict]:
    session_id = secrets.token_urlsafe(32)
    bundle = {
        "discord_user_id": str(user_id),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "csrf_token": csrf_token,
        "token_expires_at": expires_at.astimezone(timezone.utc).isoformat(),
    }
    return session_id, {
        "session_hash": cipher.hash_id(session_id),
        "discord_user_id": str(user_id),
        "token_bundle": cipher.encrypt(bundle),
        "token_expires_at": bundle["token_expires_at"],
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
        "revoked_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
    }
