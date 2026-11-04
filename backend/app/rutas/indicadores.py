"""KPIs de solo lectura, calculados por el motor analitico (sin IA)."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app import schemas
from app.rutas.comun import PATRON_MES, a_registros, kpis_df, mes
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
    df = kpis_df()
    del_mes = mes(periodo) if periodo else df["periodo"].max()
    if not (df["periodo"] == del_mes).any():
        raise HTTPException(status_code=404, detail=f"No hay datos para el periodo {periodo}")
    if area_id not in set(df["area_id"]):
        raise HTTPException(status_code=404, detail=f"El area {area_id} no existe")
    if indicador is not None and indicador not in set(df["indicador"]):
        raise HTTPException(status_code=404, detail=f"El indicador '{indicador}' no existe")

    filtro = (df["periodo"] == del_mes) & (df["area_id"] == area_id)
    if indicador is not None:
        filtro &= df["indicador"] == indicador
    return a_registros(df[filtro])


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
    df = kpis_df()
    if indicador not in set(df["indicador"]):
        raise HTTPException(status_code=404, detail=f"El indicador '{indicador}' no existe")
    if area_id not in set(df["area_id"]):
        raise HTTPException(status_code=404, detail=f"El area {area_id} no existe")

    f = df[(df["indicador"] == indicador) & (df["area_id"] == area_id)]
    if desde:
        f = f[f["periodo"] >= mes(desde)]
    if hasta:
        f = f[f["periodo"] <= mes(hasta)]
    f = f.sort_values("periodo")[["periodo", "valor", "n", "suprimido", "estado"]]
    return a_registros(f)
