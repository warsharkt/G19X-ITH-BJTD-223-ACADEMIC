"""Panel de configuracion (RF-12): umbrales del semaforo y programacion mensual."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app import avisos, programacion, schemas, umbrales
from app.rutas.comun import olvidar_kpis
from app.seguridad import Usuario, solo_responsable, solo_rrhh, usuario_actual

router = APIRouter(tags=["Configuración"])


@router.put("/umbrales/{indicador}", response_model=schemas.Umbral)
def cambiar_umbral(indicador: str, cambio: schemas.UmbralCambio, u: Usuario = Depends(solo_responsable)):
    """Cambia los umbrales de un indicador (solo la Responsable de RRHH). Queda en la bitacora.

    El semaforo se recalcula de inmediato. Las alertas que resulten se avisan
    en la siguiente revision de la programacion (cada hora)."""
    try:
        nuevo = umbrales.actualizar(indicador, cambio.umbral_atencion, cambio.umbral_critico, u.usuario)
    except umbrales.UmbralInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    if nuevo is None:
        raise HTTPException(status_code=404, detail=f"El indicador '{indicador}' no existe")
    olvidar_kpis()  # el semaforo cambio
    return nuevo


@router.get("/umbrales/cambios", response_model=list[schemas.CambioUmbral])
def cambios_de_umbrales(limite: int = Query(20, ge=1, le=100), _u: Usuario = Depends(usuario_actual)):
    """Bitacora de cambios de umbrales: quien, cuando, y valores de antes y despues."""
    try:
        return umbrales.cambios(limite)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@router.get("/programacion", response_model=schemas.Programacion)
def ver_programacion(_u: Usuario = Depends(usuario_actual)):
    """Programacion mensual de reportes (RF-07) y los meses que ya genero."""
    try:
        return {
            **programacion.leer(),
            "correo_activo": avisos.configuracion_smtp() is not None,
            "corridas": programacion.corridas(),
        }
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@router.put("/programacion", response_model=schemas.Programacion)
def cambiar_programacion(cambio: schemas.ProgramacionCambio, u: Usuario = Depends(solo_rrhh)):
    """Activa o desactiva la programacion y elige el dia del mes (solo RRHH).

    Cada mes, a partir de ese dia, se generan los reportes del ultimo mes
    cerrado con datos: el consolidado y cada area. Al guardar, la API revisa
    de inmediato si ya toca."""
    try:
        programacion.guardar(cambio.activa, cambio.dia_del_mes, u.usuario)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    programacion.revisar_pronto()
    return ver_programacion(u)
