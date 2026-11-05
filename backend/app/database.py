"""Conexion central a PostgreSQL. Todo el backend importa el engine de aqui.

Dos formas de configurarla en el .env:
  - DATABASE_URL: cadena completa (Supabase u otro PostgreSQL en la nube).
    Tiene prioridad si existe.
  - POSTGRES_USER/PASSWORD/DB + DB_HOST/DB_PORT: el PostgreSQL local de
    Docker (docker-compose.yml). Es lo que se usa si no hay DATABASE_URL.

En Docker, la API no usa POSTGRES_USER (superusuario): scripts/arranque.py
crea la cuenta DB_API_USUARIO, sin privilegios, y le pasa DB_API_USUARIO y
DB_API_CONTRASENA solo al proceso de la API.
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
        cuenta_api = os.getenv("DB_API_USUARIO") and os.getenv("DB_API_CONTRASENA")
        return URL.create(
            "postgresql+psycopg",
            username=os.getenv("DB_API_USUARIO") if cuenta_api else os.getenv("POSTGRES_USER"),
            password=os.getenv("DB_API_CONTRASENA") if cuenta_api else os.getenv("POSTGRES_PASSWORD"),
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
# Remota = una DATABASE_URL hacia otro equipo (Supabase). El PostgreSQL de
# docker-compose.yml es propio aunque la API lo vea como "db" dentro de Docker.
ES_REMOTA = bool(os.getenv("DATABASE_URL", "").strip()) and DB_URL.host not in ("localhost", "127.0.0.1", None)

# connect_timeout: si PostgreSQL no responde, fallar en segundos (por defecto 5)
# en lugar de quedarse esperando minutos.
_args = {"connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "5"))}
# Una consulta o un candado no esperan sin limite: si no, unas cuantas peticiones
# atoradas ocupan todos los hilos de la API y nadie mas recibe respuesta. En
# Supabase no: su pooler no acepta estas opciones al conectar.
if not ES_REMOTA:
    _args["options"] = (
        f"-c statement_timeout={int(os.getenv('DB_SEGUNDOS_CONSULTA', '30')) * 1000} "
        f"-c lock_timeout={int(os.getenv('DB_SEGUNDOS_CANDADO', '5')) * 1000}"
    )
if DB_URL.port == 6543:
    # "Transaction pooler" de Supabase: no admite sentencias preparadas
    # (se recomienda el "Session pooler", puerto 5432)
    _args["prepare_threshold"] = None
# pool_pre_ping: las conexiones que se cortaron (la nube, un reinicio de la base)
# se revisan antes de usarlas. pool_timeout: sin conexion libre, 503 en segundos.
engine = create_engine(DB_URL, connect_args=_args, pool_pre_ping=True, pool_timeout=10)


def ejecutar_sql(archivo: str):
    """Ejecuta un archivo de db/ con varias sentencias (los idempotentes:
    umbrales.sql, narrativas.sql, usuarios.sql, rls.sql).

    En Docker no hace nada dentro de la API: scripts/arranque.py ya los corrio
    como superusuario, y la cuenta de la API no es duena de las tablas."""
    if os.getenv("DB_ESQUEMA_PREPARADO") == "si":
        return
    sql = (RAIZ / "db" / archivo).read_text(encoding="utf-8")
    with engine.begin() as conn:
        # conexion nativa de psycopg: permite varias sentencias en un execute
        conn.connection.driver_connection.execute(sql)
