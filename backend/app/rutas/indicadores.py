"""KPIs de solo lectura, calculados por el motor analitico (sin IA)."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app import schemas
from app.rutas.comun import PATRON_MES, indice_kpis, mes
from app.seguridad import Usuario, area_por_defecto, con_acceso_a_datos, exigir_acceso_a_datos

router = APIRouter(prefix="/kpis", tags=["KPIs"])


@router.get("", response_model=list[schemas.KpiFila])
def kpis(
    periodo: str | None = Query(
        None, pattern=PATRON_MES, description="AAAA-MM. Por defecto, el ultimo mes con datos."
    ),
    area_id: int | None = Query(
        None, description="0 = consolidado corporativo. Por defecto: tu area si eres gerente, si no el 0."
    ),
    indicador: str | None = Query(None, description="Filtra por un indicador"),
    u: Usuario = Depends(con_acceso_a_datos),
):
    """KPIs de un mes y un area, con tendencias y semaforo."""
    area_id = area_por_defecto(u) if area_id is None else area_id
    exigir_acceso_a_datos(u, area_id)
    indice = indice_kpis()
    del_mes = mes(periodo).date() if periodo else indice["ultimo_mes"]
    if del_mes not in indice["periodos"]:
        raise HTTPException(
            status_code=404, detail=f"No hay datos para el periodo {periodo}" if periodo else "Todavía no hay datos cargados"
        )
    if area_id not in indice["areas"]:
        raise HTTPException(status_code=404, detail=f"El area {area_id} no existe")
    if indicador is not None and indicador not in indice["indicadores"]:
        raise HTTPException(status_code=404, detail=f"El indicador '{indicador}' no existe")

    filas = indice["por_mes"].get((area_id, del_mes), [])
    return [f for f in filas if f["indicador"] == indicador] if indicador is not None else filas


@router.get("/serie/{indicador}", response_model=list[schemas.PuntoSerie])
def serie(
    indicador: str,
    area_id: int | None = Query(
        None, description="0 = consolidado corporativo. Por defecto: tu area si eres gerente, si no el 0."
    ),
    desde: str | None = Query(None, pattern=PATRON_MES, description="AAAA-MM"),
    hasta: str | None = Query(None, pattern=PATRON_MES, description="AAAA-MM"),
    u: Usuario = Depends(con_acceso_a_datos),
):
    """Serie de tiempo de un indicador (para las graficas del dashboard)."""
    area_id = area_por_defecto(u) if area_id is None else area_id
    exigir_acceso_a_datos(u, area_id)
    indice = indice_kpis()
    if indicador not in indice["indicadores"]:
        raise HTTPException(status_code=404, detail=f"El indicador '{indicador}' no existe")
    if area_id not in indice["areas"]:
        raise HTTPException(status_code=404, detail=f"El area {area_id} no existe")

    puntos = indice["por_serie"].get((indicador, area_id), [])
    inicio = mes(desde).date() if desde else None
    fin = mes(hasta).date() if hasta else None
    return [p for p in puntos if (inicio is None or p["periodo"] >= inicio) and (fin is None or p["periodo"] <= fin)]
