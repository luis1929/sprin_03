"""
Conexión a PostgreSQL — reutiliza tu config de APP_colibry
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST     = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT     = os.getenv("DB_PORT", "5433")
DB_NAME     = os.getenv("DB_NAME", "contabilidad_ai")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Crea las tablas de ATOBot si no existen."""
    with engine.connect() as conn:

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS whatsapp_sessions (
                id          SERIAL PRIMARY KEY,
                phone       VARCHAR(20) UNIQUE NOT NULL,
                user_name   VARCHAR(100),
                language    VARCHAR(5) DEFAULT 'es',
                created_at  TIMESTAMP DEFAULT NOW(),
                last_seen   TIMESTAMP DEFAULT NOW()
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ato_conversaciones (
                id          SERIAL PRIMARY KEY,
                phone       VARCHAR(20) NOT NULL,
                role        VARCHAR(20) NOT NULL,
                content     TEXT,
                created_at  TIMESTAMP DEFAULT NOW()
            )
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_ato_conv_phone
            ON ato_conversaciones(phone, created_at)
        """))

        conn.commit()
        print("✅ Tablas ATOBot verificadas/creadas en PostgreSQL")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
