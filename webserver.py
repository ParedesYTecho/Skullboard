from flask import Flask, request
from threading import Thread
import requests
import os

app = Flask(__name__)

APPLICATION_ID = "1367463352774955059"
DISCORD_BOT_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI = "https://skullboard-fqf1.onrender.com/callback"

@app.route('/')
def index():
    return "Hello, I am alive!"

@app.route('/callback')
def callback():
    code = request.args.get("code")
    if not code:
        return "❌ No se proporcionó el código de autorización.", 400

    # Intercambiar código por access_token
    data = {
        "client_id": APPLICATION_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "scope": "identify role_connections.write"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    token_res = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers)

    if token_res.status_code != 200:
        return f"❌ Error obteniendo el token: {token_res.text}", 400

    access_token = token_res.json()["access_token"]

    # Obtener datos del usuario
    user_info = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    if user_info.get("id") != "561225979389804544": # ID del propietario del bot
        return "❌ No estás autorizado para vincular este rol.", 403

    # Asignar datos de rol
    connection_url = f"https://discord.com/api/v10/users/@me/applications/{APPLICATION_ID}/role-connection"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "platform_name": "Skullboard",
        "platform_username": "Owner",
        "metadata": {
            "is_owner": True
        }
    }

    assign_res = requests.put(connection_url, headers=headers, json=payload)

    if assign_res.status_code in [200, 204]:
        return "✅ Rol vinculado correctamente. Ya puedes cerrar esta ventana."
    else:
        return f"❌ Error al vincular el rol: {assign_res.status_code} {assign_res.text}"

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

    response = requests.put(url, headers=headers, json=body)
    print("📌 Metadata registrada:", response.status_code, response.text)

def run():
    try:
        register_metadata()
        app.run(host='0.0.0.0', port=8080)
    except Exception as e:
        print(f"❌ Error al iniciar el servidor: {e}")

def keep_alive():
    server = Thread(target=run)
    server.start()
