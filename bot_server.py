"""
Colibry Bot Server — Agente Inteligente con Memoria
Motor: OpenAI GPT-4o-mini + LangChain + SQLite
Personalidad: Administrador Eclesiástico — Iglesia en Barranquilla
"""

import json
import logging
import os
import re
from datetime import datetime

import requests
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import Json, RealDictCursor

from flask import Flask, Response, jsonify, render_template, request
import socket
import subprocess
from functools import wraps
from langchain_community.chat_message_histories import SQLChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage
from openai import APIConnectionError, APIError, OpenAI, RateLimitError

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


FLOWISE_URL     = os.getenv("FLOWISE_BASE_URL", "")
FLOWISE_API_KEY = os.getenv("FLOWISE_API_KEY", "")
FLOWISE_FLOW_ID = os.getenv("FLOWISE_FLOW_ID", "")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "colibry_memory.db")
TTS_MAX_CHARS  = int(os.getenv("TTS_MAX_CHARS", "300"))


# ── System Prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres el Asistente Virtual oficial de America's TAX OFFICE - Financial & Immigration.

FECHA ACTUAL: 24 de marzo de 2026. Usa siempre esta fecha como referencia. No menciones 2023 ni fechas anteriores.
AÑO FISCAL VIGENTE: 2025 (declaraciones presentadas en 2026).

IDIOMA: Responde siempre en el mismo idioma que use el cliente (español, inglés, francés o alemán).

PERSONALIDAD:
- Profesional, empático y preciso. Máximo 200 palabras por respuesta.
- Nunca das asesoría legal definitiva; recomiendas consultar un especialista.

SERVICIOS DE LA EMPRESA:
- Tax Returns (declaraciones de impuestos), ITIN, Notaría, Traducciones certificadas,
  Trámites migratorios, Asesoría financiera, Incorporación de empresas.
"""


# ── Herramientas (Tool Calling) ────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_diezmos",
            "description": (
                "Consulta el registro de diezmos y ofrendas de un miembro "
                "de la iglesia por su nombre o número de identificación."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {
                        "type": "string",
                        "description": "Nombre completo del hermano/miembro",
                    },
                    "periodo": {
                        "type": "string",
                        "description": "Período a consultar, ej: '2025-03' o 'último mes'",
                    },
                },
                "required": ["nombre"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agendar_cita_pastoral",
            "description": (
                "Agenda una cita pastoral con el pastor o líder de la iglesia "
                "para consejería, oración o asuntos administrativos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {
                        "type": "string",
                        "description": "Nombre del hermano que solicita la cita",
                    },
                    "motivo": {
                        "type": "string",
                        "description": "Motivo: consejería, oración, administrativo, otro",
                    },
                    "fecha_preferida": {
                        "type": "string",
                        "description": "Fecha y hora preferida, ej: '2025-04-01 10:00'",
                    },
                },
                "required": ["nombre", "motivo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_miembro",
            "description": "Registra un nuevo miembro en la base de datos de la iglesia.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {
                        "type": "string",
                        "description": "Nombre completo del nuevo miembro",
                    },
                    "telefono": {
                        "type": "string",
                        "description": "Número de WhatsApp del miembro",
                    },
                    "barrio": {
                        "type": "string",
                        "description": "Barrio o sector en Barranquilla donde vive",
                    },
                },
                "required": ["nombre", "telefono"],
            },
        },
    },
]


# ── Ejecutores de herramientas ─────────────────────────────────────────────────

def ejecutar_herramienta(nombre: str, argumentos: dict) -> str:
    """Despacha la herramienta solicitada por el modelo y retorna JSON con el resultado."""
    logger.info("[TOOL] %s | args: %s", nombre, argumentos)

    if nombre == "consultar_diezmos":
        miembro = argumentos.get("nombre", "desconocido")
        periodo = argumentos.get("periodo", "mes actual")
        # TODO: conectar con sistema contable real
        return json.dumps({
            "status": "ok",
            "nombre": miembro,
            "periodo": periodo,
            "resultado": (
                f"Registro de diezmos para {miembro} en {periodo}: "
                "pendiente de integración con el sistema contable."
            ),
        }, ensure_ascii=False)

    if nombre == "agendar_cita_pastoral":
        nombre_h = argumentos.get("nombre", "hermano")
        motivo    = argumentos.get("motivo", "general")
        fecha     = argumentos.get("fecha_preferida", "por confirmar")
        # TODO: integrar con Google Calendar o sistema de agenda
        return json.dumps({
            "status": "agendado",
            "nombre": nombre_h,
            "motivo": motivo,
            "fecha": fecha,
            "mensaje": (
                f"Cita solicitada para {nombre_h}. "
                f"El pastor confirmará disponibilidad para {fecha}."
            ),
        }, ensure_ascii=False)

    if nombre == "registrar_miembro":
        nombre_h = argumentos.get("nombre", "")
        telefono = argumentos.get("telefono", "")
        barrio   = argumentos.get("barrio", "no especificado")
        # TODO: persistir en base de datos de miembros
        return json.dumps({
            "status": "registrado",
            "nombre": nombre_h,
            "telefono": telefono,
            "barrio": barrio,
            "mensaje": f"{nombre_h} registrado como nuevo miembro. ¡Bienvenido/a a la familia!",
        }, ensure_ascii=False)

    logger.warning("Herramienta desconocida: %s", nombre)
    return json.dumps({"status": "error", "mensaje": f"Herramienta '{nombre}' no implementada."})


# ── Memoria por usuario (SQLite + LangChain) ───────────────────────────────────

def _get_chat_history(phone: str) -> SQLChatMessageHistory:
    return SQLChatMessageHistory(
        session_id=phone,
        connection_string=f"sqlite:///{SQLITE_DB_PATH}",
    )


def get_history_messages(phone: str) -> list[dict]:
    """Retorna los últimos 20 mensajes en formato OpenAI (10 pares usuario/asistente)."""
    history = _get_chat_history(phone)
    messages = []
    for msg in history.messages[-20:]:
        if isinstance(msg, HumanMessage):
            messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            messages.append({"role": "assistant", "content": msg.content})
    return messages


def save_to_memory(phone: str, user_msg: str, assistant_msg: str) -> None:
    """Persiste el par pregunta/respuesta en SQLite."""
    history = _get_chat_history(phone)
    history.add_user_message(user_msg)
    history.add_ai_message(assistant_msg)



# ── TTS (solo respuestas cortas) ───────────────────────────────────────────────

def _generate_tts(phone: str, text: str) -> str | None:
    """
    Genera audio con OpenAI TTS solo si el texto es corto (≤ TTS_MAX_CHARS).
    Retorna la ruta del archivo .mp3 o None si no aplica o si falla.
    """
    if len(text) > TTS_MAX_CHARS:
        logger.debug("TTS omitido — respuesta larga (%d chars > %d)", len(text), TTS_MAX_CHARS)
        return None

    try:
        safe_phone = phone.replace("+", "").replace("@", "_").replace(":", "")
        audio_path = f"audio_{safe_phone}_{int(datetime.now().timestamp())}.mp3"

        response = client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text,
        )
        response.stream_to_file(audio_path)
        logger.info("TTS generado: %s (%d chars)", audio_path, len(text))
        return audio_path

    except APIError as e:
        logger.warning("TTS APIError (no crítico): %s", e)
        return None
    except Exception as e:
        logger.warning("TTS falló (no crítico): %s", e)
        return None


# ── Agente principal ───────────────────────────────────────────────────────────

def run_agent(phone: str, user_message: str) -> dict:
    """
    Procesa un mensaje con el agente completo:
    memoria de largo plazo + tool calling + manejo de errores + TTS opcional.

    Args:
        phone:        Identificador único del usuario (número WhatsApp).
        user_message: Texto enviado por el usuario.

    Returns:
        {
            "reply":      str   — Respuesta textual del agente,
            "audio_path": str|None — Ruta al .mp3 TTS (None si no aplica),
            "tool_used":  str|None — Nombre de la herramienta invocada (None si ninguna),
        }
    """
    history   = get_history_messages(phone)
    tool_used = None
    reply     = None

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += history
    messages.append({"role": "user", "content": user_message})

    try:
        # ── Primera llamada: puede invocar una herramienta ─────────────────────
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=512,
            temperature=0.7,
        )
        msg = response.choices[0].message

        # ── Tool Calling ───────────────────────────────────────────────────────
        if msg.tool_calls:
            tool_call  = msg.tool_calls[0]
            tool_name  = tool_call.function.name
            tool_args  = json.loads(tool_call.function.arguments)
            tool_used  = tool_name

            tool_result = ejecutar_herramienta(tool_name, tool_args)

            # Segunda llamada incluyendo el resultado de la herramienta
            messages.append(msg)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })

            final = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=512,
                temperature=0.7,
            )
            reply = final.choices[0].message.content

        else:
            reply = msg.content

    except RateLimitError:
        logger.error("RateLimitError para phone=%s", phone)
        reply = "🙏 En este momento tenemos alta demanda. Por favor intenta en unos minutos. Dios le bendiga."

    except APIConnectionError:
        logger.error("APIConnectionError para phone=%s", phone)
        reply = "⚠️ Tuve un problema de conexión. Por favor intenta nuevamente en unos momentos."

    except APIError as e:
        logger.error("APIError para phone=%s: %s", phone, e)
        reply = "⚠️ Ocurrió un error inesperado con el servicio de IA. Por favor intenta en unos momentos."

    except Exception as e:
        logger.error("Error inesperado en agente para phone=%s: %s", phone, e)
        reply = "⚠️ Tuve un problema procesando tu mensaje. Por favor intenta de nuevo."

    # Guardar en memoria solo si la respuesta fue exitosa
    is_error = reply and (reply.startswith("⚠️") or reply.startswith("🙏"))
    if reply and not is_error:
        save_to_memory(phone, user_message, reply)

    # Generar TTS solo para respuestas cortas
    audio_path = _generate_tts(phone, reply) if reply and not is_error else None

    return {
        "reply":      reply,
        "audio_path": audio_path,
        "tool_used":  tool_used,
    }




# ── PostgreSQL — Persistencia de usuarios ─────────────────────────────────

_DB_CFG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "dbname":   os.getenv("DB_NAME",     "evolution"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", "evopass2025"),
}

def _db():
    return psycopg2.connect(**_DB_CFG, connect_timeout=5)

def _init_tabla():
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS usuarios_interacciones (
                        id                  SERIAL PRIMARY KEY,
                        nickname            VARCHAR(100),
                        session_id          VARCHAR(200),
                        fecha_entrada       TIMESTAMP DEFAULT NOW(),
                        idioma              VARCHAR(10),
                        servicio_consultado VARCHAR(300),
                        pidio_cita          BOOLEAN   DEFAULT FALSE,
                        datos_adicionales   JSONB     DEFAULT '{}',
                        historial_chat      JSONB     DEFAULT '[]'
                    );
                    CREATE INDEX IF NOT EXISTS idx_ui_nick ON usuarios_interacciones(nickname);
                    CREATE INDEX IF NOT EXISTS idx_ui_sid  ON usuarios_interacciones(session_id);
                """)
            conn.commit()
        logger.info("PostgreSQL: tabla usuarios_interacciones OK")
    except Exception as exc:
        logger.warning("PostgreSQL init (no critico): %s", exc)

def _registrar_sesion(nickname: str, session_id: str, idioma: str = "es"):
    if not nickname or not session_id:
        return
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO usuarios_interacciones (nickname, session_id, idioma)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (session_id) DO UPDATE SET
                        nickname     = EXCLUDED.nickname,
                        idioma       = EXCLUDED.idioma,
                        fecha_entrada = NOW()
                """, (nickname, session_id, idioma))
            conn.commit()
    except Exception as exc:
        logger.warning("DB registrar_sesion: %s", exc)

def _detectar_intenciones(text: str) -> dict:
    t = text.lower()
    result = {"pidio_cita": False, "servicio": None, "id_encontrado": None}
    if any(w in t for w in ["cita", "appointment", "agendar", "schedule", "reunion", "meeting"]):
        result["pidio_cita"] = True
        result["servicio"] = "citas"
    elif any(w in t for w in ["precio", "price", "costo", "cost", "tarifa", "fee", "cuanto", "how much"]):
        result["servicio"] = "precios"
    elif any(w in t for w in ["taxes", "impuesto", "tax return", "itin", "ssn", "ein", "declaracion"]):
        result["servicio"] = "taxes"
    elif any(w in t for w in ["inmigracion", "immigration", "visa", "green card", "citizenship", "naturalizacion"]):
        result["servicio"] = "immigration"
    m = re.search(r"\b\d{6,12}\b", text)
    if m:
        result["id_encontrado"] = m.group()
    return result


# ── Especialistas ATO Financial ───────────────────────────────────────────

ESPECIALISTAS = {
    "taxes":       "Luis",
    "immigration": "Marta",
    "citas":       "Marta",
    "precios":     "Carlos",
    "default":     "Equipo ATO",
}


def _asignar_responsable(servicio: str) -> str:
    return ESPECIALISTAS.get(servicio or "default", ESPECIALISTAS["default"])


def _notificar_cita(nickname: str, servicio: str, responsable: str) -> None:
    msg = (
        f"[CITA] Nueva solicitud de '{nickname}' "
        f"para '{servicio}' → asignada a {responsable}"
    )
    logger.info(msg)
    webhook_url = os.getenv("WEBHOOK_CITAS", "")
    if webhook_url:
        try:
            requests.post(webhook_url, json={
                "text":        msg,
                "nickname":    nickname,
                "servicio":    servicio,
                "responsable": responsable,
                "timestamp":   datetime.now().isoformat(),
            }, timeout=5)
            logger.info("[WEBHOOK] Notificacion enviada OK")
        except Exception as exc:
            logger.warning("[WEBHOOK] Fallo (no critico): %s", exc)

def _actualizar_interaccion(session_id: str, nickname: str, intenciones: dict):
    if not session_id:
        return
    try:
        updates, params = [], []
        responsable = None
        if intenciones.get("servicio"):
            updates.append("servicio_consultado = %s")
            params.append(intenciones["servicio"])
        if intenciones.get("pidio_cita"):
            updates.append("pidio_cita = TRUE")
            updates.append("estado_cita = 'pendiente'")
            responsable = _asignar_responsable(intenciones.get("servicio"))
            updates.append("responsable = %s")
            params.append(responsable)
        if intenciones.get("id_encontrado"):
            updates.append("datos_adicionales = datos_adicionales || %s::jsonb")
            params.append(json.dumps({"id_cedula": intenciones["id_encontrado"]}))
        if not updates:
            return
        params.append(session_id)
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE usuarios_interacciones SET "
                    + ", ".join(updates)
                    + " WHERE session_id = %s",
                    params,
                )
            conn.commit()
        if responsable:
            _notificar_cita(nickname, intenciones.get("servicio", ""), responsable)
    except Exception as exc:
        logger.warning("DB actualizar_interaccion: %s", exc)

def _guardar_mensaje(session_id: str, user_msg: str, bot_reply: str):
    if not session_id:
        return
    try:
        nuevos = json.dumps([
            {"r": "u", "m": user_msg[:500],  "t": datetime.now().isoformat()},
            {"r": "b", "m": bot_reply[:500], "t": datetime.now().isoformat()},
        ])
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE usuarios_interacciones
                    SET historial_chat = (
                        SELECT jsonb_agg(elem ORDER BY (elem->>'t'))
                        FROM (
                            SELECT elem FROM jsonb_array_elements(historial_chat) AS elem
                            UNION ALL
                            SELECT elem FROM jsonb_array_elements(%s::jsonb) AS elem
                        ) sub
                        LIMIT 20
                    )
                    WHERE session_id = %s
                """, (nuevos, session_id))
            conn.commit()
    except Exception as exc:
        logger.warning("DB guardar_mensaje: %s", exc)

def _cargar_historial(nickname: str) -> str:
    if not nickname:
        return ""
    try:
        with _db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT historial_chat FROM usuarios_interacciones
                    WHERE nickname = %s AND jsonb_array_length(historial_chat) > 0
                    ORDER BY fecha_entrada DESC LIMIT 1
                """, (nickname,))
                row = cur.fetchone()
        if not row or not row["historial_chat"]:
            return ""
        msgs = row["historial_chat"][-10:]
        lines = []
        for m in msgs:
            role = "Cliente" if m.get("r") == "u" else "Colibry"
            lines.append(f"{role}: {m.get('m', '')}")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("DB cargar_historial: %s", exc)
        return ""

# ── Flask App ──────────────────────────────────────────────────────────────────

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    """Muestra el dashboard con el botón de activación."""
    return render_template("index.html")


@app.route("/ejecutar", methods=["POST"])
def ejecutar():
    data       = request.get_json(silent=True) or {}
    message    = data.get("message", data.get("mensaje", "Hola")).strip()
    session_id = data.get("session_id", data.get("phone", "web_user"))
    nickname   = data.get("nickname", "").strip()
    idioma     = data.get("lang", "es")

    logger.info("[/ejecutar] nick=%s session=%s lang=%s", nickname, session_id, idioma)

    # Registro en PostgreSQL
    _registrar_sesion(nickname, session_id, idioma)

    # Cargar historial previo si es usuario que regresa
    historial = _cargar_historial(nickname)
    if nickname and historial:
        question = (
            f"[Cliente: {nickname}]\n"
            f"[Historial previo de esta conversacion]:\n{historial}\n"
            f"[Mensaje actual]: {message}"
        )
    elif nickname:
        question = f"[El cliente se llama: {nickname}] {message}"
    else:
        question = message

    try:
        flowise_url = (
            f"{os.getenv('FLOWISE_BASE_URL', '')}/api/v1/prediction/"
            f"{os.getenv('FLOWISE_FLOW_ID', '')}"
        )
        headers = {"Content-Type": "application/json"}
        api_key = os.getenv("FLOWISE_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "question":       question,
            "overrideConfig": {"sessionId": session_id},
        }
        resp = requests.post(flowise_url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        rjson     = resp.json()
        bot_reply = rjson.get("text", rjson.get("answer", ""))

        # Detectar intenciones y persistir
        intenciones = _detectar_intenciones(message + " " + bot_reply)
        _actualizar_interaccion(session_id, nickname, intenciones)
        _guardar_mensaje(session_id, message, bot_reply)

        return jsonify({"status": "ok", "mensaje": bot_reply, "session_id": session_id})

    except Exception as exc:
        logger.error("[/ejecutar] error: %s", exc)
        return jsonify({"status": "error", "mensaje": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "online", "motor": "gpt-4o-mini", "memoria": "sqlite"})





# ── Proxy Flowise ──────────────────────────────────────────────────────────────

@app.route("/flowise/chat", methods=["POST"])
def flowise_chat():
    # Proxy: reenvía la petición del frontend a Flowise y retorna la respuesta.
    # Body JSON: { "message": "texto", "session_id": "opcional" }
    data       = request.get_json(silent=True) or {}
    message    = data.get("message", "").strip()
    session_id = data.get("session_id", "web_user")

    if not message:
        return jsonify({"error": "Campo 'message' requerido"}), 400

    if not FLOWISE_URL or not FLOWISE_FLOW_ID:
        return jsonify({"error": "Flowise no configurado en el servidor"}), 503

    endpoint = f"{FLOWISE_URL}/api/v1/prediction/{FLOWISE_FLOW_ID}"
    headers  = {"Content-Type": "application/json"}
    if FLOWISE_API_KEY:
        headers["Authorization"] = f"Bearer {FLOWISE_API_KEY}"

    payload = {
        "question":  message,
        "overrideConfig": {"sessionId": session_id},
    }

    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        flowise_data = resp.json()
        # Normalizar: Flowise puede devolver 'text' o 'answer'
        reply = flowise_data.get("text") or flowise_data.get("answer") or str(flowise_data)
        logger.info("[/flowise/chat] session=%s respuesta=%d chars", session_id, len(reply))
        return jsonify({"status": "ok", "reply": reply, "raw": flowise_data})

    except requests.Timeout:
        logger.error("[/flowise/chat] Timeout conectando a Flowise")
        return jsonify({"error": "Flowise no responde (timeout 30s)"}), 504

    except requests.HTTPError as e:
        logger.error("[/flowise/chat] HTTPError: %s", e)
        return jsonify({"error": f"Flowise retornó error {resp.status_code}"}), 502

    except Exception as e:
        logger.error("[/flowise/chat] Error: %s", e)
        return jsonify({"error": "Error interno conectando a Flowise"}), 500


# ── TTS (Text-to-Speech via OpenAI) ───────────────────────────────────────────

@app.route("/tts", methods=["POST"])
def tts_endpoint():
    # Recibe { "text": "...", "lang": "es"|"en" }
    # Devuelve audio/mpeg generado con OpenAI TTS
    from flask import send_file
    import io
    data  = request.get_json(silent=True) or {}
    text  = data.get("text", "").strip()
    lang  = data.get("lang", "es")

    if not text:
        return jsonify({"error": "Texto requerido"}), 400

    # Truncar para evitar audios muy largos (max ~600 chars)
    text = text[:600]
    # Nova (ES) / Shimmer (EN) — tono profesional en ambos casos
    # Voz por idioma: nova (ES), shimmer (EN), alloy (FR/DE)
    voice_map = {"es": "nova", "en": "shimmer", "fr": "alloy", "de": "alloy"}
    voice = data.get("voice") or voice_map.get(lang, "nova")

    try:
        resp = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
        )
        audio_bytes = resp.read()
        logger.info("[/tts] lang=%s voice=%s chars=%d", lang, voice, len(text))
        return Response(
            audio_bytes,
            mimetype="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=response.mp3"},
        )
    except Exception as e:
        logger.error("[/tts] error: %s", e)
        return jsonify({"error": str(e)}), 500

# ── Panel de Control /status ───────────────────────────────────────────────────

_STATUS_USER = "aton2026"
_STATUS_PASS = "Dispatch2026"


def _require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != _STATUS_USER or auth.password != _STATUS_PASS:
            return Response(
                "Panel restringido.",
                401,
                {"WWW-Authenticate": 'Basic realm="Colibry Panel"'},
            )
        return f(*args, **kwargs)
    return decorated


def _port_open(port, host="127.0.0.1", timeout=1):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _http_ok(url, timeout=5):
    """Verifica que una URL externa responda con HTTP 2xx o 3xx."""
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        return r.status_code < 500
    except Exception:
        return False


def _parse_log():
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.log")
    today = datetime.now().strftime("%Y-%m-%d")
    msgs_today = 0
    last_msg = "Sin mensajes aun"
    tools_used = []
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "/ejecutar" in line and "accion=" in line:
                    if today in line:
                        msgs_today += 1
                    last_msg = line[:19]
                if "[TOOL]" in line:
                    parts = line.split("[TOOL]")
                    if len(parts) > 1:
                        tool_name = parts[1].split("|")[0].strip()
                        tools_used.append({"ts": line[:19], "name": tool_name})
    except Exception:
        pass
    return msgs_today, last_msg, tools_used[-10:]


@app.route("/status")
@_require_auth
def status_panel():
    msgs_today, last_msg, tools = _parse_log()
    # Flowise corre en Railway (externo) — verificar via HTTP
    flowise_ext_url = FLOWISE_URL  # desde .env
    flowise_ok_ext  = bool(flowise_ext_url) and _http_ok(flowise_ext_url)
    flowise_port_local = next((p for p in [3000, 3001] if _port_open(p)), None)
    flowise_port  = flowise_port_local or ("Railway" if flowise_ok_ext else None)
    # n8n corre local en Docker — verificar puerto
    n8n_ports     = [5678, 3001, 3000]
    n8n_port      = next((p for p in n8n_ports if _port_open(p)), None)
    try:
        uptime_str = subprocess.check_output(["uptime", "-p"], text=True).strip()
    except Exception:
        uptime_str = "N/A"
    return render_template(
        "status.html",
        bot_ok       = True,
        evolution_ok = _port_open(8080),
        flowise_ok   = flowise_ok_ext or (flowise_port is not None),
        flowise_port = flowise_port or ("Railway" if flowise_ok_ext else "—"),
        n8n_ok       = n8n_port is not None,
        n8n_port     = n8n_port or "—",
        msgs_today   = msgs_today,
        last_msg     = last_msg,
        tools        = tools,
        uptime       = uptime_str,
        now          = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )



# ── Admin CRM Dashboard ────────────────────────────────────────────────────

@app.route("/admin")
@_require_auth
def admin_dashboard():
    return render_template("admin.html")


@app.route("/admin/api/stats")
@_require_auth
def admin_stats():
    try:
        with _db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT COUNT(DISTINCT nickname) AS t FROM usuarios_interacciones"
                    " WHERE nickname IS NOT NULL AND nickname != ''"
                )
                total_usuarios = cur.fetchone()["t"] or 0
                cur.execute(
                    "SELECT COUNT(DISTINCT nickname) AS tot,"
                    " SUM(CASE WHEN pidio_cita THEN 1 ELSE 0 END) AS citas"
                    " FROM usuarios_interacciones"
                    " WHERE nickname IS NOT NULL AND nickname != ''"
                )
                row = cur.fetchone()
                tot = row["tot"] or 0
                citas = row["citas"] or 0
                tasa = round(citas / tot * 100, 1) if tot > 0 else 0.0
                cur.execute(
                    "SELECT idioma, COUNT(*) AS c FROM usuarios_interacciones"
                    " WHERE idioma IS NOT NULL GROUP BY idioma ORDER BY c DESC LIMIT 1"
                )
                lr = cur.fetchone()
                idioma_top = (lr["idioma"] or "ES").upper() if lr else "ES"
                cur.execute("SELECT COUNT(*) AS t FROM usuarios_interacciones")
                total_int = cur.fetchone()["t"] or 0
                cur.execute(
                    "SELECT COUNT(*) AS t FROM usuarios_interacciones"
                    " WHERE pidio_cita = TRUE AND estado_cita = 'pendiente'"
                )
                citas_pend = cur.fetchone()["t"] or 0
        return jsonify({
            "total_usuarios":     total_usuarios,
            "tasa_citas":         tasa,
            "con_cita":           citas,
            "idioma_top":         idioma_top,
            "total_interacciones": total_int,
            "citas_pendientes":   citas_pend,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/admin/api/chart/servicios")
@_require_auth
def admin_chart_servicios():
    try:
        with _db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT COALESCE(NULLIF(servicio_consultado,''),'Sin especificar') AS s,"
                    " COUNT(*) AS c FROM usuarios_interacciones GROUP BY s ORDER BY c DESC"
                )
                rows = cur.fetchall()
        return jsonify({"labels": [r["s"] for r in rows], "data": [r["c"] for r in rows]})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/admin/api/chart/flujo")
@_require_auth
def admin_chart_flujo():
    try:
        with _db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT TO_CHAR(DATE_TRUNC('hour', fecha_entrada), 'DD/MM HH24:00') AS h,"
                    " COUNT(*) AS c"
                    " FROM usuarios_interacciones"
                    " WHERE fecha_entrada >= NOW() - INTERVAL '30 days'"
                    " GROUP BY DATE_TRUNC('hour', fecha_entrada)"
                    " ORDER BY DATE_TRUNC('hour', fecha_entrada)"
                )
                rows = cur.fetchall()
        return jsonify({"labels": [r["h"] for r in rows], "data": [r["c"] for r in rows]})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/admin/api/citas")
@_require_auth
def admin_citas():
    responsable = request.args.get("responsable", "").strip()
    try:
        with _db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if responsable:
                    cur.execute(
                        "SELECT id, nickname, fecha_entrada::text, idioma,"
                        " servicio_consultado, responsable, estado_cita, datos_adicionales, historial_chat"
                        " FROM usuarios_interacciones"
                        " WHERE pidio_cita = TRUE AND responsable ILIKE %s"
                        " ORDER BY fecha_entrada DESC LIMIT 50",
                        (f"%{responsable}%",),
                    )
                else:
                    cur.execute(
                        "SELECT id, nickname, fecha_entrada::text, idioma,"
                        " servicio_consultado, responsable, estado_cita, datos_adicionales, historial_chat"
                        " FROM usuarios_interacciones"
                        " WHERE pidio_cita = TRUE"
                        " ORDER BY estado_cita ASC, fecha_entrada DESC LIMIT 50"
                    )
                rows = [dict(r) for r in cur.fetchall()]
        return jsonify(rows)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/admin/api/cita/estado", methods=["POST"])
@_require_auth
def admin_cita_estado():
    data   = request.get_json(silent=True) or {}
    cita_id = data.get("id")
    estado  = data.get("estado", "pendiente")
    if not cita_id:
        return jsonify({"error": "id requerido"}), 400
    estados_validos = ["pendiente", "confirmada", "completada", "cancelada"]
    if estado not in estados_validos:
        return jsonify({"error": f"estado invalido, usa: {estados_validos}"}), 400
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE usuarios_interacciones SET estado_cita = %s WHERE id = %s",
                    (estado, cita_id),
                )
            conn.commit()
        return jsonify({"ok": True, "id": cita_id, "estado": estado})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/admin/api/buscar")
@_require_auth
def admin_buscar():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    try:
        with _db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, nickname, fecha_entrada::text, idioma,"
                    " servicio_consultado, pidio_cita, responsable, estado_cita,"
                    " datos_adicionales, historial_chat"
                    " FROM usuarios_interacciones WHERE nickname ILIKE %s"
                    " ORDER BY fecha_entrada DESC LIMIT 20",
                    (f"%{q}%",),
                )
                rows = [dict(r) for r in cur.fetchall()]
        return jsonify(rows)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/admin/api/export/csv")
@_require_auth
def admin_export_csv():
    import csv as _csv
    import io as _sio
    responsable = request.args.get("responsable", "").strip()
    try:
        with _db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if responsable:
                    cur.execute(
                        "SELECT id, nickname, fecha_entrada::text, idioma,"
                        " servicio_consultado, pidio_cita, responsable, estado_cita,"
                        " datos_adicionales::text"
                        " FROM usuarios_interacciones WHERE responsable ILIKE %s"
                        " ORDER BY fecha_entrada DESC",
                        (f"%{responsable}%",),
                    )
                else:
                    cur.execute(
                        "SELECT id, nickname, fecha_entrada::text, idioma,"
                        " servicio_consultado, pidio_cita, responsable, estado_cita,"
                        " datos_adicionales::text"
                        " FROM usuarios_interacciones ORDER BY fecha_entrada DESC"
                    )
                rows = cur.fetchall()
        buf = _sio.StringIO()
        fields = ["id","nickname","fecha_entrada","idioma",
                  "servicio_consultado","pidio_cita","responsable","estado_cita","datos_adicionales"]
        w = _csv.DictWriter(buf, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
        fname = f"citas_{responsable or 'todos'}_colibry.csv"
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={fname}"},
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info("Colibry Bot Server iniciando en puerto %s", port)
    app.run(host="0.0.0.0", port=port, debug=False)
