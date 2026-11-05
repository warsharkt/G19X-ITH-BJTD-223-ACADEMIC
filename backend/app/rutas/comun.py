"""Lo que comparten varios routers: los KPIs en memoria y el formato de mes."""
import math
import threading
import time

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine
from app.kpis import CORPORATIVO, calcular_kpis
from app.schemas import PATRON_MES  # noqa: F401 (los routers lo importan de aqui)

SEGUNDOS_CACHE = 60

# Calcular los KPIs toma casi un segundo: se guardan en memoria unos segundos
# para no recalcular en cada peticion del dashboard.
_cache = {"df": None, "momento": 0.0}
# Al vencer la cache calcula uno solo: si cada peticion calculara por su cuenta,
# 25 a la vez tardaban 3 s en lugar de 0.2. Los demas siguen con los datos de
# hace un minuto en vez de esperar: si la base se atora, no se ocupan todos los
# hilos de la API. Solo esperan si no hay nada que mostrar (o cambiaron los datos).
_calculando = threading.Lock()
SEGUNDOS_ESPERA = 10


def _vigente() -> pd.DataFrame | None:
    df = _cache["df"]
    return df if df is not None and time.monotonic() - _cache["momento"] <= SEGUNDOS_CACHE else None


def kpis_df() -> pd.DataFrame:
    df = _vigente()
    if df is not None:
        return df
    anterior = _cache["df"]
    if anterior is not None and not _calculando.acquire(blocking=False):
        return anterior
    if anterior is None and not _calculando.acquire(timeout=SEGUNDOS_ESPERA):
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    try:
        df = _vigente()
        if df is None:
            df = calcular_kpis()
            _cache["df"], _cache["momento"] = df, time.monotonic()
        return df
    except (SQLAlchemyError, pd.errors.DatabaseError):  # pandas envuelve los errores de la base
        if anterior is not None:
            return anterior
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    finally:
        _calculando.release()


def olvidar_kpis():
    """Los datos o los umbrales cambiaron: recalcular en la siguiente consulta."""
    _cache["df"] = None


SERIE = ("periodo", "valor", "n", "suprimido", "estado")


def indice_kpis() -> dict:
    """Los KPIs ya convertidos a JSON e indexados, una vez por calculo: por
    (area, mes) para el tablero y por (indicador, area) para las graficas.
    Antes cada peticion filtraba las ~1,500 filas y las convertia de nuevo;
    con una sola API atendiendo, eso limitaba a unas 70 peticiones/s."""
    df = kpis_df()
    indice = _cache.get("indice")
    if indice is None or indice["df"] is not df:
        por_mes, por_serie = {}, {}
        for r in a_registros(df):
            por_mes.setdefault((r["area_id"], r["periodo"]), []).append(r)
            por_serie.setdefault((r["indicador"], r["area_id"]), []).append({c: r[c] for c in SERIE})
        for puntos in por_serie.values():
            puntos.sort(key=lambda p: p["periodo"])
        indice = {
            "df": df, "por_mes": por_mes, "por_serie": por_serie,
            "areas": set(df["area_id"]), "indicadores": set(df["indicador"]),
            "periodos": {p.date() for p in df["periodo"].unique()}, "ultimo_mes": df["periodo"].max().date(),
        }
        _cache["indice"] = indice
    return indice


def a_registros(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> lista de dicts JSON-compatible (NaN pasa a null).

    Fila por fila en Python y no con astype(object) + where, que es mucho
    mas lento en pandas."""
    registros = df.to_dict("records")
    for r in registros:
        for campo, valor in r.items():
            if isinstance(valor, float) and math.isnan(valor):
                r[campo] = None
            elif isinstance(valor, pd.Timestamp):
                r[campo] = valor.date()
    return registros


def mes(texto: str) -> pd.Timestamp:
    return pd.Timestamp(texto + "-01")


def ids_de_areas() -> list[int]:
    try:
        with engine.connect() as conn:
            return [CORPORATIVO] + list(conn.execute(text("SELECT id FROM areas ORDER BY id")).scalars())
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
