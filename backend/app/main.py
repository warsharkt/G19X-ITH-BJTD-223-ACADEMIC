import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

# Carga el .env de la raiz del proyecto
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DB_URL = URL.create(
    "postgresql+psycopg",
    username=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host="localhost",
    port=5433,
    database=os.getenv("POSTGRES_DB"),
)
engine = create_engine(DB_URL)

app = FastAPI(title="Motor Inteligente de Reportes de RRHH")


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {type(exc).__name__}"
    return {"status": "ok", "database": db_status}
