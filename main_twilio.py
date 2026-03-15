from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests

app = Flask(__name__)

# Configuración
FLOWISE_URL = "http://localhost:3001/api/v1/prediction/98e29a71-fa25-4a68-a696-69243797699e"

def consultar_flowise(pregunta: str, session_id: str) -> str:
    payload = {
        "question": pregunta,
        "overrideConfig": {
            "sessionId": session_id
        }
    }
    try:
        res = requests.post(FLOWISE_URL, json=payload, timeout=30)
        return res.json().get("text", "No pude procesar tu consulta.")
    except Exception as e:
        return f"Error de conexión: {str(e)}"

@app.route("/webhook", methods=["POST"])
def webhook():
    mensaje = request.form.get("Body", "")
    numero  = request.form.get("From", "")
    
    print(f"📩 Mensaje de {numero}: {mensaje}")
    
    respuesta = consultar_flowise(mensaje, session_id=numero)
    
    print(f"🤖 Respuesta: {respuesta}")
    
    resp = MessagingResponse()
    resp.message(respuesta)
    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
    