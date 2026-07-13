from flask import Flask, request, send_from_directory, redirect
from threading import Thread
from urllib.parse import urlencode
import requests
import os
import secrets
import time

app = Flask(__name__)

APPLICATION_ID = os.getenv("DISCORD_APPLICATION_ID", "1367463352774955059")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "https://skullboard-fqf1.onrender.com/callback")

@app.route('/')
def index():
    try:
        return send_from_directory('legal', 'index.html')
    except Exception:
        return "Hello, I am alive!"

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
