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
from sqlalchemy import desc, text
import jwt
import requests

load_dotenv()

app = Flask(__name__)
CORS(app)

database_url = os.getenv("DATABASE_URL")

if not database_url:
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_name = os.getenv("DB_NAME")
    if all([db_user, db_password, db_host, db_port, db_name]):
        database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_SORT_KEYS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True
}

db = SQLAlchemy(app)

SECRET_KEY = os.getenv("JWT_SECRET", "change-this-in-production")
N8N_WEBHOOK_SECRET = os.getenv("N8N_WEBHOOK_SIGNATURE_SECRET")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

N8N_BASE_URL = os.getenv("N8N_BASE_URL")
FLOWISE_BASE_URL = os.getenv("FLOWISE_BASE_URL")
FLOWISE_API_KEY = os.getenv("FLOWISE_API_KEY")
FLOWISE_FLOW_ID = os.getenv("FLOWISE_FLOW_ID", "general-agent")
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
    meta_data = db.Column(db.JSON, default=dict)


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


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = db.Column(db.String(36), db.ForeignKey("conversations.id"), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    channel = db.Column(db.String(50), nullable=False)
    processed_by = db.Column(db.String(100))
    meta_data = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = db.Column(db.String(100), nullable=False, index=True)
    user_id = db.Column(db.String(36), index=True)
    data = db.Column(db.JSON, nullable=False)
    ip_address = db.Column(db.String(45))
    source = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


def db_available():
    try:
        db.session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning(f"DB no disponible: {str(e)}")
        return False


def safe_commit():
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger.warning(f"No se pudo hacer commit: {str(e)}")
        return False


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
    if not db_available():
        logger.info(f"Audit sin DB: {event_type}")
        return

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
        safe_commit()
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

    flow_id = flow_id or FLOWISE_FLOW_ID
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
        "version": "2.1-degraded"
    }), 200


@app.route("/health", methods=["GET"])
def health():
    database_status = "ok" if db_available() else "unavailable"

    return jsonify({
        "status": "online",
        "version": "2.1-degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "mode": "degraded" if database_status != "ok" else "normal",
        "dependencies": {
            "database": database_status,
            "evolution": EVOLUTION_API_URL or "not configured",
            "flowise": FLOWISE_BASE_URL or "not configured",
            "n8n": N8N_BASE_URL or "not configured"
        }
    }), 200


@app.route("/version", methods=["GET"])
def version():
    return jsonify({
        "service": "ATO Financial Chatbot",
        "version": "2.1-degraded",
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
        session_id = remote_jid or numero or str(uuid.uuid4())

        if not mensaje or not numero:
            return jsonify({"status": "invalid", "message": "No message or number found"}), 400

        user_id = None
        conversation_id = str(uuid.uuid4())
        database_mode = db_available()

        if database_mode:
            try:
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
                        id=conversation_id,
                        user_id=user.id,
                        agent_type=user.preferred_agent or "general",
                        status="active"
                    )
                    db.session.add(conv)
                    db.session.flush()
                else:
                    conversation_id = conv.id

                user_id = user.id

                msg_user = Message(
                    id=str(uuid.uuid4()),
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="user",
                    content=mensaje,
                    channel="whatsapp",
                    processed_by="evolution",
                    meta_data={
                        "event": event_name,
                        "remote_jid": remote_jid
                    }
                )
                db.session.add(msg_user)
                safe_commit()
            except Exception as e:
                db.session.rollback()
                database_mode = False
                logger.warning(f"Fallo persistencia, sigo sin DB: {str(e)}")

        respuesta = consultar_flowise(mensaje, session_id)
        evolution_status = enviar_mensaje_evolution(numero, respuesta)

        if database_mode and user_id:
            try:
                msg_agent = Message(
                    id=str(uuid.uuid4()),
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="agent",
                    content=respuesta,
                    channel="whatsapp",
                    processed_by="flowise"
                )
                db.session.add(msg_agent)

                user = db.session.get(User, user_id)
                if user:
                    user.last_interaction = datetime.utcnow()

                safe_commit()
            except Exception as e:
                db.session.rollback()
                logger.warning(f"No se pudo guardar respuesta del agente: {str(e)}")

        log_audit_event("webhook_evolution_processed", user_id, {
            "conversation_id": conversation_id,
            "message_preview": mensaje[:100],
            "remote_jid": remote_jid,
            "database_mode": database_mode,
            "evolution_status": evolution_status
        })

        return jsonify({
            "status": "success",
            "mode": "normal" if database_mode else "degraded",
            "database_persisted": database_mode,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "reply_preview": respuesta[:120]
        }), 200

    except Exception as e:
        logger.error(f"Error en webhook_evolution: {str(e)}")
        log_audit_event("webhook_evolution_error", data={"error": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/webhook/n8n", methods=["POST"])
def webhook_from_n8n():
    data = request.get_json(silent=True) or {}

    if not db_available():
        return jsonify({
            "status": "ignored",
            "mode": "degraded",
            "message": "Database unavailable, message not persisted"
        }), 200

    try:
        conversation_id = data.get("conversation_id")
        user_id = data.get("user_id")
        message_content = data.get("message")
        agent_type = data.get("agent_type")
        meta_data = data.get("metadata", {})

        if not all([conversation_id, user_id, message_content]):
            return jsonify({"error": "Missing required fields"}), 400

        msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            user_id=user_id,
            role="agent",
            content=message_content,
            channel=meta_data.get("channel", "whatsapp"),
            processed_by=meta_data.get("processed_by", "flowise"),
            meta_data=meta_data
        )
        db.session.add(msg)

        user = db.session.get(User, user_id)
        if user:
            user.last_interaction = datetime.utcnow()
            if agent_type:
                user.preferred_agent = agent_type

        safe_commit()

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
    if not db_available():
        return jsonify({
            "error": "Database unavailable in degraded mode"
        }), 503

    conversation = db.session.get(Conversation, conversation_id)

    if not conversation:
        return jsonify({"error": "Conversation not found"}), 404

    messages = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.created_at.asc()).all()

    return jsonify({
        "conversation": {
            "id": conversation.id,
            "user_id": conversation.user_id,
            "agent_type": conversation.agent_type,
            "status": conversation.status,
            "started_at": conversation.started_at.isoformat() if conversation.started_at else None,
            "ended_at": conversation.ended_at.isoformat() if conversation.ended_at else None,
            "summary": conversation.summary,
            "context": conversation.context,
            "sentiment": conversation.sentiment,
            "resolution_score": conversation.resolution_score
        },
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "channel": m.channel,
                "processed_by": m.processed_by,
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in messages
        ]
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
