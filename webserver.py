from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def index():
    return "Hello, I am alive!"

def run():
    try:
        app.run(host='127.0.0.1', port=8080)
    except Exception as e:
        print(f"Error al iniciar el servidor: {e}")

def keep_alive():
    server = Thread(target=run)
    server.start()
