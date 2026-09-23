"""Conexion central a PostgreSQL. Todo el backend importa el engine de aqui."""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

# .env en la raiz del proyecto (backend/app/database.py -> subir 2 niveles)
RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(RAIZ / ".env")

DB_URL = URL.create(
    "postgresql+psycopg",
    username=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5433")),
    database=os.getenv("POSTGRES_DB"),
)

# connect_timeout: si PostgreSQL no responde, fallar en segundos (por defecto 5)
# en lugar de quedarse esperando minutos.
engine = create_engine(
    DB_URL, connect_args={"connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "5"))}
)