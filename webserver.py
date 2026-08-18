from flask import Flask, request, send_from_directory, redirect, jsonify
from threading import Thread, Lock
from urllib.parse import urlencode
from collections import OrderedDict
import requests
import os
import secrets
import time
import json
import re
import html

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

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')

# ─── Security Headers ─────────────────────────────────────────────────────────
@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# ─── Thread-Safe Caches ───────────────────────────────────────────────────────
_stats_lock = Lock()
_stats_cache = {"ts": 0.0, "data": {"servers": None, "highlighted": None}}
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
        total = r.headers.get("Content-Range", "").split("/")[-1]
        return int(total) if total.isdigit() else None
    except Exception:
        return None

def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

def _get_real_ip() -> str:
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        ips = [i.strip() for i in xff.split(",") if i.strip()]
        if ips:
            return ips[0]
    return request.remote_addr or "127.0.0.1"

@app.route('/')
def index():
    try:
        return send_from_directory('legal', 'index.html')
    except Exception:
        return "Hello, I am alive!"

@app.route('/api/stats')
def api_stats():
    now = time.time()
    needs_refresh = False
    with _stats_lock:
        cached = _stats_cache["data"]
        if now - _stats_cache["ts"] >= _STATS_TTL or cached["servers"] is None:
            needs_refresh = True
            data = cached
        else:
            data = cached

    if needs_refresh:
        try:
            # Las llamadas HTTP se hacen FUERA del lock principal
            srv = _sb_count("settings")
            hl  = _sb_count("tracked_messages")
            if srv is not None:
                new_data = {"servers": srv, "highlighted": hl}
                with _stats_lock:
                    _stats_cache["ts"] = time.time()
                    _stats_cache["data"] = new_data
                data = new_data
        except Exception as e:
            print(f"⚠️ /api/stats error: {e}")

    resp = app.response_class(json.dumps(data), mimetype="application/json")
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "public, max-age=60"
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
            print(f"⚠️ Resend error {r.status_code}: {r.text}")
            return _cors(jsonify(ok=False, error="No se pudo enviar el mensaje.")), 502
    except requests.RequestException as e:
        print(f"⚠️ /api/contact red: {e}")
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
        print(f"⚠️ Error de red OAuth2: {e}")
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
        print(f"⚠️ Error asignando rol: {e}")
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
        print(f"⚠️ Error registrando metadata: {e}")

def run():
    try:
        register_metadata()
    except Exception as e:
        print(f"⚠️ Error al registrar metadata: {e}")
    try:
        port = int(os.getenv("PORT", "8080"))
        app.run(host='0.0.0.0', port=port, threaded=True)
    except Exception as e:
        print(f"❌ Error al iniciar el servidor: {e}")

def keep_alive():
    server = Thread(target=run, daemon=True)
    server.start()
