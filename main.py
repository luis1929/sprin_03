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