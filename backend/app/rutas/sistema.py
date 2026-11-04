"""Estado de la API y datos de la marca. No requieren sesion."""
from fastapi import APIRouter
from sqlalchemy import text

from app import marca
from app.database import engine

router = APIRouter(tags=["Sistema"])


@router.get("/marca")
def ver_marca() -> dict[str, str]:
    """Nombre del producto y de la empresa (para la pantalla de inicio). No requiere sesion."""
    return {"producto": marca.PRODUCTO, "empresa": marca.empresa()}


@router.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {type(exc).__name__}"
    return {"status": "ok", "database": db_status}
