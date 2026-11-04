"""Firma de reportes (10.3.9): quien firma, suplencias y pedidos a RRHH."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app import firmas, narrativa, schemas, trabajos
from app.rutas.comun import kpis_df, mes
from app.seguridad import (
    ErrorDeUsuario,
    Usuario,
    area_por_defecto,
    con_acceso_a_datos,
    exigir_acceso_a_datos,
    usuario_actual,
)

router = APIRouter(tags=["Firma de reportes"])


def _firmas(funcion, *args):
    try:
        return funcion(*args)
    except ErrorDeUsuario as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@router.get("/firmas", response_model=schemas.EstadoFirmas)
def ver_firmas(u: Usuario = Depends(usuario_actual)):
    """Quien firma hoy los reportes: la Responsable de RRHH y, si la hay, su suplente."""
    return _firmas(firmas.estado, u)


@router.post("/firmas/suplencia", response_model=schemas.EstadoFirmas)
def designar_suplente(nueva: schemas.SuplenciaNueva, u: Usuario = Depends(usuario_actual)):
    """La Responsable designa a una Analista que firma en su lugar desde hoy
    hasta la fecha indicada (vacaciones, incapacidad). Queda en la bitacora."""
    if not u.es_responsable:
        raise HTTPException(status_code=403, detail="Solo la Responsable de RRHH designa a su suplente")
    return _firmas(firmas.designar_suplente, u, nueva.suplente, nueva.hasta, nueva.motivo)


@router.post("/firmas/suplencia/terminar", response_model=schemas.EstadoFirmas)
def terminar_suplencia(u: Usuario = Depends(usuario_actual)):
    """La Responsable regresa antes: la suplencia termina hoy."""
    if not u.es_responsable:
        raise HTTPException(status_code=403, detail="Solo la Responsable de RRHH termina la suplencia")
    return _firmas(firmas.terminar_suplencia, u)


@router.post("/pedidos", status_code=201, response_model=schemas.PedidoCreado)
def pedir_reporte(pedido: schemas.PedidoReporte, u: Usuario = Depends(con_acceso_a_datos)):
    """Direccion o un gerente pide un reporte a RRHH (fuera de la programacion
    mensual). No genera nada: avisa a las Analistas de RRHH, que lo preparan."""
    if u.rol not in ("direccion", "gerente"):
        raise HTTPException(status_code=403, detail="RRHH genera los reportes directamente desde Reportes con IA")
    area_id = area_por_defecto(u) if pedido.area_id is None else pedido.area_id
    exigir_acceso_a_datos(u, area_id)
    try:
        periodo, _ = narrativa.validar_solicitud(kpis_df(), mes(pedido.periodo), area_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    id_, avisadas = _firmas(trabajos.registrar_pedido, area_id, periodo, pedido.comentario, u.usuario)
    return {"id": id_, "analistas_avisadas": avisadas}
