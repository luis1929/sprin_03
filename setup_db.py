import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "dWkIhlqEoNLYdSDinnjLIFajaxXdYjpL")
DB_HOST     = os.getenv("DB_HOST", "postgres.railway.internal")
DB_PORT     = os.getenv("DB_PORT", "5432")

# Conectar a 'postgres' primero (para crear la BD)
DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/postgres"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def create_database():
    """Crea la BD ato_financial"""
    with engine.connect() as conn:
        conn.execute(text("CREATE DATABASE ato_financial;"))
        conn.commit()
        print("✅ BD ato_financial creada")

def init_schema():
    """Crea el schema completo"""
    DB_NAME = "ato_financial"
    DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine2 = create_engine(DATABASE_URL, pool_pre_ping=True)
    
    with engine2.connect() as conn:
        # Lee el schema
        with open('001_initial_schema.sql', 'r') as f:
            sql = f.read()
        
        conn.execute(text(sql))
        conn.commit()
        print("✅ Schema creado en ato_financial")

if __name__ == "__main__":
    try:
        create_database()
    except Exception as e:
        if "already exists" in str(e):
            print("⚠️ BD ya existe")
        else:
            print(f"❌ Error: {e}")
    
    try:
        init_schema()
    except Exception as e:
        print(f"❌ Error en schema: {e}")