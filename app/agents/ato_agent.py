"""
Agente ATOBot — OpenAI GPT + Memoria PostgreSQL
"""

import os
from openai import OpenAI
from sqlalchemy import text, engine as sa_engine
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """
Eres *ATOBot*, el asistente virtual oficial de *America's Tax Office (ATO Financial)* — empresa familiar fundada en 2014 en Los Angeles, CA.

REGLA DE IDIOMA:
- Español → responde en español. Inglés → responde en inglés.

SOBRE ATO FINANCIAL:
- WhatsApp: +1 (321) 467-6888
- Horario: Lunes–Viernes 9:00 AM – 5:00 PM (PT)
- Web: www.atofinancial.com

SERVICIOS:
1. IMPUESTOS: Declaraciones W-2/1099, atrasos, deudas IRS, ITIN, OIC, EITC
2. SEGUROS: Salud (HMO/PPO/ACA), Vida (término/entera), Auto (SR-22), Hogar
3. BIENES RAÍCES: Compra/venta/renta, FHA, VA, Convencional, DSCR, Refinanciamiento

REGLAS:
- Máximo 250 palabras. Formato WhatsApp con *negrita* y emojis moderados.
- Siempre termina ofreciendo contacto:
  ES: "¿Quieres que un agente te contacte? 📲 +1 (321) 467-6888"
  EN: "Ready to speak with an agent? 📲 +1 (321) 467-6888"
- NO des tarifas específicas ni asesoría legal concreta.
"""

WELCOME_ES = """¡Hola! 👋 Soy *ATOBot*, el asistente virtual de *America's Tax Office*.

Estoy aquí para ayudarte con:
💼 *Impuestos* — declaraciones, deudas IRS, ITIN
🛡️ *Seguros* — salud, vida, auto y hogar
🏠 *Bienes Raíces & Préstamos* — compra, venta, hipotecas

¿Con cuál de estos servicios te puedo ayudar hoy? 😊"""

WELCOME_EN = """Hi there! 👋 I'm *ATOBot*, virtual assistant for *America's Tax Office*.

I'm here to help you with:
💼 *Taxes* — returns, IRS debt, ITIN
🛡️ *Insurance* — health, life, auto & home
🏠 *Real Estate & Loans* — buying, selling, mortgages

What can I help you with today? 😊"""


class ATOAgent:
    MAX_HISTORY = 10

    def __init__(self, db_engine=None):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.engine = db_engine
        if self.engine is None:
            from sqlalchemy import create_engine
            DB_URL = "postgresql+psycopg2://{}:{}@{}:{}/{}".format(
                os.getenv("DB_USER", "postgres"),
                os.getenv("DB_PASSWORD", ""),
                os.getenv("DB_HOST", "127.0.0.1"),
                os.getenv("DB_PORT", "5433"),
                os.getenv("DB_NAME", "contabilidad_ai"),
            )
            self.engine = create_engine(DB_URL)
        self._init_tables()

    def _init_tables(self):
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS whatsapp_sessions (
                    id         SERIAL PRIMARY KEY,
                    phone      VARCHAR(20) UNIQUE NOT NULL,
                    language   VARCHAR(5) DEFAULT 'es',
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_seen  TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ato_conversaciones (
                    id         SERIAL PRIMARY KEY,
                    phone      VARCHAR(20) NOT NULL,
                    role       VARCHAR(20) NOT NULL,
                    content    TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ato_conv_phone
                ON ato_conversaciones(phone, created_at)
            """))
            conn.commit()
        print("✅ Tablas ATOBot listas")

    def get_or_create_session(self, phone: str) -> dict:
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT id, language FROM whatsapp_sessions WHERE phone = :phone"),
                {"phone": phone}
            ).fetchone()
            if result:
                conn.execute(
                    text("UPDATE whatsapp_sessions SET last_seen = NOW() WHERE phone = :phone"),
                    {"phone": phone}
                )
                conn.commit()
                return {"is_new": False, "language": result[1]}
            else:
                conn.execute(
                    text("INSERT INTO whatsapp_sessions (phone, language) VALUES (:phone, 'es')"),
                    {"phone": phone}
                )
                conn.commit()
                return {"is_new": True, "language": "es"}

    def detect_language(self, msg: str) -> str:
        signals = ["á","é","í","ó","ú","ñ","¿","¡","hola","necesito",
                   "ayuda","impuesto","gracias","tengo","quiero","cómo"]
        return "es" if any(s in msg.lower() for s in signals) else "en"

    def update_language(self, phone: str, language: str):
        with self.engine.connect() as conn:
            conn.execute(
                text("UPDATE whatsapp_sessions SET language = :lang WHERE phone = :phone"),
                {"lang": language, "phone": phone}
            )
            conn.commit()

    def save_message(self, phone: str, role: str, content: str):
        with self.engine.connect() as conn:
            conn.execute(
                text("INSERT INTO ato_conversaciones (phone, role, content) VALUES (:phone, :role, :content)"),
                {"phone": phone, "role": role, "content": content}
            )
            conn.commit()

    def get_history(self, phone: str) -> list:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""SELECT role, content FROM ato_conversaciones
                        WHERE phone = :phone ORDER BY created_at ASC LIMIT :limit"""),
                {"phone": phone, "limit": self.MAX_HISTORY * 2}
            ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in rows]

    def call_openai(self, phone: str, user_message: str) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += self.get_history(phone)
        messages.append({"role": "user", "content": user_message})
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=1024
        )
        return response.choices[0].message.content

    def process(self, phone: str, user_message: str) -> dict:
        session = self.get_or_create_session(phone)
        language = self.detect_language(user_message)
        self.update_language(phone, language)

        if session["is_new"]:
            welcome = WELCOME_ES if language == "es" else WELCOME_EN
            self.save_message(phone, "assistant", welcome)
            self.save_message(phone, "user", user_message)
            response = self.call_openai(phone, user_message)
            self.save_message(phone, "assistant", response)
            return {"phone": phone, "response": f"{welcome}\n\n{response}", "is_new": True}

        self.save_message(phone, "user", user_message)
        response = self.call_openai(phone, user_message)
        self.save_message(phone, "assistant", response)
        return {"phone": phone, "response": response, "is_new": False}

    # ── Métodos para el dashboard ─────────────────────────────
    def total_users(self) -> int:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT COUNT(*) FROM whatsapp_sessions")).scalar() or 0

    def total_messages(self) -> int:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT COUNT(*) FROM ato_conversaciones")).scalar() or 0

    def recent_conversations(self, limit: int = 10) -> list:
        with self.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT ws.phone, COUNT(ac.id) as msgs, MAX(ac.created_at)::text as last
                FROM whatsapp_sessions ws
                LEFT JOIN ato_conversaciones ac ON ws.phone = ac.phone
                GROUP BY ws.phone
                ORDER BY MAX(ac.created_at) DESC NULLS LAST
                LIMIT :limit
            """), {"limit": limit}).fetchall()
        result = []
        for row in rows:
            phone = row[0]
            masked = phone[:3] + "****" + phone[-4:] if len(phone) > 7 else "***"
            last = str(row[2])[:16].replace("T", " ") if row[2] else "—"
            result.append({"phone": masked, "messages": row[1], "last_seen": last})
        return result