# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ATOBot v3.0 — A WhatsApp chatbot for America's Tax Office (ATO Financial) built with FastAPI, OpenAI GPT-4o-mini, and PostgreSQL. It handles inbound WhatsApp messages via the Meta Cloud API webhook, processes them through an AI agent with per-user conversation history, and replies via the WhatsApp API.

## Commands

### Run the server
```bash
uvicorn main:app --reload --port 8000
```

### Install dependencies
```bash
pip install -r requirements.txt
```

### Test the bot locally (without WhatsApp)
```bash
curl -X POST http://localhost:8000/test/chat \
  -H "Content-Type: application/json" \
  -d '{"phone": "test_user", "message": "Hola"}'
```

### Start infrastructure (PostgreSQL + pgAdmin + n8n)
```bash
docker compose -f docker-compose-colibry.yml up -d
```

## Architecture

### Request Flow
1. Meta sends a POST to `/webhook` with the WhatsApp message payload.
2. `whatsapp_router.py` parses the payload, extracts `sender` and `user_text`.
3. `ato_agent.process(phone, message)` is called — it looks up or creates a session, detects language (ES/EN), fetches the last 10 message pairs from PostgreSQL, calls OpenAI, saves the new messages, and returns the reply.
4. The router sends the reply back via `send_whatsapp()` (async HTTPX POST to Meta Graph API).

### Key Files
- `main.py` — App entry point. Creates the SQLAlchemy engine, instantiates `ATOAgent`, injects it into the router via `set_agent()`, mounts the dashboard at `/`.
- `app/agents/ato_agent.py` — Core logic: session management, language detection, OpenAI calls (`gpt-4o-mini`), and conversation persistence. Also exposes dashboard query methods.
- `app/routers/whatsapp_router.py` — Webhook endpoints: GET for Meta verification challenge, POST for incoming messages. Agent is injected at startup via module-level global.
- `app/database/connection.py` — Standalone engine/session factory (currently not used by `main.py`, which creates its own engine directly).
- `app/services/stats_service.py` — Dashboard stats queries (currently not used by `main.py`, which calls agent methods directly).
- `templates/dashboard.html` — Jinja2 template rendered at `/`.

### Database Tables (auto-created on startup)
- `whatsapp_sessions` — One row per phone number, tracks `language` and `last_seen`.
- `ato_conversaciones` — Full conversation log with `phone`, `role` (`user`/`assistant`), `content`. Indexed on `(phone, created_at)`.

### Known Inconsistencies
- `whatsapp_router.py` references `result["welcome"]` and `result["reply"]`, but `ATOAgent.process()` returns `result["response"]` and `result["is_new"]`. This will cause a `KeyError` on new-user messages in production.
- `app/database/connection.py` and `app/services/stats_service.py` are unused by the main app flow.
- `health` endpoint reports `ai_model: claude-sonnet-4-6` but the agent actually calls `gpt-4o-mini`.

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key |
| `WHATSAPP_TOKEN` | Meta permanent access token |
| `WHATSAPP_PHONE_ID` | Meta phone number ID |
| `VERIFY_TOKEN` | Webhook verification token (must match Meta dashboard) |
| `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` / `DB_NAME` | PostgreSQL connection (default port: 5433) |
