#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import uuid
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

load_dotenv()

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

FLOWISE_BASE_URL = os.getenv("FLOWISE_BASE_URL")
FLOWISE_API_KEY = os.getenv("FLOWISE_API_KEY")
FLOWISE_FLOW_ID = os.getenv("FLOWISE_FLOW_ID", "general-agent")

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "Colibry")

N8N_BASE_URL = os.getenv("N8N_BASE_URL")


def get_flowise_headers():
    headers = {"Content-Type": "application/json"}
    if FLOWISE_API_KEY:
        headers["Authorization"] = f"Bearer {FLOWISE_API_KEY}"
    return headers


def consultar_flowise(pregunta, session_id):
    if not FLOWISE_BASE_URL:
        return "Flowise no está configurado."

    url = f"{FLOWISE_BASE_URL}/api/v1/prediction/{FLOWISE_FLOW_ID}"
    payload = {
        "question": pregunta,
        "overrideConfig": {
            "sessionId": session_id
        }
    }

    try:
        res = requests.post(
            url,
            json=payload,
            headers=get_flowise_headers(),
            timeout=30
        )
        res.raise_for_status()
        data = res.json()
        return data.get("text", "No pude procesar tu consulta.")
    except Exception as e:
        logger.error(f"Error en Flowise: {str(e)}")
        return f"Error conectando con Flowise: {str(e)}"


def enviar_mensaje_evolution(numero, mensaje):
    if not EVOLUTION_API_URL or not EVOLUTION_API_KEY:
        logger.error("Evolution API no está configurado")
        return None

    url = f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}"
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "number": numero,
        "options": {
            "delay": 1200,
            "presence": "composing"
        },
        "textMessage": {
            "text": mensaje
        }
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=30)
        logger.info(f"Mensaje enviado a {numero} - Status: {res.status_code}")
        return res.status_code
    except Exception as e:
        logger.error(f"Error al enviar por Evolution: {str(e)}")
        return None


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "service": "ATO Financial Chatbot",
        "version": "2.2-minimal"
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "online",
        "mode": "degraded",
        "version": "2.2-minimal",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {
            "database": "disabled",
            "evolution": EVOLUTION_API_URL or "not configured",
            "flowise": FLOWISE_BASE_URL or "not configured",
            "n8n": N8N_BASE_URL or "not configured"
        }
    }), 200


@app.route("/webhook", methods=["GET", "POST"])
@app.route("/webhook/evolution", methods=["GET", "POST"])
def webhook_evolution():
    if request.method == "GET":
        return jsonify({
            "status": "ok",
            "message": "Webhook endpoint activo. Usa POST para enviar eventos."
        }), 200

    data = request.get_json(silent=True) or {}
    logger.info(f"Webhook Evolution recibido: {data}")

    try:
        event_name = data.get("event", "")
        key_data = data.get("data", {}).get("key", {})
        message_data = data.get("data", {}).get("message", {})

        if key_data.get("fromMe") is True:
            return jsonify({"status": "ignored", "reason": "fromMe"}), 200

        mensaje = (
            message_data.get("conversation")
            or message_data.get("extendedTextMessage", {}).get("text")
            or message_data.get("imageMessage", {}).get("caption")
            or ""
        )

        remote_jid = key_data.get("remoteJid", "")
        numero = remote_jid.split("@")[0] if remote_jid else ""
        session_id = remote_jid or numero or str(uuid.uuid4())

        if not mensaje or not numero:
            return jsonify({
                "status": "invalid",
                "message": "No message or number found",
                "event": event_name
            }), 400

        respuesta = consultar_flowise(mensaje, session_id)
        evolution_status = enviar_mensaje_evolution(numero, respuesta)

        return jsonify({
            "status": "success",
            "mode": "degraded",
            "database_persisted": False,
            "event": event_name,
            "number": numero,
            "evolution_status": evolution_status,
            "reply_preview": respuesta[:120]
        }), 200

    except Exception as e:
        logger.error(f"Error en webhook_evolution: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
