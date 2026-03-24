"""
Colibry Bot — Flask + Evolution API + Flowise
Recibe eventos MESSAGES_UPSERT de Evolution API y responde via Flowise.
"""

import os
import logging
import uuid

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

# ── Configuración ──────────────────────────────────────────────────────────────

FLOWISE_BASE_URL  = os.getenv("FLOWISE_BASE_URL")
FLOWISE_API_KEY   = os.getenv("FLOWISE_API_KEY")
FLOWISE_FLOW_ID   = os.getenv("FLOWISE_FLOW_ID", "general-agent")

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
INSTANCE_NAME     = os.getenv("INSTANCE_NAME", "Colibry")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── App ────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ── Flowise ────────────────────────────────────────────────────────────────────

def consultar_flowise(pregunta: str, session_id: str) -> str:
    if not FLOWISE_BASE_URL:
        logger.error("FLOWISE_BASE_URL no configurado")
        return "Lo siento, el servicio de IA no está disponible en este momento."

    url = f"{FLOWISE_BASE_URL}/api/v1/prediction/{FLOWISE_FLOW_ID}"
    headers = {"Content-Type": "application/json"}
    if FLOWISE_API_KEY:
        headers["Authorization"] = f"Bearer {FLOWISE_API_KEY}"

    payload = {
        "question": pregunta,
        "overrideConfig": {"sessionId": session_id},
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=30)
        res.raise_for_status()
        return res.json().get("text", "No pude procesar tu consulta.")
    except requests.exceptions.Timeout:
        logger.error("Flowise timeout para session %s", session_id)
        return "La respuesta tardó demasiado. Por favor intenta de nuevo."
    except Exception as e:
        logger.error("Error en Flowise: %s", e)
        return "Ocurrió un error procesando tu mensaje."


# ── Evolution API ──────────────────────────────────────────────────────────────

def enviar_mensaje(numero: str, mensaje: str) -> bool:
    if not EVOLUTION_API_URL or not EVOLUTION_API_KEY:
        logger.error("Evolution API no configurado")
        return False

    url = f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}"
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "number": numero,
        "options": {"delay": 1200, "presence": "composing"},
        "textMessage": {"text": mensaje},
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        ok = res.status_code == 200
        logger.info("Mensaje a %s — status %s", numero, res.status_code)
        return ok
    except Exception as e:
        logger.error("Error al enviar mensaje a %s: %s", numero, e)
        return False


# ── Rutas ──────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "Colibry Bot",
        "status": "online",
        "flowise": FLOWISE_BASE_URL or "no configurado",
        "evolution": EVOLUTION_API_URL or "no configurado",
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "online",
        "flowise": bool(FLOWISE_BASE_URL),
        "evolution": bool(EVOLUTION_API_URL and EVOLUTION_API_KEY),
    })


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return jsonify({"status": "ok", "message": "Webhook activo"}), 200

    data = request.get_json(silent=True) or {}
    event = data.get("event", "")

    # Solo procesar MESSAGES_UPSERT
    if event != "MESSAGES_UPSERT":
        return jsonify({"status": "ignored", "event": event}), 200

    try:
        msg_data  = data.get("data", {})
        key       = msg_data.get("key", {})
        message   = msg_data.get("message", {})

        # Ignorar mensajes propios
        if key.get("fromMe") is True:
            return jsonify({"status": "ignored", "reason": "fromMe"}), 200

        # Extraer número
        remote_jid = key.get("remoteJid", "")
        numero = remote_jid.split("@")[0] if remote_jid else ""
        if not numero:
            return jsonify({"status": "invalid", "reason": "no number"}), 400

        # Extraer texto del mensaje (varios tipos posibles)
        texto = (
            message.get("conversation")
            or message.get("extendedTextMessage", {}).get("text")
            or message.get("imageMessage", {}).get("caption")
            or ""
        ).strip()

        if not texto:
            logger.info("Mensaje sin texto de %s — ignorado", numero)
            return jsonify({"status": "ignored", "reason": "no text"}), 200

        session_id = remote_jid or str(uuid.uuid4())
        logger.info("[%s] %s", numero, texto[:80])

        respuesta = consultar_flowise(texto, session_id)
        enviado   = enviar_mensaje(numero, respuesta)

        return jsonify({
            "status": "success",
            "number": numero,
            "sent": enviado,
            "preview": respuesta[:120],
        }), 200

    except Exception as e:
        logger.error("Error en webhook: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500


# ── Entrypoint ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    logger.info("Colibry Bot iniciando en puerto %s", port)
    app.run(host="0.0.0.0", port=port)
