from flask import Flask, request, send_from_directory, redirect, jsonify
from threading import Thread
from urllib.parse import urlencode
import requests
import os
import secrets
import time
import json

app = Flask(__name__)

APPLICATION_ID = os.getenv("DISCORD_APPLICATION_ID", "1367463352774955059")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "https://skullboard-fqf1.onrender.com/callback")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Cache de stats públicas. ponytail: TTL 60s blinda Supabase — por mucho que
# recarguen la web o entren/salgan mensajes, máx 2 count-queries por minuto.
_stats_cache = {"ts": 0.0, "data": {"servers": None, "highlighted": None}}
_STATS_TTL = 60

def _sb_count(table: str):
    """Cuenta filas de una tabla vía REST (Content-Range), sin traer datos."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return None
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                 "Prefer": "count=exact", "Range": "0-0"},
        params={"select": "guild_id"}, timeout=8,
    )
    total = r.headers.get("Content-Range", "").split("/")[-1]
    return int(total) if total.isdigit() else None

@app.route('/')
def index():
    try:
        return send_from_directory('legal', 'index.html')
    except Exception:
        return "Hello, I am alive!"

@app.route('/api/stats')
def api_stats():
    now = time.time()
    cached = _stats_cache["data"]
    if now - _stats_cache["ts"] < _STATS_TTL and cached["servers"] is not None:
        data = cached
    else:
        try:
            data = {"servers": _sb_count("settings"), "highlighted": _sb_count("tracked_messages")}
            if data["servers"] is not None:
                _stats_cache["ts"] = now
                _stats_cache["data"] = data
        except Exception as e:
            print(f"⚠️ /api/stats error: {e}")
            data = cached  # degradar al último bueno (o nulls)
    resp = app.response_class(json.dumps(data), mimetype="application/json")
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "public, max-age=60"
    return resp

# ── Formulario de contacto (Resend) ───────────────────────────────────────────
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
CONTACT_TO   = "globalsupportpyt@gmail.com"
CONTACT_FROM = "SkullBoard <onboarding@resend.dev>"  # sin dominio: entrega solo a la cuenta Resend
_contact_last = {}  # ponytail: rate-limit por IP en memoria (proceso único). Crece con IPs; trivial.

def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

@app.route('/api/contact', methods=["POST", "OPTIONS"])
def api_contact():
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))

    data = request.get_json(silent=True) or {}
    if (data.get("website") or "").strip():  # honeypot: bots rellenan campo oculto
        return _cors(jsonify(ok=True))       # fingimos éxito, no enviamos

    name = (data.get("name") or "").strip()[:80]
    email = (data.get("email") or "").strip()[:120]
    msg = (data.get("message") or "").strip()[:4000]
    if len(msg) < 5:
        return _cors(jsonify(ok=False, error="El mensaje es demasiado corto.")), 400

    ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "")).split(",")[0].strip()
    now = time.time()
    if now - _contact_last.get(ip, 0) < 30:
        return _cors(jsonify(ok=False, error="Espera un momento antes de enviar otro mensaje.")), 429
    if not RESEND_API_KEY:
        return _cors(jsonify(ok=False, error="El envío de correo no está configurado.")), 500

    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = (
        "<h2>Nuevo mensaje de contacto (SkullBoard)</h2>"
        f"<p><strong>De:</strong> {esc(name or 'Anónimo')}</p>"
        f"<p><strong>Email:</strong> {esc(email or '—')}</p><hr/>"
        f"<p style='white-space:pre-wrap'>{esc(msg)}</p>"
    )
    payload = {"from": CONTACT_FROM, "to": [CONTACT_TO],
               "subject": f"Contacto SkullBoard — {name or 'Anónimo'}", "html": html}
    if "@" in email:
        payload["reply_to"] = email

    try:
        r = requests.post("https://api.resend.com/emails",
                          headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                          json=payload, timeout=10)
    except requests.RequestException as e:
        print(f"⚠️ /api/contact red: {e}")
        return _cors(jsonify(ok=False, error="No se pudo contactar con el servidor de correo.")), 502
    if r.status_code >= 300:
        print(f"⚠️ resend {r.status_code}: {r.text}")
        return _cors(jsonify(ok=False, error="No se pudo enviar el mensaje.")), 502

    _contact_last[ip] = now
    return _cors(jsonify(ok=True))

@app.route('/<path:filename>')
def serve_legal_files(filename):
    try:
        return send_from_directory('legal', filename)
    except Exception:
        return "❌ Archivo no encontrado.", 404

OWNER_ID = os.getenv("BOT_OWNER_ID", "561225979389804544")

# ── OAuth2: protección anti-CSRF ──────────────────────────────────────────────
# state -> epoch de caducidad. Solo se aceptan callbacks cuyo `state` emitimos
# nosotros desde /verify. Se limpian solos al validarse o expirar.
_oauth_states: dict = {}
_OAUTH_STATE_TTL = 600  # 10 minutos

def _new_state() -> str:
    now = time.time()
    for s, exp in list(_oauth_states.items()):
        if exp < now:
            _oauth_states.pop(s, None)
    state = secrets.token_urlsafe(24)
    _oauth_states[state] = now + _OAUTH_STATE_TTL
    return state

@app.route('/verify')
def verify():
    """Punto de entrada recomendado para vincular el rol de owner.
    Genera un `state` anti-CSRF y redirige a la autorización de Discord.
    (Configura esta URL como 'Linked Roles Verification URL' en el portal.)"""
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

# Linked Role Connection
@app.route('/callback')
def callback():
    code = request.args.get("code")
    if not code:
        return "❌ No se proporcionó el código de autorización.", 400

    # Validación anti-CSRF: si llega con state, debe ser uno emitido por /verify.
    state = request.args.get("state")
    if state is not None:
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
        token_res = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers, timeout=10)
    except requests.RequestException as e:
        print(f"⚠️ Error de red en intercambio de token: {e}")
        return "❌ Error al contactar con Discord. Inténtalo más tarde.", 502

    if token_res.status_code != 200:
        print(f"⚠️ Intercambio de token falló ({token_res.status_code}): {token_res.text}")
        return "❌ No se pudo completar la autorización.", 400

    access_token = token_res.json().get("access_token")
    if not access_token:
        return "❌ No se pudo completar la autorización.", 400

    try:
        user_info = requests.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        ).json()
    except requests.RequestException as e:
        print(f"⚠️ Error obteniendo usuario: {e}")
        return "❌ Error al contactar con Discord. Inténtalo más tarde.", 502

    if user_info.get("id") != OWNER_ID:  # ID del propietario del bot
        return "❌ No estás autorizado para vincular este rol.", 403

    connection_url = f"https://discord.com/api/v10/users/@me/applications/{APPLICATION_ID}/role-connection"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "platform_name": "Skullboard",
        "platform_username": "Owner",
        "metadata": {"is_owner": True}
    }
    try:
        assign_res = requests.put(connection_url, headers=headers, json=payload, timeout=10)
    except requests.RequestException as e:
        print(f"⚠️ Error asignando rol: {e}")
        return "❌ Error al contactar con Discord. Inténtalo más tarde.", 502

    if assign_res.status_code in (200, 204):
        return "✅ Rol vinculado correctamente. Ya puedes cerrar esta ventana."
    print(f"⚠️ Fallo al vincular rol ({assign_res.status_code}): {assign_res.text}")
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

    response = requests.put(url, headers=headers, json=body, timeout=10)
    print("📌 Metadata registrada:", response.status_code, response.text)

def run():
    try:
        register_metadata()
    except Exception as e:
        print(f"⚠️ Error al registrar metadata: {e}")
    try:
        # threaded=True: una petición lenta no bloquea el keep-alive de Render
        app.run(host='0.0.0.0', port=8080, threaded=True)
    except Exception as e:
        print(f"❌ Error al iniciar el servidor: {e}")

def keep_alive():
    server = Thread(target=run)
    server.start()
