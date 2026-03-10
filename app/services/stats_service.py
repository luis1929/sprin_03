"""
Servicio de estadísticas para el dashboard.
Consulta PostgreSQL — tablas de ATOBot.
"""

from sqlalchemy import text
from app.database.connection import engine


def get_stats() -> dict:
    """Retorna estadísticas para el dashboard."""
    try:
        with engine.connect() as conn:

            total_users = conn.execute(
                text("SELECT COUNT(*) FROM whatsapp_sessions")
            ).scalar() or 0

            total_messages = conn.execute(
                text("SELECT COUNT(*) FROM ato_conversaciones")
            ).scalar() or 0

            rows = conn.execute(
                text("""
                    SELECT
                        ws.phone,
                        COUNT(ac.id) as msg_count,
                        MAX(ac.created_at)::text as last_seen
                    FROM whatsapp_sessions ws
                    LEFT JOIN ato_conversaciones ac ON ws.phone = ac.phone
                    GROUP BY ws.phone
                    ORDER BY MAX(ac.created_at) DESC NULLS LAST
                    LIMIT 10
                """)
            ).fetchall()

            conversations = []
            for row in rows:
                phone = row[0]
                masked = phone[:3] + "****" + phone[-4:] if len(phone) > 7 else "***"
                last = str(row[2])[:16].replace("T", " ") if row[2] else "—"
                conversations.append({
                    "phone": masked,
                    "messages": row[1],
                    "last_seen": last
                })

        return {
            "total_users": total_users,
            "total_messages": total_messages,
            "conversations": conversations,
        }

    except Exception as e:
        print(f"⚠️ Error obteniendo stats: {e}")
        return {
            "total_users": 0,
            "total_messages": 0,
            "conversations": [],
        }
