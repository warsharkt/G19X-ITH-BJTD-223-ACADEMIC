"""Catalogos: areas, meses con datos y umbrales del semaforo."""
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import cargas, schemas, umbrales
from app.database import engine
from app.kpis import CORPORATIVO
from app.rutas.comun import PATRON_MES, kpis_df, mes
from app.seguridad import Usuario, areas_visibles, usuario_actual

router = APIRouter(tags=["Catalogos"])


@router.get("/areas", response_model=list[schemas.Area])
def areas(u: Usuario = Depends(usuario_actual)):
    """Areas que el usuario puede consultar. El id 0 es el consolidado corporativo."""
    try:
        with engine.connect() as conn:
            filas = conn.execute(text("SELECT id, nombre FROM areas ORDER BY id")).all()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    todas = [{"id": CORPORATIVO, "nombre": "Corporativo"}] + [{"id": i, "nombre": n} for i, n in filas]
    permitidas = set(areas_visibles(u, [a["id"] for a in todas]))
    return [a for a in todas if a["id"] in permitidas]


@router.get("/periodos", response_model=list[str])
def periodos(_u: Usuario = Depends(usuario_actual)):
    """Meses con datos, en formato AAAA-MM, del mas antiguo al mas reciente."""
    return sorted(p.strftime("%Y-%m") for p in kpis_df()["periodo"].unique())


@router.get("/periodos/{periodo}/faltantes", response_model=schemas.FuentesDelMes)
def fuentes_faltantes(periodo: str = Path(pattern=PATRON_MES), _u: Usuario = Depends(usuario_actual)):
    """Que le falta a un mes (AAAA-MM) antes de generar su reporte.

    `fuentes`: fuentes mensuales sin datos de ese mes (el reporte saldria sin
    sus indicadores). `sin_actualizar`: plantilla y vacantes que nadie ha
    subido desde que cerro el mes (si hubo altas, bajas o contrataciones, el
    reporte no las incluiria)."""
    dia = mes(periodo).date()
    try:
        return {"fuentes": cargas.fuentes_faltantes(dia), "sin_actualizar": cargas.fuentes_sin_actualizar(dia)}
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@router.get("/umbrales", response_model=list[schemas.Umbral])
def ver_umbrales(_u: Usuario = Depends(usuario_actual)):
    """Umbrales de atencion y criticos que definen el semaforo de cada indicador."""
    try:
        return umbrales.listar()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
