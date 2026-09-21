"""API del Motor Inteligente de Reportes de RRHH (paso 4).

Solo lectura por ahora. La autenticacion y el control de acceso por rol
(RBAC) llegan en el paso 6: hasta entonces la API solo debe usarse en local.
"""
import time

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import schemas
from app.database import engine
from app.kpis import CORPORATIVO, calcular_kpis

app = FastAPI(
    title="Motor Inteligente de Reportes de RRHH",
    description=(
        "Indicadores de Recursos Humanos calculados por el motor analitico "
        "(sin IA): rotacion, clima, desempeno, capacitacion, reclutamiento y "
        "productividad, con tendencias y semaforo."
    ),
    version="0.4.0",
)

# El frontend de React (paso 7) se sirve en local desde estos origenes.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

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


def a_registros(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> lista de dicts JSON-compatible (NaN pasa a null)."""
    df = df.assign(periodo=df["periodo"].dt.date).astype(object)
    return df.where(df.notna(), None).to_dict("records")


def _mes(texto: str) -> pd.Timestamp:
    return pd.Timestamp(texto + "-01")


@app.get("/health", tags=["Sistema"])
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {type(exc).__name__}"
    return {"status": "ok", "database": db_status}


@app.get("/areas", response_model=list[schemas.Area], tags=["Catalogos"])
def areas():
    """Areas de la empresa. El id 0 es el consolidado corporativo."""
    try:
        with engine.connect() as conn:
            filas = conn.execute(text("SELECT id, nombre FROM areas ORDER BY id")).all()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    return [{"id": CORPORATIVO, "nombre": "Corporativo"}] + [
        {"id": i, "nombre": n} for i, n in filas
    ]


@app.get("/periodos", response_model=list[str], tags=["Catalogos"])
def periodos():
    """Meses con datos, en formato AAAA-MM, del mas antiguo al mas reciente."""
    return sorted(p.strftime("%Y-%m") for p in kpis_df()["periodo"].unique())


@app.get("/umbrales", response_model=list[schemas.Umbral], tags=["Catalogos"])
def umbrales():
    """Umbrales de atencion y criticos que definen el semaforo de cada indicador."""
    kpis_df()  # asegura que la tabla exista
    with engine.connect() as conn:
        filas = conn.execute(
            text(
                "SELECT indicador, nombre, unidad, sentido, "
                "umbral_atencion::float8 AS umbral_atencion, "
                "umbral_critico::float8 AS umbral_critico "
                "FROM umbrales ORDER BY indicador"
            )
        ).mappings().all()
    return [dict(f) for f in filas]


@app.get("/kpis", response_model=list[schemas.KpiFila], tags=["KPIs"])
def kpis(
    periodo: str | None = Query(
        None, pattern=PATRON_MES, description="AAAA-MM. Por defecto, el ultimo mes con datos."
    ),
    area_id: int = Query(CORPORATIVO, description="0 = consolidado corporativo"),
    indicador: str | None = Query(None, description="Filtra por un indicador"),
):
    """KPIs de un mes y un area, con tendencias y semaforo."""
    df = kpis_df()
    mes = _mes(periodo) if periodo else df["periodo"].max()
    if not (df["periodo"] == mes).any():
        raise HTTPException(status_code=404, detail=f"No hay datos para el periodo {periodo}")
    if area_id not in set(df["area_id"]):
        raise HTTPException(status_code=404, detail=f"El area {area_id} no existe")
    if indicador is not None and indicador not in set(df["indicador"]):
        raise HTTPException(status_code=404, detail=f"El indicador '{indicador}' no existe")

    filtro = (df["periodo"] == mes) & (df["area_id"] == area_id)
    if indicador is not None:
        filtro &= df["indicador"] == indicador
    return a_registros(df[filtro])


@app.get("/kpis/serie/{indicador}", response_model=list[schemas.PuntoSerie], tags=["KPIs"])
def serie(
    indicador: str,
    area_id: int = Query(CORPORATIVO, description="0 = consolidado corporativo"),
    desde: str | None = Query(None, pattern=PATRON_MES, description="AAAA-MM"),
    hasta: str | None = Query(None, pattern=PATRON_MES, description="AAAA-MM"),
):
    """Serie de tiempo de un indicador (para las graficas del dashboard)."""
    df = kpis_df()
    if indicador not in set(df["indicador"]):
        raise HTTPException(status_code=404, detail=f"El indicador '{indicador}' no existe")
    if area_id not in set(df["area_id"]):
        raise HTTPException(status_code=404, detail=f"El area {area_id} no existe")

    f = df[(df["indicador"] == indicador) & (df["area_id"] == area_id)]
    if desde:
        f = f[f["periodo"] >= _mes(desde)]
    if hasta:
        f = f[f["periodo"] <= _mes(hasta)]
    f = f.sort_values("periodo")[["periodo", "valor", "n", "suprimido", "estado"]]
    return a_registros(f)