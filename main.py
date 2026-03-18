#!/usr/bin/env python
# -*- coding: utf-8 -*-

# ============================================================
# ATO FINANCIAL - FLASK BACKEND ESCALABLE v2.0
# Basado en el main.py actual + arquitectura n8n
# ============================================================

import os
import json
import logging
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv
import uuid

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, func
import jwt
import requests

load_dotenv()

# ============================================================
# CONFIGURACIÓN
# ============================================================

app = Flask(__name__)
CORS(app)

# Database
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JSON_SORT_KEYS'] = False

db = SQLAlchemy(app)

# Security
SECRET_KEY = os.getenv('JWT_SECRET', 'your-secret-key-change-in-prod')
N8N_WEBHOOK_SECRET = os.getenv('N8N_WEBHOOK_SIGNATURE_SECRET')

# Logging
logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

# External APIs
N8N_BASE_URL = os.getenv('N8N_BASE_URL')
FLOWISE_BASE_URL = os.getenv('FLOWISE_BASE_URL')
EVOLUTION_API_URL = os.getenv('EVOLUTION_API_URL')
EVOLUTION_API_KEY = os.getenv('EVOLUTION_API_KEY')
INSTANCE_NAME = os.getenv('INSTANCE_NAME', 'Colibry')

# ============================================================
# MODELOS ORM
# ============================================================

class User(db.Model):
    """Almacena usuarios/sesiones"""
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255))
    name = db.Column(db.String(255))
    channel = db.Column(db.String(50), nullable=False, index=True)
    preferred_agent = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    last_interaction = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='active')
    metadata = db.Column(db.JSON, default={})
    
    conversations = db.relationship('Conversation', backref='user', lazy='dynamic')
    messages = db.relationship('Message', backref='user', lazy='dynamic')


class Conversation(db.Model):
    """Sesión de conversación con agente"""
    __tablename__ = 'conversations'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    agent_type = db.Column(db.String(100), nullable=False, index=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    ended_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='active', index=True)
    summary = db.Column(db.Text)
    context = db.Column(db.JSON, default={})
    sentiment = db.Column(db.String(20))
    resolution_score = db.Column(db.Float)
    
    messages = db.relationship('Message', backref='conversation', lazy='dynamic')


class Message(db.Model):
    """Cada mensaje en conversación"""
    __tablename__ = 'messages'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = db.Column(db.String(36), db.ForeignKey('conversations.id'), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    channel = db.Column(db.String(50), nullable=False)
    processed_by = db.Column(db.String(100))
    metadata = db.Column(db.JSON, default={})
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Analytics(db.Model):
    """Métricas agregadas"""
    __tablename__ = 'analytics'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    agent_type = db.Column(db.String(100))
    total_messages = db.Column(db.Integer, default=0)
    avg_response_time = db.Column(db.Float)
    sentiment_avg = db.Column(db.Float)
    resolution_rate = db.Column(db.Float)
    conversion_indicator = db.Column(db.Boolean, default=False)
    churn_risk_score = db.Column(db.Float, index=True)
    metadata = db.Column(db.JSON, default={})
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', 'agent_type', name='unique_user_date_agent'),
    )


class AuditLog(db.Model):
    """Logs de compliance"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = db.Column(db.String(100), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), index=True)
    data = db.Column(db.JSON, nullable=False)
    ip_address = db.Column(db.String(45))
    source = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


# ============================================================
# MIDDLEWARE & AUTENTICACIÓN
# ============================================================

def token_required(f):
    """Valida JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'message': 'Invalid token format'}), 401
        
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            current_user = data.get('user_id')
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated


def log_audit_event(event_type, user_id=None, data=None):
    """Registra eventos en audit logs"""
    log = AuditLog(
        id=str(uuid.uuid4()),
        event_type=event_type,
        user_id=user_id,
        data=data or {},
        ip_address=request.remote_addr,
        source=request.headers.get('User-Agent', 'unknown')
    )
    db.session.add(log)
    db.session.commit()


# ============================================================
# FUNCIONES AUXILIARES (Compatibilidad con código antiguo)
# ============================================================

def consultar_flowise(pregunta, session_id, flow_id=None):
    """
    Consulta Flowise (mantiene compatibilidad con código anterior).
    Si flow_id no se especifica, intenta obtenerlo de las variables de entorno.
    """
    if not flow_id:
        flow_id = os.getenv("FLOWISE_FLOW_ID", "general-agent")
    
    url = f"{FLOWISE_BASE_URL}/api/v1/prediction/{flow_id}"
    
    payload = {
        "question": pregunta,
        "sessionId": session_id
    }
    headers = {"Content-Type": "application/json"}

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=30)
        res.raise_for_status()
        return res.json().get("text", "No pude procesar tu consulta.")
    except Exception as e:
        logger.error(f"Error en Flowise: {str(e)}")
        return f"Error conectando con Flowise: {str(e)}"


def enviar_mensaje_evolution(numero, mensaje):
    """
    Envía mensaje por Evolution API (compatibilidad con código anterior).
    """
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
        logger.info(f"Mensaje enviado a {numero} - Status: {res.status_code}")
        return res.status_code
    except Exception as e:
        logger.error(f"Error al enviar por Evolution: {e}")
        return None


# ============================================================
# ROUTES: HEALTH & VERSION
# ============================================================

@app.route('/', methods=['GET'])
def home():
    """Health check básico"""
    return jsonify({
        'status': 'online',
        'service': 'ATO Financial Chatbot v2.0',
        'version': '2.0'
    }), 200


@app.route('/health', methods=['GET'])
def health():
    """Health check detallado"""
    try:
        db.session.execute('SELECT 1')
        db_status = 'ok'
    except Exception as e:
        db_status = f'error: {str(e)}'
    
    return jsonify({
        'status': 'online',
        'version': '2.0',
        'timestamp': datetime.utcnow().isoformat(),
        'dependencies': {
            'database': db_status,
            'evolution': f'{EVOLUTION_API_URL or "not configured"}',
            'flowise': f'{FLOWISE_BASE_URL or "not configured"}',
            'n8n': f'{N8N_BASE_URL or "not configured"}'
        }
    }), 200


# ============================================================
# ROUTES: WEBHOOKS (Compatibilidad + Nueva Arquitectura)
# ============================================================

@app.route('/webhook', methods=['POST'])
def webhook_evolution():
    """
    Webhook de Evolution API (mantiene compatibilidad con código anterior).
    Ahora además guarda en BD y prepara para n8n.
    """
    data = request.json
    logger.info(f"Webhook Evolution recibido: {data}")

    try:
        # Parsear Evolution API
        mensaje_data = data.get("data", {}).get("message", {})
        mensaje = mensaje_data.get("conversation", "")
        numero = data.get("data", {}).get("key", {}).get("remoteJid", "").split("@")[0]

        if not mensaje or not numero:
            return jsonify({"status": "invalid"}), 400

        # Obtener o crear usuario
        user = User.query.filter_by(phone_number=numero).first()
        if not user:
            user = User(
                id=str(uuid.uuid4()),
                phone_number=numero,
                channel='whatsapp',
                status='active'
            )
            db.session.add(user)
            db.session.flush()

        # Obtener o crear conversación
        conv = Conversation.query.filter_by(
            user_id=user.id,
            status='active'
        ).order_by(desc(Conversation.started_at)).first()
        
        if not conv:
            conv = Conversation(
                id=str(uuid.uuid4()),
                user_id=user.id,
                agent_type='general',
                status='active'
            )
            db.session.add(conv)
            db.session.flush()

        # Guardar mensaje de usuario
        msg_user = Message(
            id=str(uuid.uuid4()),
            conversation_id=conv.id,
            user_id=user.id,
            role='user',
            content=mensaje,
            channel='whatsapp',
            processed_by='evolution'
        )
        db.session.add(msg_user)

        # Consultar Flowise (compatibilidad con código anterior)
        respuesta = consultar_flowise(mensaje, numero)

        # Guardar mensaje de agente
        msg_agent = Message(
            id=str(uuid.uuid4()),
            conversation_id=conv.id,
            user_id=user.id,
            role='agent',
            content=respuesta,
            channel='whatsapp',
            processed_by='flowise'
        )
        db.session.add(msg_agent)

        # Actualizar usuario
        user.last_interaction = datetime.utcnow()

        db.session.commit()

        # Enviar por Evolution
        enviar_mensaje_evolution(numero, respuesta)

        # Auditoría
        log_audit_event('webhook_evolution_processed', user.id, {
            'conversation_id': conv.id,
            'message': mensaje[:100]
        })

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"Error en webhook_evolution: {str(e)}")
        log_audit_event('webhook_evolution_error', data={"error": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/webhook/n8n', methods=['POST'])
def webhook_from_n8n():
    """
    Recibe respuestas desde n8n después de procesar con Flowise.
    """
    data = request.get_json()
    
    try:
        conversation_id = data.get('conversation_id')
        user_id = data.get('user_id')
        message_content = data.get('message')
        agent_type = data.get('agent_type')
        metadata = data.get('metadata', {})
        
        if not all([conversation_id, user_id, message_content]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Guardar mensaje
        msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            user_id=user_id,
            role='agent',
            content=message_content,
            channel=metadata.get('channel', 'whatsapp'),
            processed_by=metadata.get('processed_by', 'flowise'),
            metadata=metadata
        )
        db.session.add(msg)
        
        # Actualizar last_interaction
        user = User.query.get(user_id)
        if user:
            user.last_interaction = datetime.utcnow()
        
        db.session.commit()
        
        log_audit_event('webhook_n8n_processed', user_id, {
            'conversation_id': conversation_id
        })
        
        return jsonify({
            'status': 'saved',
            'message_id': msg.id,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f'Error in webhook_n8n: {str(e)}')
        return jsonify({'error': str(e)}), 500


# ============================================================
# ROUTES: CONVERSATIONS (CRUD)
# ============================================================

@app.route('/conversations/<conversation_id>', methods=['GET'])
@token_required
def get_conversation(user_id, conversation_id):
    """Obtiene historial de conversación"""
    conversation = Conversation.query.get(conversation_id)
    
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404
    
    if conversation.user_id != user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    messages = Message.query.filter_by(conversation_id=conversation_id).all()
    
    return jsonify({
        'conversation': {
            'id': conversation.id,
            'agent_type': conversation.agent_type,
            'started_at': conversation.started_at.isoformat(),
            'status': conversation.status,
            'summary': conversation.summary
        },
        'messages': [
            {
                'id': m.id,
                'role': m.role,
                'content': m.content,
                'created_at': m.created_at.isoformat()
            }
            for m in messages
        ]
    }), 200


@app.route('/conversations', methods=['GET'])
@token_required
def list_conversations(user_id):
    """Lista conversaciones del usuario"""
    conversations = Conversation.query.filter_by(user_id=user_id)\
        .order_by(desc(Conversation.started_at))\
        .limit(10)\
        .all()
    
    return jsonify({
        'conversations': [
            {
                'id': c.id,
                'agent_type': c.agent_type,
                'started_at': c.started_at.isoformat(),
                'status': c.status,
                'summary': c.summary
            }
            for c in conversations
        ]
    }), 200


# ============================================================
# ROUTES: ANALYTICS
# ============================================================

@app.route('/analytics/summary', methods=['GET'])
def get_analytics_summary():
    """Dashboard ejecutivo"""
    today = datetime.utcnow().date()
    
    today_messages = Message.query.filter(
        Message.created_at >= datetime.combine(today, datetime.min.time())
    ).count()
    
    today_conversations = Conversation.query.filter(
        Conversation.started_at >= datetime.combine(today, datetime.min.time())
    ).count()
    
    today_users = db.session.query(func.count(func.distinct(Message.user_id))).filter(
        Message.created_at >= datetime.combine(today, datetime.min.time())
    ).scalar()
    
    return jsonify({
        'timestamp': datetime.utcnow().isoformat(),
        'today': {
            'messages': today_messages,
            'conversations': today_conversations,
            'active_users': today_users or 0
        }
    }), 200


# ============================================================
# ROUTES: FLOWISE (Testing)
# ============================================================

@app.route('/flowise/query', methods=['POST'])
def query_flowise_direct():
    """Testing directo de Flowise"""
    data = request.get_json()
    
    flow_id = data.get('flow_id', os.getenv("FLOWISE_FLOW_ID"))
    question = data.get('question')
    
    if not flow_id or not question:
        return jsonify({'error': 'Missing flow_id or question'}), 400
    
    try:
        response = requests.post(
            f'{FLOWISE_BASE_URL}/api/v1/prediction/{flow_id}',
            json={'question': question},
            timeout=30
        )
        return jsonify(response.json()), 200
    except Exception as e:
        logger.error(f'Flowise error: {str(e)}')
        return jsonify({'error': str(e)}), 500


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f'Internal error: {str(error)}')
    return jsonify({'error': 'Internal server error'}), 500


# ============================================================
# INICIALIZACIÓN
# ============================================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    port = int(os.getenv('PORT', 5000))
    
    # Usar Gunicorn en producción (Railway)
    # En local: python main.py
    app.run(host='0.0.0.0', port=port, debug=False)