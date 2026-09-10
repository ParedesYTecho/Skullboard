from flask import Flask, request, send_from_directory, redirect, jsonify, make_response
from threading import Thread, Lock
from urllib.parse import urlencode
from collections import OrderedDict
import requests
import os
import secrets
import time
import re
import html
import random
import functools
import hashlib
import hmac
import logging
from datetime import datetime, timezone
from dashboard_sessions import SessionCipher, SessionSecurityError, new_session

logger = logging.getLogger("skullboard.webserver")
_LOG_SECRET_RE = re.compile(
    r"(?i)(bearer\s+|(?:access[_-]?token|refresh[_-]?token|session[_-]?id|client[_-]?secret|api[_-]?key|authorization|code|state|cookie)\s*[=:]\s*)[^\s&,;]+"
)


def _redact_log(value) -> str:
    return _LOG_SECRET_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", str(value))

# ─── Serialización y Métricas de Rendimiento ─────────────────────────────────
try:
    import orjson
    def json_dumps(obj) -> str:
        return orjson.dumps(obj).decode("utf-8")
except ImportError:
    import json
    def json_dumps(obj) -> str:
        return json.dumps(obj)

try:
    import psutil
    def get_memory_mb() -> float:
        return round(psutil.Process().memory_info().rss / (1024 * 1024), 2)
except ImportError:
    def get_memory_mb() -> float:
        return 0.0

_START_TIME = time.time()

app = Flask(__name__)

APPLICATION_ID = os.getenv("DISCORD_APPLICATION_ID", "1367463352774955059")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "https://skullboard-fqf1.onrender.com/callback")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
CONTACT_TO   = "globalsupportpyt@gmail.com"
CONTACT_FROM = "SkullBoard <onboarding@resend.dev>"
OWNER_ID = str(os.getenv("BOT_OWNER_ID", "561225979389804544"))
SESSION_TTL = 30 * 24 * 60 * 60
APP_ENV = os.getenv("SKULLBOARD_ENV", "development").lower()
_DEFAULT_ALLOWED_ORIGINS = "https://skullboard.vercel.app" if APP_ENV == "production" else \
    "https://skullboard.vercel.app,http://localhost:8080,http://127.0.0.1:8080"
ALLOWED_ORIGINS = {
    origin.strip().rstrip("/") for origin in os.getenv(
        "WEB_ALLOWED_ORIGINS", _DEFAULT_ALLOWED_ORIGINS
    ).split(",") if origin.strip()
}


def _session_cookie_name(env: str | None = None) -> str:
    return "__Host-skullboard_session" if (env or APP_ENV) == "production" else "skullboard_session"


def _session_cookie_secure(env: str | None = None) -> bool:
    return (env or APP_ENV) == "production"


SESSION_COOKIE = _session_cookie_name()
SESSION_ENCRYPTION_KEY = os.getenv("SKULLBOARD_SESSION_ENCRYPTION_KEY")
if APP_ENV == "production" and not SESSION_ENCRYPTION_KEY:
    raise RuntimeError("SKULLBOARD_SESSION_ENCRYPTION_KEY is required in production")
_session_cipher = SessionCipher(SESSION_ENCRYPTION_KEY) if SESSION_ENCRYPTION_KEY else None
_session_lock = Lock()
_refresh_locks: dict[str, Lock] = {}


def _dashboard_redirect_uri() -> str:
    configured = os.getenv("SKULLBOARD_DASHBOARD_REDIRECT_URI")
    if configured:
        return configured
    return "http://localhost:8080/dashboard" if APP_ENV != "production" else "https://skullboard.vercel.app/dashboard"


def _dashboard_redirects() -> set[str]:
    if APP_ENV == "production":
        return {_dashboard_redirect_uri()}
    return {_dashboard_redirect_uri(), "http://127.0.0.1:8080/dashboard", "http://localhost:8080/dashboard"}
_rate_lock = Lock()
_rate_buckets: OrderedDict[tuple[str, str], list[float]] = OrderedDict()

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')

# ─── Security Headers ─────────────────────────────────────────────────────────
@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    if request.path.startswith("/api/") or request.path in ("/dashboard", "/callback"):
        response.headers["Cache-Control"] = "no-store"
    return response

# ─── Thread-Safe Caches ───────────────────────────────────────────────────────
_stats_lock = Lock()
_stats_cache = {"ts": 0.0, "data": {"servers": None, "highlighted": None}, "refreshing": False}
_STATS_TTL = 60

_contact_lock = Lock()
_contact_last: OrderedDict[str, float] = OrderedDict()
_global_contact_history: list[float] = []
_MAX_CONTACT_IPS = 2000
_MAX_GLOBAL_PER_MINUTE = 10

_oauth_lock = Lock()
_oauth_states: OrderedDict[str, float] = OrderedDict()
_OAUTH_STATE_TTL = 600
_MAX_OAUTH_STATES = 1000

# ─── PostgREST Resilience Retry Engine ─────────────────────────────────────────
def sync_db_retry(max_retries: int = 3, base_delay: float = 0.3, max_delay: float = 2.0):
    """Reintenta automáticamente llamadas síncronas PostgREST ante fallos temporales."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_exc = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt == max_retries:
                        print(f"[ERROR] [Sync DB Retry] Fallo tras {max_retries} intentos ({func.__name__}): {_redact_log(e)}")
                        raise
                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = min(delay * jitter, max_delay)
                    print(f"[WARN] [Sync DB Retry] Intento {attempt}/{max_retries} en {func.__name__} fallo: {_redact_log(e)}. Reintentando en {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                    delay *= 2
            if last_exc:
                raise last_exc
        return wrapper
    return decorator

@sync_db_retry(max_retries=3, base_delay=0.3, max_delay=2.0)
def _sb_count(table: str):
    """Cuenta filas de una tabla vía REST (Content-Range), sin traer datos."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Prefer": "count=exact", "Range": "0-0"},
            params={"select": "guild_id"}, timeout=6,
        )
        if r.status_code == 429 or r.status_code >= 500:
            r.raise_for_status()
        total = r.headers.get("Content-Range", "").split("/")[-1]
        return int(total) if total.isdigit() else None
    except (requests.RequestException, TimeoutError) as e:
        raise e
    except Exception:
        return None

def _cors(resp):
    origin = request.headers.get("Origin", "").rstrip("/")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Vary"] = "Origin"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRF-Token"
    return resp

@app.after_request
def after_request_cors(response):
    return _cors(response)

def _require_origin():
    origin = request.headers.get("Origin", "").rstrip("/")
    if not origin and request.method == "GET" and request.path == "/api/auth/start":
        return None
    if origin not in ALLOWED_ORIGINS:
        return _cors(jsonify(ok=False, error="Origen no permitido")), 403
    return None


def _new_dashboard_state() -> str:
    if not _session_cipher or not SUPABASE_URL or not SUPABASE_KEY:
        raise SessionSecurityError("secure session persistence unavailable")
    state = secrets.token_urlsafe(32)
    expires_at = datetime.fromtimestamp(time.time() + _OAUTH_STATE_TTL, timezone.utc).isoformat()
    if not _sb_upsert("dashboard_oauth_states", {
        "state_hash": _session_cipher.hash_state(state),
        "expires_at": expires_at
    }):
        raise SessionSecurityError("oauth state persistence failed")
    return state


def _consume_dashboard_state(state: str) -> bool:
    try:
        state_hash = _session_cipher.hash_state(state)
    except SessionSecurityError:
        return False
    rows = _sb_select_required("dashboard_oauth_states", {
        "state_hash": f"eq.{state_hash}",
        "limit": 1
    })
    if not rows:
        return False
    try:
        expires_at = datetime.fromisoformat(rows[0]["expires_at"].replace("Z", "+00:00"))
        if expires_at.timestamp() <= time.time():
            _sb_delete("dashboard_oauth_states", {"state_hash": f"eq.{state_hash}"})
            return False
    except (KeyError, ValueError, TypeError, AttributeError, SessionSecurityError):
        _sb_delete("dashboard_oauth_states", {"state_hash": f"eq.{state_hash}"})
        return False
    return _sb_delete("dashboard_oauth_states", {"state_hash": f"eq.{state_hash}"}, require_match=True)


def _purge_expired_sessions():
    if not _session_cipher or not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        expires_filter = {"expires_at": f"lt.{datetime.now(timezone.utc).isoformat()}"}
        _sb_delete("dashboard_sessions", expires_filter)
        _sb_delete("dashboard_oauth_states", expires_filter)
    except Exception:
        logger.warning("No se pudieron limpiar sesiones expiradas")


_session_purge_lock = Lock()
_last_session_purge = 0.0
_SESSION_PURGE_INTERVAL = 3600


def _maybe_purge_expired_sessions():
    global _last_session_purge
    now = time.time()
    if now - _last_session_purge < _SESSION_PURGE_INTERVAL:
        return
    with _session_purge_lock:
        if now - _last_session_purge < _SESSION_PURGE_INTERVAL:
            return
        _last_session_purge = now
    _purge_expired_sessions()


def _require_session():
    if not _session_cipher or not SUPABASE_URL or not SUPABASE_KEY:
        raise SessionSecurityError("secure session persistence unavailable")
    session_id = request.cookies.get(SESSION_COOKIE, "")
    if not session_id:
        return None
    try:
        session_hash = _session_cipher.hash_id(session_id)
    except SessionSecurityError:
        return None
    rows = _sb_select_required("dashboard_sessions", {"session_hash": f"eq.{session_hash}", "limit": 1})
    if not rows:
        return None
    row = rows[0]
    try:
        expiry = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        if row.get("revoked_at") or expiry.timestamp() <= time.time():
            return None
        bundle = _session_cipher.decrypt(row["token_bundle"])
        if (bundle.get("session_hash") != row.get("session_hash") or
                bundle.get("discord_user_id") != row.get("discord_user_id") or
                bundle.get("scopes") != ["identify", "guilds"]):
            return None
    except (KeyError, ValueError, TypeError, AttributeError, SessionSecurityError):
        return None
    touched = _sb_patch("dashboard_sessions", {
        "session_hash": f"eq.{session_hash}",
        "revoked_at": "is.null",
        "expires_at": f"gt.{datetime.now(timezone.utc).isoformat()}"
    }, {"last_seen_at": datetime.now(timezone.utc).isoformat()})
    if not touched:
        return None
    return session_id, row, bundle


def _invalidate_session(session_hash: str):
    if not _sb_delete("dashboard_sessions", {"session_hash": f"eq.{session_hash}"}):
        raise SessionSecurityError("session invalidation failed")


def _invalidate_refresh_owned_session(session_hash: str, refresh_lock_id: str, token_version: int) -> bool:
    return _sb_delete("dashboard_sessions", {
        "session_hash": f"eq.{session_hash}",
        "refresh_lock_id": f"eq.{refresh_lock_id}",
        "token_version": f"eq.{token_version}"
    }, require_match=True)


def _invalidate_request_session():
    session_id = request.cookies.get(SESSION_COOKIE, "")
    if not session_id or not _session_cipher:
        return
    try:
        _invalidate_session(_session_cipher.hash_id(session_id))
    except SessionSecurityError:
        logger.warning("No se pudo invalidar sesión Discord rechazada")


def _refresh_lock_for(session_hash: str) -> Lock:
    with _session_lock:
        return _refresh_locks.setdefault(session_hash, Lock())


def _claim_refresh_lock(session_hash: str):
    lock_id = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc).isoformat()
    lock_until = datetime.fromtimestamp(time.time() + 30, timezone.utc).isoformat()
    rows = _sb_patch("dashboard_sessions", {
        "session_hash": f"eq.{session_hash}",
        "revoked_at": "is.null",
        "expires_at": f"gt.{now}",
        "or": f"(refresh_lock_id.is.null,refresh_lock_until.lt.{now})"
    }, {"refresh_lock_id": lock_id, "refresh_lock_until": lock_until})
    return lock_id if rows else None


def _release_refresh_lock(session_hash: str, lock_id: str):
    try:
        _sb_patch("dashboard_sessions", {"session_hash": f"eq.{session_hash}", "refresh_lock_id": f"eq.{lock_id}"}, {
            "refresh_lock_id": None,
            "refresh_lock_until": None
        })
    except SessionSecurityError:
        logger.warning("No se pudo liberar el bloqueo de renovación")


def _session_credentials():
    session = _require_session()
    if not session:
        return None
    session_id, row, bundle = session
    try:
        token_expiry = datetime.fromisoformat(bundle["token_expires_at"].replace("Z", "+00:00")).timestamp()
    except (KeyError, ValueError, TypeError, AttributeError):
        _invalidate_session(_session_cipher.hash_id(session_id))
        return None
    if token_expiry - time.time() > 120:
        return bundle
    refresh_token = bundle.get("refresh_token")
    session_hash = _session_cipher.hash_id(session_id)
    if not refresh_token:
        _invalidate_session(session_hash)
        return None
    if not DISCORD_CLIENT_SECRET:
        raise SessionSecurityError("oauth refresh unavailable")
    lock = _refresh_lock_for(session_hash)
    with lock:
        current = _require_session()
        if not current:
            return None
        _, current_row, current_bundle = current
        try:
            if datetime.fromisoformat(current_bundle["token_expires_at"].replace("Z", "+00:00")).timestamp() - time.time() > 120:
                return current_bundle
        except (KeyError, ValueError, TypeError, AttributeError):
            _invalidate_session(session_hash)
            return None
        refresh_lock_id = _claim_refresh_lock(session_hash)
        if not refresh_lock_id:
            # ponytail: short bounded polling, replace with a queue only if refresh volume justifies it.
            deadline = time.time() + 8
            while time.time() < deadline:
                time.sleep(0.25)
                current = _require_session()
                if not current:
                    return None
                try:
                    if datetime.fromisoformat(current[2]["token_expires_at"].replace("Z", "+00:00")).timestamp() - time.time() > 120:
                        return current[2]
                except (KeyError, ValueError, TypeError, AttributeError):
                    return None
            raise SessionSecurityError("oauth refresh busy")
        try:
            response = requests.post("https://discord.com/api/v10/oauth2/token", data={
                "client_id": APPLICATION_ID, "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "refresh_token", "refresh_token": current_bundle["refresh_token"]
            }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=8)
            if response.status_code in (400, 401, 403):
                if _invalidate_refresh_owned_session(session_hash, refresh_lock_id, int(current_row.get("token_version") or 0)):
                    return None
                latest = _require_session()
                return latest[2] if latest else None
            if response.status_code != 200:
                _release_refresh_lock(session_hash, refresh_lock_id)
                raise SessionSecurityError("oauth refresh unavailable")
            data = response.json()
            access_token = data.get("access_token")
            if not access_token:
                if _invalidate_refresh_owned_session(session_hash, refresh_lock_id, int(current_row.get("token_version") or 0)):
                    return None
                latest = _require_session()
                return latest[2] if latest else None
            new_expiry = datetime.fromtimestamp(time.time() + max(int(data.get("expires_in", 3600)), 60), timezone.utc)
            current_bundle.update({"access_token": access_token, "token_expires_at": new_expiry.isoformat()})
            if data.get("refresh_token"):
                current_bundle["refresh_token"] = data["refresh_token"]
            updated = _sb_patch("dashboard_sessions", {
                "session_hash": f"eq.{session_hash}",
                "refresh_lock_id": f"eq.{refresh_lock_id}",
                "revoked_at": "is.null",
                "expires_at": f"gt.{datetime.now(timezone.utc).isoformat()}"
            }, {
                "token_bundle": _session_cipher.encrypt(current_bundle),
                "token_expires_at": new_expiry.isoformat(),
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
                "refresh_lock_id": None,
                "refresh_lock_until": None,
                "token_version": int(current_row.get("token_version") or 0) + 1
            })
            if not updated:
                return None
            return current_bundle
        except (requests.RequestException, ValueError, TypeError):
            _release_refresh_lock(session_hash, refresh_lock_id)
            raise SessionSecurityError("oauth refresh unavailable") from None


def _session_token():
    bundle = _session_credentials()
    return bundle["access_token"] if bundle else ""

def _session_user():
    token = _session_token()
    return _fetch_discord_user(token) if token else None

def _valid_guild_id(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9]{15,20}", str(value)))

_discord_user_cache = {}
_discord_guilds_cache = {}
_discord_cache_lock = Lock()
_DISCORD_CACHE_TTL = 120  # 2 minutos de cache

def _fetch_discord_user(token: str):
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    now = time.time()
    with _discord_cache_lock:
        if token_hash in _discord_user_cache:
            ts, val = _discord_user_cache[token_hash]
            if now - ts < _DISCORD_CACHE_TTL:
                return val
    try:
        r = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bearer {token}"}, timeout=6)
        if r.status_code in (401, 403):
            logger.warning(f"⚠️ [OAuth @me] Discord API devolvió HTTP {r.status_code}")
            return None
        if r.status_code != 200:
            logger.warning(f"⚠️ [OAuth @me] Discord API temporalmente no disponible: HTTP {r.status_code}")
            raise SessionSecurityError("discord user service unavailable")
        data = r.json()
        with _discord_cache_lock:
            _discord_user_cache[token_hash] = (now, data)
            if len(_discord_user_cache) > 500:
                _discord_user_cache.pop(next(iter(_discord_user_cache)))
        return data
    except requests.RequestException as e:
        logger.error(f"❌ [OAuth @me] Error al consultar usuario: {_redact_log(e)}")
        raise SessionSecurityError("discord user service unavailable") from None
    except (ValueError, TypeError) as e:
        logger.error(f"❌ [OAuth @me] Respuesta inválida: {_redact_log(e)}")
        raise SessionSecurityError("discord user service unavailable") from None

def _fetch_discord_guilds(token: str):
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    now = time.time()
    with _discord_cache_lock:
        if token_hash in _discord_guilds_cache:
            ts, val = _discord_guilds_cache[token_hash]
            if now - ts < _DISCORD_CACHE_TTL:
                return val
    try:
        r = requests.get("https://discord.com/api/v10/users/@me/guilds", headers={"Authorization": f"Bearer {token}"}, timeout=8)
        if r.status_code in (401, 403):
            logger.warning(f"⚠️ [OAuth @me/guilds] Discord API devolvió HTTP {r.status_code}")
            return None
        if r.status_code != 200:
            logger.warning(f"⚠️ [OAuth @me/guilds] Discord API temporalmente no disponible: HTTP {r.status_code}")
            raise SessionSecurityError("discord guild service unavailable")
        data = r.json()
        with _discord_cache_lock:
            _discord_guilds_cache[token_hash] = (now, data)
            if len(_discord_guilds_cache) > 500:
                _discord_guilds_cache.pop(next(iter(_discord_guilds_cache)))
        return data
    except requests.RequestException as e:
        logger.error(f"❌ [OAuth @me/guilds] Error al consultar servidores: {_redact_log(e)}")
        raise SessionSecurityError("discord guild service unavailable") from None
    except (ValueError, TypeError) as e:
        logger.error(f"❌ [OAuth @me/guilds] Respuesta inválida: {_redact_log(e)}")
        raise SessionSecurityError("discord guild service unavailable") from None


def _clear_discord_cache(token: str):
    if not token:
        return
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with _discord_cache_lock:
        _discord_user_cache.pop(token_hash, None)
        _discord_guilds_cache.pop(token_hash, None)


def _fetch_bot_channels(guild_id: str) -> list[dict]:
    """Return writable channel candidates visible to SkullBoard's bot."""
    if not DISCORD_BOT_TOKEN:
        raise SessionSecurityError("discord channel service unavailable")
    try:
        response = requests.get(
            f"https://discord.com/api/v10/guilds/{guild_id}/channels",
            headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"},
            timeout=6,
        )
        if response.status_code in (401, 403):
            raise SessionSecurityError("discord channel service unavailable")
        if response.status_code != 200:
            raise SessionSecurityError("discord channel service unavailable")
        payload = response.json()
        if not isinstance(payload, list):
            raise SessionSecurityError("discord channel service unavailable")
        return [
            {"id": str(channel.get("id")), "name": str(channel.get("name") or ""), "type": channel.get("type")}
            for channel in payload
            if channel.get("type") in (0, 5) and _valid_guild_id(str(channel.get("id") or ""))
        ]
    except SessionSecurityError:
        raise
    except (requests.RequestException, ValueError, TypeError):
        raise SessionSecurityError("discord channel service unavailable") from None


def _channel_is_available_to_bot(guild_id: str, channel_id: int) -> bool:
    if channel_id == 0:
        return True
    return any(channel["id"] == str(channel_id) for channel in _fetch_bot_channels(guild_id))


def _public_discord_user(data: dict) -> dict:
    return {
        key: data.get(key)
        for key in ("id", "username", "global_name", "avatar")
        if data.get(key) is not None
    }

@sync_db_retry(max_retries=3, base_delay=0.3, max_delay=2.0)
def _sb_select(table: str, params: dict):
    if not (SUPABASE_URL and SUPABASE_KEY):
        return []
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params=params, timeout=6
        )
        if r.status_code == 429 or r.status_code >= 500:
            r.raise_for_status()
        return r.json() if r.status_code == 200 else []
    except (requests.RequestException, TimeoutError) as e:
        raise e
    except Exception:
        return []

@sync_db_retry(max_retries=3, base_delay=0.3, max_delay=2.0)
def _sb_select_required(table: str, params: dict):
    if not (SUPABASE_URL and SUPABASE_KEY):
        raise SessionSecurityError("secure session persistence unavailable")
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params=params, timeout=6
        )
        if r.status_code == 429 or r.status_code >= 500:
            r.raise_for_status()
        if r.status_code != 200:
            raise SessionSecurityError("secure session persistence unavailable")
        data = r.json()
        if not isinstance(data, list):
            raise SessionSecurityError("secure session persistence unavailable")
        return data
    except requests.RequestException:
        raise SessionSecurityError("secure session persistence unavailable") from None
    except (ValueError, TypeError):
        raise SessionSecurityError("secure session persistence unavailable") from None

@sync_db_retry(max_retries=3, base_delay=0.3, max_delay=2.0)
def _sb_patch(table: str, params: dict, data: dict):
    if not (SUPABASE_URL and SUPABASE_KEY):
        raise SessionSecurityError("secure session persistence unavailable")
    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            },
            params=params, json=data, timeout=6
        )
        if r.status_code == 429 or r.status_code >= 500:
            r.raise_for_status()
        if r.status_code not in (200, 204):
            raise SessionSecurityError("secure session persistence unavailable")
        if r.status_code == 204:
            return []
        result = r.json()
        if not isinstance(result, list):
            raise SessionSecurityError("secure session persistence unavailable")
        return result
    except requests.RequestException:
        raise SessionSecurityError("secure session persistence unavailable") from None
    except (ValueError, TypeError):
        raise SessionSecurityError("secure session persistence unavailable") from None

@sync_db_retry(max_retries=3, base_delay=0.3, max_delay=2.0)
def _sb_upsert(table: str, data: dict):
    if not (SUPABASE_URL and SUPABASE_KEY):
        return False
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates"
            },
            json=data, timeout=6
        )
        if r.status_code == 429 or r.status_code >= 500:
            r.raise_for_status()
        return r.status_code in (200, 201, 204)
    except (requests.RequestException, TimeoutError):
        return False
    except Exception:
        return False

@sync_db_retry(max_retries=3, base_delay=0.3, max_delay=2.0)
def _sb_delete(table: str, params: dict, require_match: bool = False):
    if not (SUPABASE_URL and SUPABASE_KEY):
        return False
    try:
        r = requests.delete(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                **({"Prefer": "return=representation"} if require_match else {})
            },
            params=params, timeout=6
        )
        if r.status_code not in (200, 204):
            return False
        if not require_match:
            return True
        deleted = r.json() if r.status_code == 200 else []
        return isinstance(deleted, list) and bool(deleted)
    except requests.RequestException:
        return False
    except (ValueError, TypeError):
        return False

@sync_db_retry(max_retries=3, base_delay=0.3, max_delay=2.0)
def _sb_rpc(function_name: str, payload: dict):
    if not (SUPABASE_URL and SUPABASE_KEY):
        return []
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/{function_name}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json"
            },
            json=payload, timeout=6
        )
        if r.status_code == 429 or r.status_code >= 500:
            r.raise_for_status()
        return r.json() if r.status_code == 200 else []
    except (requests.RequestException, TimeoutError) as e:
        raise e
    except Exception:
        return []

@sync_db_retry(max_retries=3, base_delay=0.3, max_delay=2.0)
def _sb_rpc_required(function_name: str, payload: dict):
    if not (SUPABASE_URL and SUPABASE_KEY):
        raise SessionSecurityError("secure database unavailable")
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/{function_name}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json"
            },
            json=payload, timeout=6
        )
        if r.status_code == 429 or r.status_code >= 500:
            r.raise_for_status()
        if r.status_code != 200:
            raise SessionSecurityError("secure database unavailable")
        result = r.json()
        if not isinstance(result, list):
            raise SessionSecurityError("secure database unavailable")
        return result
    except requests.RequestException:
        raise SessionSecurityError("secure database unavailable") from None
    except (ValueError, TypeError):
        raise SessionSecurityError("secure database unavailable") from None

def _get_real_ip() -> str:
    return request.remote_addr or "127.0.0.1"

@app.before_request
def enforce_rate_limit():
    if not request.path.startswith("/api/"):
        return None
    _maybe_purge_expired_sessions()
    limit = 30 if request.path in ("/api/auth/token", "/api/contact") else 120
    now = time.time()
    key = (_get_real_ip(), request.path)
    with _rate_lock:
        recent = [stamp for stamp in _rate_buckets.get(key, []) if now - stamp < 60]
        if len(recent) >= limit:
            return _cors(jsonify(ok=False, error="Demasiadas solicitudes.")), 429
        recent.append(now)
        _rate_buckets[key] = recent
        _rate_buckets.move_to_end(key)
        while len(_rate_buckets) > 10000:
            _rate_buckets.popitem(last=False)
    return None

@app.route('/')
def index():
    try:
        return send_from_directory('legal', 'index.html')
    except Exception:
        return "Hello, I am alive!"

_STATS_COMMANDS = 22

@app.route('/api/stats')
def api_stats():
    now = time.time()
    needs_refresh = False
    with _stats_lock:
        cached = _stats_cache["data"]
        if (now - _stats_cache["ts"] >= _STATS_TTL or cached["servers"] is None) and not _stats_cache.get("refreshing", False):
            _stats_cache["refreshing"] = True
            needs_refresh = True
        data = cached

    if needs_refresh:
        try:
            # Las llamadas HTTP se hacen FUERA del lock principal
            srv = _sb_count("settings")
            hl  = _sb_count("tracked_messages")
            if srv is not None:
                new_data = {"servers": srv, "highlighted": hl, "commands": _STATS_COMMANDS}
                with _stats_lock:
                    _stats_cache["ts"] = time.time()
                    _stats_cache["data"] = new_data
                    _stats_cache["refreshing"] = False
                data = new_data
            else:
                with _stats_lock:
                    _stats_cache["refreshing"] = False
        except Exception as e:
            print(f"⚠️ /api/stats error: {_redact_log(e)}")
            with _stats_lock:
                _stats_cache["refreshing"] = False

    resp = app.response_class(json_dumps(data), mimetype="application/json")
    resp.headers["Cache-Control"] = "public, max-age=60"
    return resp

@app.route('/api/health')
def api_health():
    data = {
        "status": "healthy",
        "uptime_seconds": round(time.time() - _START_TIME, 1),
        "memory_rss_mb": get_memory_mb(),
        "timestamp": int(time.time())
    }
    resp = app.response_class(json_dumps(data), mimetype="application/json")
    return resp

def _is_guild_authorized(perms_int: int, is_owner: bool) -> bool:
    """Valida permisos estrictos: ADMINISTRATOR (0x8) o OWNER del servidor."""
    return bool(perms_int & 0x8) or bool(is_owner)

# ─── Dashboard API Endpoints (Discord OAuth2 Secured) ────────────────────────
@app.route('/api/auth/start', methods=["GET", "OPTIONS"])
def api_auth_start():
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))
    denied = _require_origin()
    if denied:
        return denied
    _purge_expired_sessions()
    try:
        state = _new_dashboard_state()
    except SessionSecurityError:
        logger.error("No se pudo persistir el estado OAuth del dashboard")
        return _cors(jsonify(ok=False, error="Servicio de sesión no disponible")), 503
    origin = request.headers.get("Origin", "").rstrip("/")
    redirect_uri = f"{origin}/dashboard" if APP_ENV != "production" and origin in ALLOWED_ORIGINS else _dashboard_redirect_uri()
    params = urlencode({"client_id": APPLICATION_ID, "redirect_uri": redirect_uri,
                        "response_type": "code", "scope": "identify guilds", "state": state})
    return _cors(jsonify(ok=True, auth_url=f"https://discord.com/api/oauth2/authorize?{params}"))


@app.route('/api/auth/token', methods=["POST", "OPTIONS"])
def api_auth_token():
    """Intercambia code validado por sesión opaca; navegador nunca recibe OAuth token."""
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))
    denied = _require_origin()
    if denied:
        return denied
    if not request.is_json:
        logger.warning("OAuth dashboard rejected: invalid request content type")
        return _cors(jsonify(ok=False, error="Solicitud OAuth inválida")), 400
    body = request.get_json(silent=True)
    code = body.get("code") if isinstance(body, dict) else None
    state = body.get("state") if isinstance(body, dict) else None
    redirect_uri = body.get("redirect_uri") if isinstance(body, dict) else None
    if not isinstance(body, dict) or not isinstance(state, str) or not isinstance(redirect_uri, str):
        logger.warning("OAuth dashboard rejected: missing request fields")
        return _cors(jsonify(ok=False, error="Solicitud OAuth inválida")), 400
    if redirect_uri not in _dashboard_redirects():
        logger.warning("OAuth dashboard rejected: redirect URI mismatch")
        return _cors(jsonify(ok=False, error="Redirect URI no permitida")), 400
    if not isinstance(code, str) or not (8 <= len(code) <= 512):
        logger.warning("OAuth dashboard rejected: authorization code format")
        return _cors(jsonify(ok=False, error="Código de autorización faltante")), 400
    if not DISCORD_CLIENT_SECRET:
        return _cors(jsonify(ok=False, error="Servicio OAuth no disponible")), 500
    if not _session_cipher or not SUPABASE_URL or not SUPABASE_KEY:
        return _cors(jsonify(ok=False, error="Servicio de sesión no disponible")), 503
    try:
        if not _consume_dashboard_state(state):
            logger.warning("OAuth dashboard rejected: state invalid or already consumed")
            return _cors(jsonify(ok=False, error="Solicitud OAuth caducada o inválida")), 400
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Servicio de sesión no disponible")), 503

    data = {
        "client_id": APPLICATION_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        r = requests.post("https://discord.com/api/v10/oauth2/token", data=data, headers=headers, timeout=8)
        if r.status_code != 200:
            logger.warning("OAuth dashboard rejected by Discord token endpoint: status %s", r.status_code)
            return _cors(jsonify(ok=False, error="Discord rechazó el código de autorización")), 400
        token_data = r.json()
        granted_scopes = token_data.get("scope", "")
        if isinstance(granted_scopes, str):
            granted_scopes = granted_scopes.split()
        elif not isinstance(granted_scopes, list) or not all(isinstance(scope, str) for scope in granted_scopes):
            granted_scopes = []
        if set(granted_scopes or ()) != {"identify", "guilds"}:
            safe_scopes = ",".join(sorted(set(granted_scopes or ()))) or "none"
            logger.warning("OAuth dashboard rejected: unexpected scopes (%s)", safe_scopes)
            return _cors(jsonify(ok=False, error="Scopes OAuth no permitidos")), 400
        access_token = token_data.get("access_token")
        if not access_token:
            logger.warning("OAuth dashboard rejected: Discord response without access token")
            return _cors(jsonify(ok=False, error="No se pudo obtener la sesión")), 400
        user_res = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bearer {access_token}"}, timeout=6)
        user_info = user_res.json() if user_res.status_code == 200 else {}
        if not user_info.get("id"):
            return _cors(jsonify(ok=False, error="No se pudo validar la sesión")), 401
        refresh_token = token_data.get("refresh_token") or ""
        if not refresh_token:
            logger.warning("OAuth dashboard rejected: Discord response without refresh token")
            return _cors(jsonify(ok=False, error="Discord no devolvió renovación segura")), 502
        expires_at = datetime.fromtimestamp(time.time() + max(int(token_data.get("expires_in", 3600)), 60), timezone.utc)
        csrf_token = secrets.token_urlsafe(32)
        session_id, session_row = new_session(_session_cipher, user_info["id"], access_token,
                                              refresh_token, expires_at, csrf_token)
        if not _sb_upsert("dashboard_sessions", session_row):
            logger.error("No se pudo persistir sesión OAuth")
            return _cors(jsonify(ok=False, error="No se pudo guardar la sesión")), 503
        response = make_response(_cors(jsonify(ok=True, user=_public_discord_user(user_info))))
        response.set_cookie(SESSION_COOKIE, session_id, max_age=SESSION_TTL, httponly=True,
                            secure=_session_cookie_secure(), samesite="Lax", path="/")
        return response
    except (requests.RequestException, ValueError):
        logger.warning("OAuth dashboard failed while contacting Discord")
        return _cors(jsonify(ok=False, error="Error al autenticar con Discord")), 502

@app.route('/api/auth/me', methods=["GET", "OPTIONS"])
def api_auth_me():
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))
    try:
        bundle = _session_credentials()
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Servicio de sesión no disponible")), 503
    if not bundle:
        message = "Sesión expirada" if request.cookies.get(SESSION_COOKIE) else "Inicio de sesión requerido"
        return _cors(jsonify(ok=False, error=message)), 401
    try:
        user = _fetch_discord_user(bundle["access_token"])
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Discord no disponible temporalmente")), 503
    if not user:
        _invalidate_request_session()
        return _cors(jsonify(ok=False, error="Sesión expirada")), 401
    return _cors(jsonify(ok=True, user=_public_discord_user(user), csrf_token=bundle["csrf_token"]))

@app.route('/api/auth/logout', methods=["POST", "OPTIONS"])
def api_auth_logout():
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))
    denied = _require_origin()
    if denied:
        return denied
    session_id = request.cookies.get(SESSION_COOKIE, "")
    try:
        session_hash = None
        if session_id and _session_cipher:
            try:
                session_hash = _session_cipher.hash_id(session_id)
            except SessionSecurityError:
                session_hash = None
        session = _require_session()
        if session_id and session and not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), session[2]["csrf_token"]):
            return _cors(jsonify(ok=False, error="CSRF inválido")), 403
        if session_hash:
            _invalidate_session(session_hash)
        if session and session[2].get("access_token") and DISCORD_CLIENT_SECRET:
            try:
                requests.post("https://discord.com/api/v10/oauth2/token/revoke", data={
                    "client_id": APPLICATION_ID, "client_secret": DISCORD_CLIENT_SECRET,
                    "token": session[2]["access_token"]
                }, timeout=6)
            except requests.RequestException:
                pass
            _clear_discord_cache(session[2]["access_token"])
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="No se pudo invalidar la sesión")), 503
    response = make_response(_cors(jsonify(ok=True)))
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="Lax", secure=_session_cookie_secure())
    return response

@app.route('/api/auth/guilds', methods=["GET", "OPTIONS"])
def api_auth_guilds():
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))
    try:
        token = _session_token()
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Servicio de sesión no disponible")), 503
    if not token:
        return _cors(jsonify(ok=False, error="Sesión expirada")), 401
    try:
        guilds = _fetch_discord_guilds(token)
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Discord no disponible temporalmente")), 503
    if guilds is None:
        _invalidate_request_session()
        return _cors(jsonify(ok=False, error="Sesión expirada")), 401

    user_guilds = []
    for g in guilds:
        perms = int(g.get("permissions", 0))
        is_owner = g.get("owner", False)
        is_admin = _is_guild_authorized(perms, is_owner)
        can_invite = bool(is_owner or (perms & 0x8) == 0x8 or (perms & 0x20) == 0x20)
        user_guilds.append({
            "id": str(g.get("id")),
            "name": g.get("name"),
            "icon": g.get("icon"),
            "owner": is_owner,
            "permissions": perms,
            "is_admin": is_admin,
            "can_invite": can_invite
        })

    if user_guilds and SUPABASE_URL and SUPABASE_KEY:
        gids = [g["id"] for g in user_guilds]
        try:
            rows = _sb_select("settings", {"guild_id": f"in.({','.join(gids)})"})
            settings_map = {str(s["guild_id"]): s for s in (rows or [])}
            for g in user_guilds:
                g["config"] = settings_map.get(g["id"])
                g["has_bot"] = g["id"] in settings_map
        except Exception:
            pass

    # Filtrar servidores ruidosos (paridad con Werewolf):
    # Solo mostrar servidores donde el bot ya está dentro O donde el usuario tiene permisos para invitarlo (can_invite)
    dashboard_guilds = [
        g for g in user_guilds
        if g.get("has_bot", False) or g.get("can_invite", False)
    ]

    # Servidores con el bot instalado primero, luego por permisos de admin y alfabético
    dashboard_guilds.sort(key=lambda x: (not x.get("has_bot", False), not x.get("is_admin", False), x.get("name", "").lower()))

    return _cors(jsonify(ok=True, guilds=dashboard_guilds))

@app.route('/api/guild/<guild_id>/channels', methods=["GET", "OPTIONS"])
def api_guild_channels(guild_id: str):
    """Devuelve los canales de texto del servidor para poblar el dropdown de configuración."""
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))
    
    if not _valid_guild_id(guild_id):
        return _cors(jsonify(ok=False, error="Servidor inválido")), 400
    try:
        token = _session_token()
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Servicio de sesión no disponible")), 503
    if not token:
        return _cors(jsonify(ok=False, error="Sesión expirada")), 401
    try:
        guilds = _fetch_discord_guilds(token)
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Discord no disponible temporalmente")), 503
    if guilds is None:
        _invalidate_request_session()
        return _cors(jsonify(ok=False, error="Sesión expirada")), 401
    
    matching = next((g for g in guilds if str(g.get("id")) == str(guild_id)), None)
    if not matching or not _is_guild_authorized(int(matching.get("permissions", 0)), matching.get("owner", False)):
        return _cors(jsonify(ok=False, error="Permisos insuficientes")), 403

    try:
        channels = _fetch_bot_channels(guild_id)
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Canales de Discord no disponibles temporalmente")), 503

    return _cors(jsonify(ok=True, channels=channels))
            
_cache_invalidator = None

def set_cache_invalidator(fn):
    """Permite registrar un callback para invalidar las cachés de memoria del bot."""
    global _cache_invalidator
    _cache_invalidator = fn

_bot_status_provider = None

def set_bot_status_provider(fn):
    """Permite registrar un callback para consultar métricas del bot de Discord."""
    global _bot_status_provider
    _bot_status_provider = fn

# Caché de estado general del sistema (15s TTL)
_system_status_cache = {"ts": 0.0, "data": None}
_SYSTEM_STATUS_TTL = 15

# Caché de perfiles de autor de Discord (2h TTL, máx 5000 entradas)
_author_profile_lock = Lock()
_author_profile_cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_AUTHOR_PROFILE_TTL = 7200
_MAX_AUTHOR_CACHE = 5000

def _format_uptime(seconds: int) -> str:
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {secs}s"

def _fetch_author_profile_cached(author_id: str) -> dict:
    """Obtiene username, global_name y avatar_url de un usuario de Discord con caché en RAM."""
    aid = str(author_id)
    now = time.time()

    with _author_profile_lock:
        if aid in _author_profile_cache:
            ts, profile = _author_profile_cache[aid]
            if now - ts < _AUTHOR_PROFILE_TTL:
                _author_profile_cache.move_to_end(aid)
                return profile

    fallback_name = f"Usuario {aid[-4:] if len(aid) >= 4 else aid}"
    profile = {
        "username": fallback_name,
        "global_name": fallback_name,
        "avatar_url": None
    }

    if DISCORD_BOT_TOKEN and aid.isdigit():
        try:
            r = requests.get(
                f"https://discord.com/api/v10/users/{aid}",
                headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"},
                timeout=3.5
            )
            if r.status_code == 200:
                data = r.json()
                username = data.get("username") or fallback_name
                global_name = data.get("global_name") or username
                avatar_hash = data.get("avatar")
                avatar_url = f"https://cdn.discordapp.com/avatars/{aid}/{avatar_hash}.png" if avatar_hash else None
                profile = {
                    "username": username,
                    "global_name": global_name,
                    "avatar_url": avatar_url
                }
        except Exception:
            pass

    with _author_profile_lock:
        _author_profile_cache[aid] = (now, profile)
        if len(_author_profile_cache) > _MAX_AUTHOR_CACHE:
            _author_profile_cache.popitem(last=False)

    return profile

@app.route('/api/guild/<guild_id>/config', methods=["GET", "POST", "OPTIONS"])
def api_guild_config(guild_id: str):
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))
    
    if not _valid_guild_id(guild_id):
        return _cors(jsonify(ok=False, error="Servidor inválido")), 400
    if request.method == "POST":
        denied = _require_origin()
        if denied:
            return denied
    try:
        token = _session_token()
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Servicio de sesión no disponible")), 503
    if not token:
        return _cors(jsonify(ok=False, error="Sesión expirada")), 401
    try:
        guilds = _fetch_discord_guilds(token)
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Discord no disponible temporalmente")), 503
    if guilds is None:
        _invalidate_request_session()
        return _cors(jsonify(ok=False, error="Sesión expirada")), 401
    
    matching = next((g for g in guilds if str(g.get("id")) == str(guild_id)), None)
    if not matching or not _is_guild_authorized(int(matching.get("permissions", 0)), matching.get("owner", False)):
        return _cors(jsonify(ok=False, error="Permisos insuficientes en este servidor")), 403

    if request.method == "GET":
        try:
            cfg = _sb_select_required("settings", {"guild_id": f"eq.{guild_id}"})
        except SessionSecurityError:
            return _cors(jsonify(ok=False, error="Base de datos no disponible temporalmente")), 503
        data = cfg[0] if cfg else {"guild_id": guild_id, "skullboard_channel_id": "0", "min_skulls": 1, "prefix": "sk!"}
        if data.get("skullboard_channel_id") is not None:
            data["skullboard_channel_id"] = str(data["skullboard_channel_id"])
        return _cors(jsonify(ok=True, config=data))

    if request.method == "POST":
        try:
            session = _require_session()
        except SessionSecurityError:
            return _cors(jsonify(ok=False, error="Servicio de sesión no disponible")), 503
        if not session or not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), session[2]["csrf_token"]):
            return _cors(jsonify(ok=False, error="CSRF inválido")), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _cors(jsonify(ok=False, error="JSON inválido")), 400
        try:
            min_skulls = max(1, min(int(body.get("min_skulls", 1)), 50))
            pin_threshold = max(0, min(int(body.get("pin_threshold", 0)), 50))
        except (TypeError, ValueError):
            return _cors(jsonify(ok=False, error="Configuración numérica inválida")), 400
        prefix = re.sub(r'[\r\n\s]+', '', str(body.get("prefix", "sk!")))[:10] or "sk!"
        channel_id_raw = str(body.get("skullboard_channel_id") or "0").strip()
        if channel_id_raw in ("", "0"):
            channel_id = 0
        elif re.match(r'^[0-9]{17,21}$', channel_id_raw):
            channel_id = int(channel_id_raw)
        else:
            return _cors(jsonify(ok=False, error="ID de canal inválido. Debe ser un Snowflake numérico de Discord (17-21 dígitos).")), 400

        try:
            if not _channel_is_available_to_bot(guild_id, channel_id):
                return _cors(jsonify(ok=False, error="El bot no puede publicar en ese canal")), 400
        except SessionSecurityError:
            return _cors(jsonify(ok=False, error="Canales de Discord no disponibles temporalmente")), 503

        payload = {
            "guild_id": str(guild_id),
            "min_skulls": min_skulls,
            "prefix": prefix,
            "skullboard_channel_id": channel_id,
            "pin_threshold": pin_threshold
        }
        success = _sb_upsert("settings", payload)
        if success:
            if _cache_invalidator:
                try:
                    _cache_invalidator(guild_id)
                except Exception:
                    pass
            payload["skullboard_channel_id"] = str(payload["skullboard_channel_id"])
            return _cors(jsonify(ok=True, config=payload))
        return _cors(jsonify(ok=False, error="Error al guardar configuración")), 500

# [v2.5.0 Spec] Ruta global desactivada temporalmente (desacople de UI y privacidad)
# @app.route('/api/leaderboard/global', methods=["GET", "OPTIONS"])
# def api_leaderboard_global():
#     """Devuelve los mensajes con más calaveras a nivel global de forma pública."""
#     if request.method == "OPTIONS":
#         return _cors(app.response_class(status=204))
#     
#     msgs = _sb_select("tracked_messages", {
#         "order": "skull_count.desc",
#         "limit": 20
#     })
#     return _cors(jsonify(ok=True, messages=msgs))

@app.route('/api/status', methods=["GET", "OPTIONS"])
def api_status():
    """Devuelve el estado en tiempo real del Bot, API REST y Base de Datos (Supabase)."""
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))

    now = time.time()
    if _system_status_cache["data"] and (now - _system_status_cache["ts"] < _SYSTEM_STATUS_TTL):
        return _cors(jsonify(_system_status_cache["data"]))

    # 1. Base de datos: latencia y conectividad
    db_start = time.time()
    db_ok = False
    try:
        if SUPABASE_URL and SUPABASE_KEY:
            _sb_select_required("settings", {"limit": 1})
            db_ok = True
        db_latency_ms = round((time.time() - db_start) * 1000, 1)
    except Exception:
        db_latency_ms = round((time.time() - db_start) * 1000, 1)
        db_ok = False

    # 2. Bot de Discord
    if _bot_status_provider:
        try:
            bot_info = _bot_status_provider()
        except Exception:
            bot_info = {"status": "degraded", "online": False, "latency_ms": None, "shards": None,
                        "uptime_seconds": None, "guilds": None}
    else:
        bot_info = {"status": "unknown", "online": False, "latency_ms": None, "shards": None,
                    "uptime_seconds": None, "guilds": None}

    bot_uptime_sec = bot_info.get("uptime_seconds", 0)
    bot_status_str = bot_info.get("status") or ("operational" if bot_info.get("online", False) else "degraded")
    if bot_status_str not in {"operational", "degraded", "unknown"}:
        bot_status_str = "unknown"

    # 3. API REST
    api_status_str = "operational"

    status_data = {
        "ok": True,
        "all_operational": (bot_status_str == "operational" and db_ok),
        "timestamp": int(now),
        "bot": {
            "status": bot_status_str,
            "online": bot_info.get("online", False),
            "latency_ms": bot_info.get("latency_ms"),
            "shards": bot_info.get("shards"),
            "guilds": bot_info.get("guilds"),
            "uptime_seconds": bot_uptime_sec,
            "uptime_formatted": _format_uptime(bot_uptime_sec) if isinstance(bot_uptime_sec, (int, float)) else None
        },
        "database": {
            "status": "operational" if db_ok else "degraded",
            "latency_ms": db_latency_ms,
            "provider": "Supabase PostgreSQL"
        },
        "api": {
            "status": api_status_str,
            "runtime": "Python / Flask Multi-threaded",
            "cache_ttl_seconds": _SYSTEM_STATUS_TTL
        }
    }

    _system_status_cache["ts"] = now
    _system_status_cache["data"] = status_data

    return _cors(jsonify(status_data))

@app.route('/api/guild/<guild_id>/leaderboard/public', methods=["GET", "OPTIONS"])
def api_guild_leaderboard_public(guild_id: str):
    """Devuelve el leaderboard público de un servidor con autores resueltos y jump URLs."""
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))
    if not _valid_guild_id(guild_id):
        return _cors(jsonify(ok=False, error="Servidor inválido")), 400

    msgs = _sb_select("tracked_messages", {
        "guild_id": f"eq.{guild_id}",
        "order": "skull_count.desc",
        "limit": 25
    }) or []

    starboard_channel_id = ""
    try:
        sett = _sb_select("settings", {"guild_id": f"eq.{guild_id}"})
        if sett and sett[0].get("skullboard_channel_id"):
            starboard_channel_id = str(sett[0]["skullboard_channel_id"])
    except Exception:
        pass

    enriched = []
    for m in msgs:
        item = dict(m)
        author_id = str(item.get("author_id") or "")
        profile = _fetch_author_profile_cached(author_id) if author_id else {}

        item["author_username"] = profile.get("username") or f"Usuario {author_id[-4:] if len(author_id) >= 4 else author_id}"
        item["author_global_name"] = profile.get("global_name") or item["author_username"]
        item["author_avatar_url"] = profile.get("avatar_url")

        uname_lower = str(item["author_username"]).lower().strip()
        gname_lower = str(item["author_global_name"]).lower().strip()
        if (
            uname_lower in ("deleted user", "deleted_user", "usuario desconocido")
            or uname_lower.startswith("deleted user")
            or gname_lower in ("deleted user", "deleted_user", "usuario desconocido")
            or gname_lower.startswith("deleted user")
        ):
            continue

        orig_chan = str(item.get("channel_id") or "")
        orig_mid = str(item.get("message_id") or "")
        sb_msg_id = str(item.get("skullboard_message_id") or "")

        # Prioridad de enlace: Si existe el mensaje en Skullboard oficial, enlazar a él
        if starboard_channel_id and sb_msg_id:
            target_chan = starboard_channel_id
            target_mid = sb_msg_id
        elif orig_chan and orig_mid:
            target_chan = orig_chan
            target_mid = orig_mid
        elif orig_mid and starboard_channel_id:
            target_chan = starboard_channel_id
            target_mid = orig_mid
        else:
            target_chan = orig_chan
            target_mid = orig_mid

        if target_chan and target_mid:
            item["jump_url"] = f"https://discord.com/channels/{guild_id}/{target_chan}/{target_mid}"
            item["app_jump_url"] = f"discord://-/channels/{guild_id}/{target_chan}/{target_mid}"
        else:
            item["jump_url"] = None
            item["app_jump_url"] = None

        if starboard_channel_id and sb_msg_id:
            item["skullboard_jump_url"] = f"https://discord.com/channels/{guild_id}/{starboard_channel_id}/{sb_msg_id}"
            item["app_skullboard_jump_url"] = f"discord://-/channels/{guild_id}/{starboard_channel_id}/{sb_msg_id}"
        else:
            item["skullboard_jump_url"] = None
            item["app_skullboard_jump_url"] = None

        if orig_chan and orig_mid:
            item["original_jump_url"] = f"https://discord.com/channels/{guild_id}/{orig_chan}/{orig_mid}"
            item["app_original_jump_url"] = f"discord://-/channels/{guild_id}/{orig_chan}/{orig_mid}"
        else:
            item["original_jump_url"] = None
            item["app_original_jump_url"] = None

        if orig_mid and orig_mid.isdigit() and len(orig_mid) >= 15:
            try:
                ms = (int(orig_mid) >> 22) + 1420070400000
                item["timestamp_ms"] = ms
            except Exception:
                item["timestamp_ms"] = None
        else:
            item["timestamp_ms"] = None

        enriched.append(item)

    return _cors(jsonify(ok=True, messages=enriched))

@app.route('/api/guild/<guild_id>/leaderboard/users', methods=["GET", "OPTIONS"])
def api_guild_leaderboard_users(guild_id: str):
    """Devuelve el ranking acumulado de usuarios únicos en el servidor mediante la RPC get_guild_leaderboard."""
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))
    if not _valid_guild_id(guild_id):
        return _cors(jsonify(ok=False, error="Servidor inválido")), 400

    try:
        limit = min(max(int(request.args.get("limit", 25)), 1), 100)
    except (TypeError, ValueError):
        return _cors(jsonify(ok=False, error="Límite inválido")), 400
    rows = _sb_rpc("get_guild_leaderboard", {"p_guild_id": str(guild_id), "p_limit": limit}) or []

    users = []
    for r in rows:
        author_id = str(r.get("author_id") or "")
        profile = _fetch_author_profile_cached(author_id) if author_id else {}
        author_username = profile.get("username") or f"Usuario {author_id[-4:] if len(author_id) >= 4 else author_id}"
        author_global_name = profile.get("global_name") or author_username
        author_avatar_url = profile.get("avatar_url")

        uname_lower = author_username.lower().strip()
        gname_lower = author_global_name.lower().strip()
        if (
            uname_lower in ("deleted user", "deleted_user", "usuario desconocido")
            or uname_lower.startswith("deleted user")
            or gname_lower in ("deleted user", "deleted_user", "usuario desconocido")
            or gname_lower.startswith("deleted user")
        ):
            continue

        users.append({
            "author_id": author_id,
            "author_username": author_username,
            "author_global_name": author_global_name,
            "author_avatar_url": author_avatar_url,
            "total_skulls": int(r.get("total_skulls") or 0),
            "message_count": int(r.get("message_count") or 0)
        })

    return _cors(jsonify(ok=True, users=users))

@app.route('/api/guild/<guild_id>/my-messages', methods=["GET", "OPTIONS"])
def api_guild_my_messages(guild_id: str):
    """Devuelve los mensajes destacados creados por el usuario con jump URLs."""
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))
    if not _valid_guild_id(guild_id):
        return _cors(jsonify(ok=False, error="Servidor inválido")), 400

    try:
        token = _session_token()
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Servicio de sesión no disponible")), 503
    if not token:
        return _cors(jsonify(ok=False, error="Sesión expirada")), 401
    try:
        guilds = _fetch_discord_guilds(token)
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Discord no disponible temporalmente")), 503
    matching = next((g for g in (guilds or []) if str(g.get("id")) == str(guild_id)), None)
    if guilds is None:
        _invalidate_request_session()
        return _cors(jsonify(ok=False, error="Sesión expirada")), 401
    if not matching:
        return _cors(jsonify(ok=False, error="No perteneces a este servidor")), 403
    try:
        user = _fetch_discord_user(token)
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Discord no disponible temporalmente")), 503
    if not user:
        return _cors(jsonify(ok=False, error="Sesión expirada")), 401

    user_id = str(user.get("id"))

    try:
        stats_res = _sb_rpc_required("get_guild_user_stats", {"p_guild_id": str(guild_id), "p_author_id": user_id})
        stats = stats_res[0] if (isinstance(stats_res, list) and stats_res) else {"total_messages": 0, "total_skulls": 0}
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Base de datos no disponible temporalmente")), 503

    try:
        msgs = _sb_select_required("tracked_messages", {
            "guild_id": f"eq.{guild_id}",
            "author_id": f"eq.{user_id}",
            "order": "skull_count.desc",
            "limit": 50
        })
    except SessionSecurityError:
        return _cors(jsonify(ok=False, error="Base de datos no disponible temporalmente")), 503

    starboard_channel_id = ""
    try:
        sett = _sb_select("settings", {"guild_id": f"eq.{guild_id}"})
        if sett and sett[0].get("skullboard_channel_id"):
            starboard_channel_id = str(sett[0]["skullboard_channel_id"])
    except Exception:
        pass

    enriched_msgs = []
    for m in msgs:
        item = dict(m)
        orig_chan = str(item.get("channel_id") or "")
        orig_mid = str(item.get("message_id") or "")
        sb_msg_id = str(item.get("skullboard_message_id") or "")

        if starboard_channel_id and sb_msg_id:
            target_chan = starboard_channel_id
            target_mid = sb_msg_id
        elif orig_chan and orig_mid:
            target_chan = orig_chan
            target_mid = orig_mid
        elif orig_mid and starboard_channel_id:
            target_chan = starboard_channel_id
            target_mid = orig_mid
        else:
            target_chan = orig_chan
            target_mid = orig_mid

        if target_chan and target_mid:
            item["jump_url"] = f"https://discord.com/channels/{guild_id}/{target_chan}/{target_mid}"
            item["app_jump_url"] = f"discord://-/channels/{guild_id}/{target_chan}/{target_mid}"
        else:
            item["jump_url"] = None
            item["app_jump_url"] = None

        if starboard_channel_id and sb_msg_id:
            item["skullboard_jump_url"] = f"https://discord.com/channels/{guild_id}/{starboard_channel_id}/{sb_msg_id}"
            item["app_skullboard_jump_url"] = f"discord://-/channels/{guild_id}/{starboard_channel_id}/{sb_msg_id}"
        else:
            item["skullboard_jump_url"] = None
            item["app_skullboard_jump_url"] = None

        if orig_chan and orig_mid:
            item["original_jump_url"] = f"https://discord.com/channels/{guild_id}/{orig_chan}/{orig_mid}"
            item["app_original_jump_url"] = f"discord://-/channels/{guild_id}/{orig_chan}/{orig_mid}"
        else:
            item["original_jump_url"] = None
            item["app_original_jump_url"] = None

        if orig_mid and orig_mid.isdigit() and len(orig_mid) >= 15:
            try:
                ms = (int(orig_mid) >> 22) + 1420070400000
                item["timestamp_ms"] = ms
            except Exception:
                item["timestamp_ms"] = None
        else:
            item["timestamp_ms"] = None

        enriched_msgs.append(item)

    return _cors(jsonify(
        ok=True,
        total_skulls=int(stats.get("total_skulls") or 0),
        total_messages=int(stats.get("total_messages") or 0),
        messages=enriched_msgs
    ))

@app.route('/api/og')
def api_og():
    srv = _sb_count("settings") or 100
    hl  = _sb_count("tracked_messages") or 500
    svg = f"""<svg width="1200" height="630" viewBox="0 0 1200 630" xmlns="http://www.w3.org/2000/svg">
        <defs>
            <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#0b0a10"/>
                <stop offset="50%" stop-color="#12101b"/>
                <stop offset="100%" stop-color="#08070d"/>
            </linearGradient>
            <linearGradient id="violet" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#a78bfa"/>
                <stop offset="100%" stop-color="#7c3aed"/>
            </linearGradient>
        </defs>
        <rect width="1200" height="630" fill="url(#bg)"/>
        <circle cx="950" cy="150" r="300" fill="#7c3aed" opacity="0.15"/>
        <circle cx="200" cy="500" r="250" fill="#34d399" opacity="0.1"/>
        <rect x="24" y="24" width="1152" height="582" rx="28" fill="none" stroke="rgba(255,255,255,0.12)" stroke-width="2"/>
        <text x="80" y="110" font-family="-apple-system, sans-serif" font-size="36" font-weight="bold" fill="#ffffff">💀 SkullBoard</text>
        <text x="80" y="240" font-family="-apple-system, sans-serif" font-size="54" font-weight="800" fill="#ededf2">El Starboard Definitivo</text>
        <text x="80" y="310" font-family="-apple-system, sans-serif" font-size="54" font-weight="800" fill="url(#violet)">para Servidores de Discord</text>
        <text x="80" y="380" font-family="-apple-system, sans-serif" font-size="24" fill="#94a3b8">Rankings en vivo, Auto-Pin de récords y Panel Web OAuth2.</text>
        <g transform="translate(80, 450)">
            <rect width="280" height="88" rx="16" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.12)"/>
            <text x="24" y="42" font-family="-apple-system, sans-serif" font-size="30" font-weight="bold" fill="#ffffff">{srv:,}</text>
            <text x="24" y="68" font-family="-apple-system, sans-serif" font-size="15" fill="#94a3b8">Servidores Activos</text>
        </g>
        <g transform="translate(390, 450)">
            <rect width="320" height="88" rx="16" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.12)"/>
            <text x="24" y="42" font-family="-apple-system, sans-serif" font-size="30" font-weight="bold" fill="#34d399">{hl:,}</text>
            <text x="24" y="68" font-family="-apple-system, sans-serif" font-size="15" fill="#94a3b8">Mensajes Destacados</text>
        </g>
        <g transform="translate(740, 450)">
            <rect width="380" height="88" rx="16" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.12)"/>
            <text x="24" y="42" font-family="-apple-system, sans-serif" font-size="30" font-weight="bold" fill="#a78bfa">v2.5.0</text>
            <text x="24" y="68" font-family="-apple-system, sans-serif" font-size="15" fill="#94a3b8">Dashboard Web · AutoShardedBot</text>
        </g>
    </svg>"""
    resp = app.response_class(svg, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "public, max-age=120"
    return resp

@app.route('/api/contact', methods=["POST", "OPTIONS"])
def api_contact():
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))

    data = request.get_json(silent=True) or {}
    if (data.get("website") or "").strip():  # honeypot
        return _cors(jsonify(ok=True))

    raw_name = (data.get("name") or "").strip()[:80]
    raw_email = (data.get("email") or "").strip()[:120]
    raw_msg = (data.get("message") or "").strip()[:4000]

    if len(raw_msg) < 5:
        return _cors(jsonify(ok=False, error="El mensaje es demasiado corto.")), 400

    # Sanitización estricta anti CRLF Injection
    name = re.sub(r'[\r\n]+', ' ', raw_name)
    email = re.sub(r'[\r\n\s]+', '', raw_email)

    ip = _get_real_ip()
    now = time.time()

    with _contact_lock:
        # Rate limit por IP (30s)
        if now - _contact_last.get(ip, 0) < 30:
            return _cors(jsonify(ok=False, error="Espera un momento antes de enviar otro mensaje.")), 429

        # Rate limit global (10 correos por minuto)
        global _global_contact_history
        _global_contact_history = [t for t in _global_contact_history if now - t < 60]
        if len(_global_contact_history) >= _MAX_GLOBAL_PER_MINUTE:
            return _cors(jsonify(ok=False, error="Servidor ocupado. Inténtalo en un momento.")), 429

        _contact_last[ip] = now
        _contact_last.move_to_end(ip)
        _global_contact_history.append(now)

        if len(_contact_last) > _MAX_CONTACT_IPS:
            _contact_last.popitem(last=False)

    if not RESEND_API_KEY:
        return _cors(jsonify(ok=False, error="El envío de correo no está configurado.")), 500

    safe_name = html.escape(name or 'Anónimo')
    safe_email = html.escape(email or '—')
    safe_msg = html.escape(raw_msg)

    html_content = (
        "<h2>Nuevo mensaje de contacto (SkullBoard)</h2>"
        f"<p><strong>De:</strong> {safe_name}</p>"
        f"<p><strong>Email:</strong> {safe_email}</p><hr/>"
        f"<p style='white-space:pre-wrap'>{safe_msg}</p>"
    )
    payload = {
        "from": CONTACT_FROM,
        "to": [CONTACT_TO],
        "subject": f"Contacto SkullBoard — {name or 'Anónimo'}",
        "html": html_content
    }
    if email and EMAIL_REGEX.match(email):
        payload["reply_to"] = email

    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=8
        )
        if r.status_code >= 300:
            print(f"⚠️ Resend error HTTP {r.status_code}")
            return _cors(jsonify(ok=False, error="No se pudo enviar el mensaje.")), 502
    except requests.RequestException as e:
        print(f"⚠️ /api/contact red: {_redact_log(e)}")
        return _cors(jsonify(ok=False, error="No se pudo contactar con el servidor de correo.")), 502

    return _cors(jsonify(ok=True))

@app.route('/<path:filename>')
def serve_legal_files(filename):
    # Si viene con .html, redirigir permanentemente (301) a la URL limpia
    if filename.endswith(".html"):
        clean_name = filename[:-5]
        return redirect(f"/{clean_name}", code=301)

    try:
        # 1. Si existe el archivo directo (ej. styles.css, skullboard_icon.png, robots.txt, sitemap.xml)
        if os.path.isfile(os.path.join('legal', filename)):
            return send_from_directory('legal', filename)
        # 2. Si existe con terminación .html (ej. /privacy -> legal/privacy.html)
        html_name = f"{filename}.html"
        if os.path.isfile(os.path.join('legal', html_name)):
            return send_from_directory('legal', html_name)
    except Exception:
        pass
    return "❌ Archivo no encontrado.", 404

# ── OAuth2: protección anti-CSRF ──────────────────────────────────────────────
def _new_state() -> str:
    now = time.time()
    with _oauth_lock:
        expired = [s for s, exp in _oauth_states.items() if exp < now]
        for s in expired:
            _oauth_states.pop(s, None)
        state = secrets.token_urlsafe(24)
        _oauth_states[state] = now + _OAUTH_STATE_TTL
        if len(_oauth_states) > _MAX_OAUTH_STATES:
            _oauth_states.popitem(last=False)
        return state

@app.route('/verify')
def verify():
    """Punto de entrada recomendado para vincular el rol de owner.
    Genera un `state` anti-CSRF y redirige a la autorización de Discord."""
    state  = _new_state()
    params = urlencode({
        "client_id":     APPLICATION_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         "identify role_connections.write",
        "state":         state,
        "prompt":        "consent",
    })
    return redirect(f"https://discord.com/api/oauth2/authorize?{params}")

@app.route('/callback')
def callback():
    code = request.args.get("code")
    state = request.args.get("state")

    if not code:
        return "❌ No se proporcionó el código de autorización.", 400

    # FIX CRÍTICO ANTI-CSRF: state es OBLIGATORIO
    if not state:
        return "❌ Falta el parámetro de seguridad (state). Inicia el proceso desde /verify.", 400

    with _oauth_lock:
        expiry = _oauth_states.pop(state, None)
    if expiry is None or expiry < time.time():
        return "❌ Sesión de verificación inválida o caducada. Empieza de nuevo desde /verify.", 400

    data = {
        "client_id": APPLICATION_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "scope": "identify role_connections.write"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        token_res = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers, timeout=8)
        if token_res.status_code != 200:
            return "❌ No se pudo completar la autorización con Discord.", 400
        access_token = token_res.json().get("access_token")
        if not access_token:
            return "❌ No se pudo obtener el token de acceso.", 400

        user_res = requests.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=8
        )
        if user_res.status_code != 200:
            return "❌ Error al obtener la información de usuario de Discord.", 400
        user_info = user_res.json()
    except (requests.RequestException, ValueError, Exception) as e:
        print(f"⚠️ Error de red OAuth2: {_redact_log(e)}")
        return "❌ Error al contactar con Discord. Inténtalo más tarde.", 502

    if str(user_info.get("id")) != OWNER_ID:
        return "❌ No estás autorizado para vincular este rol.", 403

    connection_url = f"https://discord.com/api/v10/users/@me/applications/{APPLICATION_ID}/role-connection"
    conn_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "platform_name": "Skullboard",
        "platform_username": "Owner",
        "metadata": {"is_owner": True}
    }
    try:
        assign_res = requests.put(connection_url, headers=conn_headers, json=payload, timeout=8)
        if assign_res.status_code in (200, 204):
            return "✅ Rol vinculado correctamente. Ya puedes cerrar esta ventana."
    except requests.RequestException as e:
        print(f"⚠️ Error asignando rol: {_redact_log(e)}")
        return "❌ Error al contactar con Discord. Inténtalo más tarde.", 502

    return "❌ No se pudo vincular el rol.", 400

def register_metadata():
    url = f"https://discord.com/api/v10/applications/{APPLICATION_ID}/role-connections/metadata"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    body = [
        {
            "key": "is_owner",
            "name": "Owner del bot",
            "description": "Este usuario es el propietario de Skullboard",
            "type": 7  # BOOLEAN
        }
    ]
    try:
        response = requests.put(url, headers=headers, json=body, timeout=8)
        print("📌 Metadata registrada:", response.status_code)
    except Exception as e:
        print(f"⚠️ Error registrando metadata: {_redact_log(e)}")

def run():
    try:
        register_metadata()
    except Exception as e:
        print(f"⚠️ Error al registrar metadata: {_redact_log(e)}")
    try:
        port = int(os.getenv("PORT", "8080"))
        app.run(host='0.0.0.0', port=port, threaded=True)
    except Exception as e:
        print(f"❌ Error al iniciar el servidor: {_redact_log(e)}")

def keep_alive():
    server = Thread(target=run, daemon=True)
    server.start()
