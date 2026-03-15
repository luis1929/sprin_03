from flask import Flask, request
import requests
import os

app = Flask(__name__)

# ==============================
# CONFIGURACIÓN
# ==============================

VERIFY_TOKEN = "colibry_verify_token"

WHATSAPP_TOKEN ="EAAiWkVZADneMBQ8YXiBvpZBJAggin4MeYc6THPwsGSvZByYBDhTtxASHGZBPMiIaTgG2xo99IiYOBGVZALrCCqGdRvt1oqA5MWchpZCnPo2tcfg4pf232aPBZCBGg7hlM7sGfffiGtBjRJ5s3qGK0ZAOKnABj1AJGZBVGR74Q4Yna4GHZAvLxyRvZCyKS1ud4ZBFDjf8JNMq2eBN2bHmhwWUlUYpstO1ZBdeUX2noQBSxhDoIRW5eZCi0fyc8hlCZAfRTcjI7JyOspD4hDg1dKOZBqeywyZA3EnjzzS4WdSKG"
PHONE_NUMBER_ID = "1094847673701798"

FLOWISE_URL = "http://localhost:3001/api/v1/prediction/98e29a71-fa25-4a68-a696-69243797699e"


# ==============================
# CONSULTAR FLOWISE
# ==============================

def consultar_flowise(pregunta, session_id):

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

        return f"Error conectando con Flowise: {str(e)}"


# ==============================
# ENVIAR MENSAJE A WHATSAPP
# ==============================

def enviar_whatsapp(numero, mensaje):

    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {
            "body": mensaje
        }
    }

    requests.post(url, headers=headers, json=data)


# ==============================
# WEBHOOK
# ==============================

@app.route("/webhook", methods=["GET", "POST"])
def webhook():

    # VERIFICACIÓN DEL WEBHOOK
    if request.method == "GET":

        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if token == VERIFY_TOKEN:
            return challenge, 200

        return "Token inválido", 403


    # MENSAJE RECIBIDO
    if request.method == "POST":

        data = request.json

        print("Evento recibido:", data)

        try:

            mensaje = data["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]

            numero = data["entry"][0]["changes"][0]["value"]["messages"][0]["from"]

            print(f"Mensaje de {numero}: {mensaje}")

            respuesta = consultar_flowise(mensaje, numero)

            print(f"Respuesta IA: {respuesta}")

            enviar_whatsapp(numero, respuesta)

        except Exception as e:

            print("Evento sin mensaje:", e)

        return "ok", 200


# ==============================
# EJECUTAR SERVIDOR
# ==============================

if __name__ == "__main__":

    app.run(host="0.0.0.0", port=5000)