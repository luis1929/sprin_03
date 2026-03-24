"""
Colibry Bot Server — Agente Inteligente con Memoria
Motor: OpenAI GPT-4o-mini + LangChain + SQLite
Personalidad: Administrador Eclesiástico — Iglesia en Barranquilla
"""

import json
import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from langchain_community.chat_message_histories import SQLChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage
from openai import APIConnectionError, APIError, OpenAI, RateLimitError

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "colibry_memory.db")
TTS_MAX_CHARS  = int(os.getenv("TTS_MAX_CHARS", "300"))


# ── System Prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres *Colibry*, el Asistente Administrativo Eclesiástico de nuestra Iglesia en Barranquilla, Colombia.

PERSONALIDAD:
- Amable, formal y cercano. Tu tono es pastoral pero profesional.
- Siempre saludas con calidez cristiana: "Dios le bendiga", "Que el Señor le guíe", etc.
- Usas lenguaje claro y evitas tecnicismos innecesarios.
- Respondes siempre en español colombiano.
- Máximo 200 palabras por respuesta. Formato WhatsApp (*negrita*, emojis moderados 🙏).

CONOCIMIENTO DIAN PARA IGLESIAS:
- Las entidades religiosas están exentas del impuesto de renta (Art. 23 E.T.) si están
  reconocidas por el Ministerio del Interior como entidades sin ánimo de lucro.
- Los ingresos por diezmos, ofrendas y donaciones no son gravados, pero deben
  contabilizarse en libros de cuentas debidamente registrados.
- Si la iglesia contrata empleados, debe cumplir con aportes parafiscales:
  SENA (2%), ICBF (3%) y Caja de Compensación Familiar (4%).
- Las iglesias pueden recibir donaciones deducibles de renta para sus donantes
  si están certificadas como entidades del Régimen Tributario Especial (RTE).
- Deben presentar declaración de activos en el exterior si aplica (Art. 607 E.T.).

REGLAS:
- Nunca des asesoría legal definitiva. Siempre recomienda consultar con un contador
  o abogado para casos específicos.
- Si el hermano menciona su nombre, recuérdalo y úsalo en las siguientes respuestas.
- Usa el historial de conversación para dar respuestas contextuales y personalizadas.
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


# ── Flask App ──────────────────────────────────────────────────────────────────

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    """Muestra el dashboard con el botón de activación."""
    return render_template("index.html")


@app.route("/ejecutar", methods=["POST"])
def ejecutar():
    """
    Recibe el clic del botón del dashboard.
    Acepta JSON opcional con { accion, origen, phone, mensaje }.
    """
    data    = request.get_json(silent=True) or {}
    accion  = data.get("accion", "activar_flujo")
    origen  = data.get("origen", "dashboard")
    phone   = data.get("phone", "dashboard_user")
    mensaje = data.get("mensaje", "Hola, activa el flujo Colibry")

    logger.info("[/ejecutar] accion=%s origen=%s phone=%s", accion, origen, phone)

    try:
        result = run_agent(phone=phone, user_message=mensaje)
        return jsonify({
            "status":     "ok",
            "mensaje":    result["reply"],
            "tool_used":  result["tool_used"],
            "audio_path": result["audio_path"],
        })
    except Exception as e:
        logger.error("[/ejecutar] error: %s", e)
        return jsonify({"status": "error", "mensaje": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "online", "motor": "gpt-4o-mini", "memoria": "sqlite"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info("Colibry Bot Server iniciando en puerto %s", port)
    app.run(host="0.0.0.0", port=port, debug=False)
