from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# ==============================
# CONFIGURACIÓN (Vía Variables de Entorno)
# ==============================
FLOWISE_URL = os.getenv("FLOWISE_URL", "https://tu-flowwise-en-railway.up.railway.app/api/v1/prediction/ID_DE_TU_FLUJO")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "Colibry")

# ==============================
# CONSULTAR FLOWISE (Cerebro Híbrido)
# ==============================
def consultar_flowise(pregunta, session_id):
    payload = {
        "question": pregunta,
        "overrideConfig": {
            "sessionId": session_id
        }
    }
    headers = {"Content-Type": "application/json"}

    try:
        res = requests.post(FLOWISE_URL, json=payload, headers=headers, timeout=30)
        res.raise_for_status()
        return res.json().get("text", "No pude procesar tu consulta.")
    except Exception as e:
        return f"Error conectando con el cerebro Colibry: {str(e)}"

# ==============================
# ENVIAR MENSAJE VIA EVOLUTION API
# ==============================
def enviar_mensaje_evolution(numero, mensaje):
    url = f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}"

    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "number": numero,
        "options": {"delay": 1200, "presence": "composing"},
        "textMessage": {"text": mensaje}
    }

    try:
        res = requests.post(url, json=payload, headers=headers)
        return res.status_code
    except Exception as e:
        print(f"Error al enviar por Evolution: {e}")

# ==============================
# RUTAS
# ==============================
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "online", "service": "ATO Financial Chatbot"}), 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print("Evento recibido de Evolution:", data)

    try:
        mensaje = data.get("data", {}).get("message", {}).get("conversation", "")
        numero = data.get("data", {}).get("key", {}).get("remoteJid", "").split("@")[0]

        if mensaje and numero:
            print(f"Procesando mensaje de {numero}: {mensaje}")
            respuesta = consultar_flowise(mensaje, numero)
            enviar_mensaje_evolution(numero, respuesta)

    except Exception as e:
        print("Error procesando el webhook:", e)

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
