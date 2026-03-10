"""
Webhook WhatsApp — Router FastAPI
Recibe y procesa mensajes de Meta/WhatsApp Business API
"""
import os
import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

WHATSAPP_TOKEN    = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
VERIFY_TOKEN      = os.getenv("VERIFY_TOKEN", "ato_secret_2025")
WA_API_URL        = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"

# El agente se inyecta desde main.py
ato_agent = None


def set_agent(agent):
    global ato_agent
    ato_agent = agent


# ── Verificación del webhook (GET) ────────────────────────────
@router.get("/webhook")
async def verify_webhook(request: Request):
    params = dict(request.query_params)
    if (params.get("hub.mode") == "subscribe" and
            params.get("hub.verify_token") == VERIFY_TOKEN):
        print("✅ Webhook verificado por Meta")
        return JSONResponse(content=int(params["hub.challenge"]))
    raise HTTPException(status_code=403, detail="Token inválido")


# ── Recepción de mensajes (POST) ──────────────────────────────
@router.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()

    try:
        value = body["entry"][0]["changes"][0]["value"]

        # Ignorar notificaciones de entrega/lectura
        if "messages" not in value:
            return JSONResponse(content={"status": "ok"})

        msg      = value["messages"][0]
        sender   = msg["from"]
        msg_type = msg.get("type", "")

        print(f"📩 Mensaje de {sender} | tipo: {msg_type}")

        # Mensajes que no son texto
        if msg_type != "text":
            await send_whatsapp(sender,
                "Por el momento solo proceso texto. ¿En qué puedo ayudarte? 😊\n\n"
                "I currently only process text messages. How can I help? 😊"
            )
            return JSONResponse(content={"status": "ok"})

        user_text = msg["text"]["body"].strip()
        print(f"   💬 [{sender}]: {user_text[:80]}")

        # Procesar con el agente
        result = ato_agent.process(sender, user_text)

        # Enviar bienvenida si es usuario nuevo
        if result["is_new"] and result["welcome"]:
            await send_whatsapp(sender, result["welcome"])

        # Enviar respuesta de Claude
        await send_whatsapp(sender, result["reply"])

    except (KeyError, IndexError) as e:
        print(f"⚠️  Error parseando webhook: {e}")

    return JSONResponse(content={"status": "ok"})


# ── Enviar mensaje por WhatsApp ───────────────────────────────
async def send_whatsapp(to: str, text: str):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        print(f"⚠️  WhatsApp no configurado. Mensaje para {to}:\n{text}")
        return

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient() as http:
        r = await http.post(WA_API_URL, json=payload, headers=headers)
        status = "✅" if r.status_code == 200 else f"❌ {r.status_code}"
        print(f"   {status} Enviado a {to}")
