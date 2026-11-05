"""Carga de datos desde los sistemas fuente (RF-01). Solo la Analista de RRHH."""
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.exc import DataError, SQLAlchemyError

from app import cargas, programacion, schemas
from app.rutas.comun import olvidar_kpis
from app.seguridad import Usuario, solo_analista

router = APIRouter(prefix="/cargas", tags=["Carga de datos"])

_TIPOS = {"csv": "text/csv; charset=utf-8", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _archivo(contenido: bytes, nombre: str, tipo: str) -> Response:
    return Response(contenido, media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


def _carga(funcion, *args):
    try:
        return funcion(*args)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0]))
    except cargas.ErrorDeCarga as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except DataError:
        raise HTTPException(status_code=422, detail="Un valor del archivo no cabe en la base: revisa las cifras")
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@router.get("/fuentes")
def fuentes_de_datos(_u: Usuario = Depends(solo_analista)) -> dict:
    """Fuentes que se pueden cargar, sus columnas y el mes pendiente por subir."""
    return {"fuentes": cargas.catalogo(), "ejemplos": _carga(cargas.info_ejemplos)}


@router.get("", response_model=list[schemas.Carga])
def historial_de_cargas(limite: int = Query(50, ge=1, le=200), _u: Usuario = Depends(solo_analista)):
    """Bitacora de cargas: quien subio que archivo, cuando, y como termino."""
    return _carga(cargas.listar, limite)


@router.post("/{fuente}", status_code=201, response_model=schemas.Carga)
def subir_archivo(fuente: str, archivo: UploadFile = File(...), u: Usuario = Depends(solo_analista)):
    """Sube y VALIDA un archivo (CSV o Excel) de una fuente. No cambia nada:
    queda 'validada' (lista para aplicar) o 'con_errores'. Solo la Analista de RRHH.

    Es `def` y no `async def` a proposito: validar un archivo tarda segundos y,
    dentro de una funcion async, dejaria a toda la API sin responder mientras."""
    contenido = archivo.file.read(cargas.BYTES_MAXIMOS + 1)
    return _carga(cargas.validar, fuente, archivo.filename or "archivo", contenido, u.usuario)


@router.post("/{id_carga}/aplicar", response_model=schemas.Carga)
def aplicar_carga(id_carga: int, u: Usuario = Depends(solo_analista)):
    """Aplica una carga validada (todo o nada) y concilia archivo contra base.
    Los indicadores se recalculan y se revisan las alertas del mes."""
    resultado = _carga(cargas.aplicar, id_carga, u.usuario)
    olvidar_kpis()
    programacion.revisar_pronto()
    return resultado


@router.post("/{id_carga}/descartar", response_model=schemas.Carga)
def descartar_carga(id_carga: int, u: Usuario = Depends(solo_analista)):
    return _carga(cargas.descartar, id_carga, u.usuario)


@router.get("/plantillas/{fuente}", response_class=Response)
def plantilla_de_carga(
    fuente: str, formato: Literal["csv", "xlsx"] = "xlsx", _u: Usuario = Depends(solo_analista)
):
    """Archivo vacio con las columnas que espera la fuente."""
    return _archivo(_carga(cargas.plantilla, fuente, formato), f"plantilla-{cargas.prefijo_de_archivo(fuente)}.{formato}", _TIPOS[formato])


@router.get("/ejemplos/{fuente}", response_class=Response)
def ejemplo_de_carga(
    fuente: str, formato: Literal["csv", "xlsx"] = "xlsx", _u: Usuario = Depends(solo_analista)
):
    """Archivo del mes pendiente (el siguiente al ultimo cargado), como lo
    exportaria el sistema de la fuente (con columnas de mas)."""
    contenido, nombre = _carga(cargas.ejemplo, fuente, formato)
    return _archivo(contenido, nombre, _TIPOS[formato])
