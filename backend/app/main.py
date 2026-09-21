from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine

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