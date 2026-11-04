"""Lo que comparten varios routers: los KPIs en memoria y el formato de mes."""
import time

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine
from app.kpis import CORPORATIVO, calcular_kpis

PATRON_MES = r"^\d{4}-(0[1-9]|1[0-2])$"
SEGUNDOS_CACHE = 60

# Calcular los KPIs toma casi un segundo: se guardan en memoria unos segundos
# para no recalcular en cada peticion del dashboard.
_cache = {"df": None, "momento": 0.0}


def kpis_df() -> pd.DataFrame:
    ahora = time.monotonic()
    if _cache["df"] is None or ahora - _cache["momento"] > SEGUNDOS_CACHE:
        try:
            _cache["df"] = calcular_kpis()
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")
        _cache["momento"] = ahora
    return _cache["df"]


def olvidar_kpis():
    """Los datos o los umbrales cambiaron: recalcular en la siguiente consulta."""
    _cache["df"] = None


def a_registros(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> lista de dicts JSON-compatible (NaN pasa a null)."""
    df = df.assign(periodo=df["periodo"].dt.date).astype(object)
    return df.where(df.notna(), None).to_dict("records")


def mes(texto: str) -> pd.Timestamp:
    return pd.Timestamp(texto + "-01")


def ids_de_areas() -> list[int]:
    try:
        with engine.connect() as conn:
            return [CORPORATIVO] + list(conn.execute(text("SELECT id FROM areas ORDER BY id")).scalars())
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
