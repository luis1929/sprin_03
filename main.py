#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv
import uuid

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, func, text
import jwt
import requests

load_dotenv()

app = Flask(__name__)
CORS(app)

database_url = os.getenv("DATABASE_URL")

if not database_url:
    database_url = (
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_SORT_KEYS"] = False

db = SQLAlchemy(app)

SECRET_KEY = os.getenv("JWT_SECRET", "change-this-in-production")
N8N_WEBHOOK_SECRET = os.getenv("N8N_WEBHOOK_SIGNATURE_SECRET")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

N8N_BASE_URL = os.getenv("N8N_BASE_URL")
FLOWISE_BASE_URL = os.getenv("FLOWISE_BASE_URL")
FLOWISE_API_KEY = os.getenv("FLOWISE_API_KEY")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "Colibry")


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255))
    name = db.Column(db.String(255))
    channel = db.Column(db.String(50), nullable=False, index=True)
    preferred_agent = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    last_interaction = db.Column(db.DateTime)
    status = db.Column(db.String(20), default="active")
    metadata = db.Column(db.JSON, default=dict)

    conversations = db.relationship("Conversation", backref="user", lazy="dynamic")
    messages = db.relationship("Message", backref="user", lazy="dynamic")


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    agent_type = db.Column(db.String(100), nullable=False, index=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    ended_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default="active", index=True)
    summary = db.Column(db.Text)
    context = db.Column(db.JSON, default=dict)
    sentiment = db.Column(db.String(20))
    resolution_score = db.Column(db.Float)

    messages = db.relationship("Message", backref="conversation", lazy="dynamic")


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = db.Column(db.String(36), db.ForeignKey("conversations.id"), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    channel = db.Column(db.String(50), nullable=False)
    processed_by = db.Column(db.String(100))
    metadata = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Analytics(db.Model):
    __tablename__ = "analytics"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    agent_type = db.Column(db.String(100))
    total_messages = db.Column(db.Integer, default=0)
    avg_response_time = db.Column(db.Float)
    sentiment_avg = db.Column(db.Float)
    resolution_rate = db.Column(db.Float)
    conversion_indicator = db.Column(db.Boolean, default=False)
    churn_risk_score = db.Column(db.Float, index=True)
    metadata = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "date", "agent_type", name="unique_user_date_agent"),
    )


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = db.Column(db.String(100), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), index=True)
    data = db.Column(db.JSON, nullable=False)
    ip_address = db.Column(db.String(45))
    source = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        if "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({"message": "Invalid token format"}), 401

        if not token:
            return jsonify({"message": "Token is missing"}), 401

        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            current_user = data.get("user_id")
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"message": "Invalid token"}), 401

        return f(current_user, *args, **kwargs)

    return decorated


def log_audit_event(event_type, user_id=None, data=None):
    try:
        log = AuditLog(
            id=str(uuid.uuid4()),
            event_type=event_type,
            user_id=user_id,
            data=data or {},
            ip_address=request.remote_addr,
            source=request.headers.get("User-Agent", "unknown"),
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error guardando audit log: {str(e)}")


def get_flowise_headers():
    headers = {"Content-Type": "application/json"}
    if FLOWISE_API_KEY:
        headers["Authorization"] = f"Bearer {FLOWISE_API_KEY}"
    return headers


def consultar_flowise(pregunta, session_id, flow_id=None):
    if not FLOWISE_BASE_URL:
        return "Flowise no está configurado."

    if not flow_id:
        flow_id = os.getenv("FLOWISE_FLOW_ID", "general-agent")

    url = f"{FLOWISE_BASE_URL}/api/v1/prediction/{flow_id}"

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
        response_json = res.json()
        return response_json.get("text", "No pude procesar tu consulta.")
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


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "service": "ATO Financial Chatbot v2.0",
        "version": "2.0"
    }), 200


@app.route("/health", methods=["GET"])
def health():
    try:
        db.session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return jsonify({
        "status": "online",
        "version": "2.0",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {
            "database": db_status,
            "evolution": EVOLUTION_API_URL or "not configured",
            "flowise": FLOWISE_BASE_URL or "not configured",
            "n8n": N8N_BASE_URL or "not configured"
        }
    }), 200


@app.route("/version", methods=["GET"])
def version():
    return jsonify({
        "service": "ATO Financial Chatbot",
        "version": "2.0",
        "environment": os.getenv("RAILWAY_ENVIRONMENT", "local")
    }), 200


@app.route("/webhook", methods=["POST"])
@app.route("/webhook/evolution", methods=["POST"])
def webhook_evolution():
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

        if not mensaje or not numero:
            return jsonify({"status": "invalid", "message": "No message or number found"}), 400

        user = User.query.filter_by(phone_number=numero).first()
        if not user:
            user = User(
                id=str(uuid.uuid4()),
                phone_number=numero,
                channel="whatsapp",
                status="active",
                preferred_agent="general"
            )
            db.session.add(user)
            db.session.flush()

        conv = Conversation.query.filter_by(
            user_id=user.id,
            status="active"
        ).order_by(desc(Conversation.started_at)).first()

        if not conv:
            conv = Conversation(
                id=str(uuid.uuid4()),
                user_id=user.id,
                agent_type=user.preferred_agent or "general",
                status="active"
            )
            db.session.add(conv)
            db.session.flush()

        msg_user = Message(
            id=str(uuid.uuid4()),
            conversation_id=conv.id,
            user_id=user.id,
            role="user",
            content=mensaje,
            channel="whatsapp",
            processed_by="evolution",
            metadata={
                "event": event_name,
                "remote_jid": remote_jid
            }
        )
        db.session.add(msg_user)

        respuesta = consultar_flowise(mensaje, remote_jid or numero)

        msg_agent = Message(
            id=str(uuid.uuid4()),
            conversation_id=conv.id,
            user_id=user.id,
            role="agent",
            content=respuesta,
            channel="whatsapp",
            processed_by="flowise"
        )
        db.session.add(msg_agent)

        user.last_interaction = datetime.utcnow()
        db.session.commit()

        enviar_mensaje_evolution(numero, respuesta)

        log_audit_event("webhook_evolution_processed", user.id, {
            "conversation_id": conv.id,
            "message_preview": mensaje[:100],
            "remote_jid": remote_jid
        })

        return jsonify({
            "status": "success",
            "conversation_id": conv.id,
            "user_id": user.id
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error en webhook_evolution: {str(e)}")
        log_audit_event("webhook_evolution_error", data={"error": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/webhook/n8n", methods=["POST"])
def webhook_from_n8n():
    data = request.get_json(silent=True) or {}

    try:
        conversation_id = data.get("conversation_id")
        user_id = data.get("user_id")
        message_content = data.get("message")
        agent_type = data.get("agent_type")
        metadata = data.get("metadata", {})

        if not all([conversation_id, user_id, message_content]):
            return jsonify({"error": "Missing required fields"}), 400

        msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            user_id=user_id,
            role="agent",
            content=message_content,
            channel=metadata.get("channel", "whatsapp"),
            processed_by=metadata.get("processed_by", "flowise"),
            metadata=metadata
        )
        db.session.add(msg)

        user = User.query.get(user_id)
        if user:
            user.last_interaction = datetime.utcnow()
            if agent_type:
                user.preferred_agent = agent_type

        db.session.commit()

        log_audit_event("webhook_n8n_processed", user_id, {
            "conversation_id": conversation_id,
            "agent_type": agent_type
        })

        return jsonify({
            "status": "saved",
            "message_id": msg.id,
            "timestamp": datetime.utcnow().isoformat()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in webhook_n8n: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/conversations/<conversation_id>", methods=["GET"])
@token_required
def get_conversation(user_id, conversation_id):
    conversation = Conversation.query.get(conversation_id)

  if not conversation:
    return jsonify({"error": "Conversation not found"}), 404

