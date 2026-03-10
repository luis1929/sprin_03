"""
ATOBot — Main FastAPI App
America's Tax Office — WhatsApp Chatbot
"""
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine
from dotenv import load_dotenv

from app.agents.ato_agent import ATOAgent
from app.routers.whatsapp_router import router as whatsapp_router, set_agent

load_dotenv()

# ── Base de datos (tu PostgreSQL existente) ───────────────────
DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST     = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT     = os.getenv("DB_PORT", "5433")
DB_NAME     = os.getenv("DB_NAME", "contabilidad_ai")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

# ── Inicializar agente ────────────────────────────────────────
agent = ATOAgent(db_engine=engine)
set_agent(agent)

# ── FastAPI app ───────────────────────────────────────────────
app = FastAPI(
    title="ATOBot — America's Tax Office",
    version="3.0.0",
    description="WhatsApp Chatbot | Claude AI | PostgreSQL"
)

templates = Jinja2Templates(directory="templates")

# ── Incluir router WhatsApp ───────────────────────────────────
app.include_router(whatsapp_router)


# ── Dashboard ─────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {
        "request":        request,
        "total_users":    agent.total_users(),
        "total_messages": agent.total_messages(),
        "conversations":  agent.recent_conversations(),
    })


# ── Health check ──────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status":   "running",
        "bot":      "ATOBot v3.0",
        "company":  "America's Tax Office",
        "db":       DB_NAME,
        "ai_model": "claude-sonnet-4-6"
    }


# ── Test local (sin WhatsApp) ─────────────────────────────────
@app.post("/test/chat")
async def test_chat(request: Request):
    """Endpoint para probar el bot sin WhatsApp"""
    body = await request.json()
    phone   = body.get("phone", "test_user")
    message = body.get("message", "Hola")
    result  = agent.process(phone, message)
    return result
