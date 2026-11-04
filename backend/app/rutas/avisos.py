"""Bandeja de avisos de cada persona (RF-09)."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError

from app import avisos, schemas
from app.seguridad import Usuario, usuario_actual

router = APIRouter(prefix="/avisos", tags=["Avisos"])


@router.get("", response_model=schemas.Avisos)
def ver_avisos(
    solo_no_leidos: bool = False,
    limite: int = Query(50, ge=1, le=200),
    u: Usuario = Depends(usuario_actual),
):
    """Tus avisos (alertas en rojo, reportes por revisar, aprobados o
    rechazados), del mas reciente al mas antiguo, y cuantos no has leido.
    Solo los de las areas que puedes ver hoy."""
    try:
        return avisos.listar(u, solo_no_leidos, limite)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@router.post("/{id_aviso}/leido", status_code=204)
def marcar_aviso_leido(id_aviso: int, u: Usuario = Depends(usuario_actual)):
    try:
        existe = avisos.marcar_leido(u, id_aviso)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    if not existe:
        raise HTTPException(status_code=404, detail=f"El aviso {id_aviso} no existe")
    return Response(status_code=204)


@router.post("/leidos")
def marcar_todos_los_avisos(u: Usuario = Depends(usuario_actual)) -> dict[str, int]:
    """Marca como leidos todos tus avisos."""
    try:
        return {"marcados": avisos.marcar_todos(u)}
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
