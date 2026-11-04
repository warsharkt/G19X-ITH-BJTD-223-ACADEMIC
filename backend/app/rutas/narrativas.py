"""Narrativas con IA: solicitud, consulta, firma (RF-05) y exportacion (RF-08)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError

from app import exportar, narrativa, schemas, trabajos
from app.llm import ConfiguracionIA, obtener_proveedor
from app.rutas.comun import PATRON_MES, kpis_df, mes
from app.seguridad import (
    Usuario,
    area_por_defecto,
    areas_visibles,
    con_acceso_a_datos,
    exigir_acceso_a_datos,
    solo_analista,
)

router = APIRouter(prefix="/narrativas", tags=["Narrativa"])


def _para(u: Usuario, trabajo: dict) -> dict:
    """Direccion y los gerentes reciben el reporte cuando RRHH ya lo firmo
    (regla 10.3.9). Antes pueden ver en que va y quien lo firmara, pero no el
    texto de la IA, el motivo de un rechazo ni los errores de la generacion."""
    if u.rol == "rrhh" or (trabajo["estado"] == "lista" and trabajo["revision"] == "aprobada"):
        return trabajo
    return {**trabajo, "narrativa": None, "error": None, "detalle_error": None, "comentario_revision": None}


def proveedor_configurado():
    """Proveedor del .env; 503 con el motivo si la configuracion no es valida o segura."""
    try:
        return obtener_proveedor()
    except ConfiguracionIA as exc:
        raise HTTPException(status_code=503, detail=f"IA no disponible: {exc}")


@router.post("", status_code=202, response_model=schemas.TrabajoNarrativa)
def crear_narrativa(
    solicitud: schemas.NarrativaSolicitud,
    u: Usuario = Depends(solo_analista),
    proveedor=Depends(proveedor_configurado),
):
    """Solicita la narrativa ejecutiva (resumen, hallazgos y recomendaciones).

    Solo la Analista de RRHH la solicita: la Responsable la firma, y
    Direccion y los gerentes la piden a RRHH con POST /pedidos. La respuesta
    dice quien la va a firmar (`firma`).

    Responde de inmediato con un id y estado `en_proceso`; el modelo la redacta
    en segundo plano (en CPU tarda minutos). Consulta el resultado con
    `GET /narrativas/{id}`. La redacta SIEMPRE el modelo de lenguaje, solo a
    partir de los KPIs ya calculados, y su respuesta se valida (cifras,
    trazabilidad, sin causalidad); si no lo logra, termina en `error` con el
    motivo. Siempre requiere revision humana antes de distribuirse.
    """
    area_id = area_por_defecto(u) if solicitud.area_id is None else solicitud.area_id
    exigir_acceso_a_datos(u, area_id)
    df = kpis_df()
    try:
        periodo, _ = narrativa.validar_solicitud(
            df, mes(solicitud.periodo) if solicitud.periodo else None, area_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    try:
        id_ = trabajos.encolar(periodo, area_id, proveedor, df, solicitante=u.usuario)
        return trabajos.obtener(id_)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@router.get("/{id_narrativa}", response_model=schemas.TrabajoNarrativa)
def ver_narrativa(id_narrativa: int, u: Usuario = Depends(con_acceso_a_datos)):
    """Estado de una solicitud y, cuando esta `lista`, la narrativa completa."""
    try:
        trabajo = trabajos.obtener(id_narrativa)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    if trabajo is None:
        raise HTTPException(status_code=404, detail=f"La narrativa {id_narrativa} no existe")
    exigir_acceso_a_datos(u, trabajo["area_id"])
    return _para(u, trabajo)


@router.post("/{id_narrativa}/revision", response_model=schemas.TrabajoNarrativa)
def revisar_narrativa(
    id_narrativa: int, solicitud: schemas.RevisionSolicitud, u: Usuario = Depends(con_acceso_a_datos)
):
    """Aprueba o rechaza una narrativa terminada (RF-05) y registra quien lo hizo (RF-11).

    Firma la Responsable de RRHH o su suplente vigente, y nunca quien la
    solicito: siempre la revisa alguien distinto. Al aprobar puede agregar una
    Nota de RRHH, que va firmada y aparte del texto de la IA. La decision es
    definitiva; si se rechaza, se explica el motivo y se solicita una nueva.
    """
    if u.rol != "rrhh":
        raise HTTPException(
            status_code=403, detail="Los reportes los firma la Responsable de Recursos Humanos o su suplente"
        )
    try:
        trabajo = trabajos.revisar(
            id_narrativa, solicitud.decision, u.usuario, solicitud.comentario, solicitud.nota
        )
    except trabajos.RevisionNoPermitida as exc:
        raise HTTPException(status_code=409 if exc.conflicto else 403, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    if trabajo is None:
        raise HTTPException(status_code=404, detail=f"La narrativa {id_narrativa} no existe")
    return trabajo


@router.get(
    "/{id_narrativa}/exportar",
    response_class=Response,
    responses={200: {"content": {tipo: {} for tipo in exportar.FORMATOS.values()},
                     "description": "Archivo del reporte"}},
)
def exportar_narrativa(
    id_narrativa: int,
    formato: Literal["pdf", "pptx"] = Query("pdf", description="pdf (reporte) o pptx (presentacion ejecutiva)"),
    u: Usuario = Depends(con_acceso_a_datos),
):
    """Descarga el reporte en PDF o como presentacion ejecutiva (RF-08).

    Solo los reportes **aprobados** por RRHH se pueden exportar (regla 10.3.9),
    y cada quien solo los de las areas que puede ver. El archivo se arma con
    la narrativa aprobada tal como quedo guardada (no se recalcula nada) y
    cada descarga queda en la bitacora: quien, en que formato y cuando.
    """
    try:
        trabajo = trabajos.obtener(id_narrativa)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    if trabajo is None:
        raise HTTPException(status_code=404, detail=f"La narrativa {id_narrativa} no existe")
    exigir_acceso_a_datos(u, trabajo["area_id"])
    if trabajo["estado"] != "lista" or trabajo["revision"] != "aprobada":
        estado = trabajo["revision"] if trabajo["estado"] == "lista" else trabajo["estado"]
        raise HTTPException(
            status_code=409,
            detail=f"Solo se pueden exportar reportes aprobados por RRHH; este está {estado.replace('_', ' ')}",
        )
    contenido = exportar.generar(trabajo, formato)
    try:
        trabajos.registrar_exportacion(id_narrativa, formato, u.usuario)
    except SQLAlchemyError:  # sin bitacora no se distribuye
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    return Response(
        contenido,
        media_type=exportar.FORMATOS[formato],
        headers={"Content-Disposition": f'attachment; filename="{exportar.nombre_archivo(trabajo, formato)}"'},
    )


@router.get("", response_model=list[schemas.TrabajoNarrativa])
def historial_narrativas(
    area_id: int | None = Query(None, description="0 = consolidado corporativo"),
    periodo: str | None = Query(None, pattern=PATRON_MES, description="AAAA-MM"),
    revision: str | None = Query(
        None, pattern="^(pendiente|aprobada|rechazada)$", description="Solo narrativas listas con esa revision"
    ),
    limite: int = Query(20, ge=1, le=100),
    u: Usuario = Depends(con_acceso_a_datos),
):
    """Historial de solicitudes de las areas que puedes ver, de la mas reciente a la mas antigua."""
    if area_id is not None:
        exigir_acceso_a_datos(u, area_id)
        area_ids = [area_id]
    else:
        area_ids = None if u.rol == "rrhh" else areas_visibles(u, [])
    try:
        return [_para(u, t) for t in trabajos.listar(area_ids, mes(periodo) if periodo else None, limite, revision)]
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
