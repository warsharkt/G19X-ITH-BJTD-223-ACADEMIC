"""Conexion central a PostgreSQL. Todo el backend importa el engine de aqui.

Dos formas de configurarla en el .env:
  - DATABASE_URL: cadena completa (Supabase u otro PostgreSQL en la nube).
    Tiene prioridad si existe.
  - POSTGRES_USER/PASSWORD/DB + DB_HOST/DB_PORT: el PostgreSQL local de
    Docker (docker-compose.yml). Es lo que se usa si no hay DATABASE_URL.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url

# .env en la raiz del proyecto (backend/app/database.py -> subir 2 niveles)
RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(RAIZ / ".env")


def _url_desde_entorno() -> URL:
    cadena = os.getenv("DATABASE_URL", "").strip()
    if not cadena:
        return URL.create(
            "postgresql+psycopg",
            username=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5433")),
            database=os.getenv("POSTGRES_DB"),
        )
    url = make_url(cadena)
    # Supabase entrega "postgresql://...": se indica el driver que usamos
    url = url.set(drivername="postgresql+psycopg")
    # Fuera de este equipo la conexion siempre va cifrada
    if url.host not in ("localhost", "127.0.0.1") and "sslmode" not in url.query:
        url = url.update_query_dict({"sslmode": "require"})
    return url


DB_URL = _url_desde_entorno()
ES_REMOTA = DB_URL.host not in ("localhost", "127.0.0.1", None)

# connect_timeout: si PostgreSQL no responde, fallar en segundos (por defecto 5)
# en lugar de quedarse esperando minutos.
_args = {"connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "5"))}
if DB_URL.port == 6543:
    # "Transaction pooler" de Supabase: no admite sentencias preparadas
    # (se recomienda el "Session pooler", puerto 5432)
    _args["prepare_threshold"] = None
# pool_pre_ping: en la nube las conexiones inactivas se cortan; se revisan antes de usarlas
engine = create_engine(DB_URL, connect_args=_args, pool_pre_ping=ES_REMOTA)


def ejecutar_sql(archivo: str):
    """Ejecuta un archivo de db/ con varias sentencias (los idempotentes:
    umbrales.sql, narrativas.sql, usuarios.sql, rls.sql)."""
    sql = (RAIZ / "db" / archivo).read_text(encoding="utf-8")
    with engine.begin() as conn:
        # conexion nativa de psycopg: permite varias sentencias en un execute
        conn.connection.driver_connection.execute(sql)
