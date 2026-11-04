"""Administracion de cuentas (RF-11, RF-12): solo TI las cambia; TI y RRHH las ven."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app import mfa, schemas, seguridad
from app.seguridad import ErrorDeUsuario, Usuario, solo_ti, ti_o_rrhh

router = APIRouter(prefix="/usuarios", tags=["Cuentas"])


def _cuentas(funcion, *args):
    """Traduce los errores de las operaciones de cuentas a HTTP."""
    try:
        return funcion(*args)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0]))
    except ErrorDeUsuario as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@router.get("", response_model=list[schemas.Cuenta])
def ver_cuentas(_u: Usuario = Depends(ti_o_rrhh)):
    """Cuentas del sistema (sin contrasenas ni secretos)."""
    return _cuentas(seguridad.listar_cuentas)


@router.get("/cambios", response_model=list[schemas.CambioCuenta])
def bitacora_de_cuentas(
    usuario: str | None = Query(None, description="Solo los cambios de esa cuenta"),
    limite: int = Query(50, ge=1, le=200),
    _u: Usuario = Depends(ti_o_rrhh),
):
    """Quien creo o modifico cada cuenta, cuando y que cambio (RF-11)."""
    return _cuentas(seguridad.cambios, limite, usuario)


@router.post("", status_code=201, response_model=schemas.CuentaCreada)
def crear_cuenta(nueva: schemas.CuentaNueva, u: Usuario = Depends(solo_ti)):
    """Crea una cuenta con una contrasena temporal que se muestra UNA vez: la
    persona la cambia al entrar, asi TI nunca conoce la definitiva."""
    temporal = seguridad.generar_contrasena_temporal()
    id_ = _cuentas(
        lambda: seguridad.crear_usuario(
            nueva.usuario, nueva.nombre, nueva.rol, temporal, nueva.area_id, nueva.correo, por=u.usuario, temporal=True,
            firma_reportes=nueva.firma_reportes,
        )
    )
    return {"cuenta": seguridad.obtener_cuenta(id_), "contrasena_temporal": temporal}


@router.patch("/{usuario_id}", response_model=schemas.Cuenta)
def modificar_cuenta(usuario_id: int, cambio: schemas.CuentaCambio, u: Usuario = Depends(solo_ti)):
    """Cambia nombre, rol, area, correo o desactiva/reactiva una cuenta. Nadie
    cambia su propio rol ni se desactiva. Las cuentas no se borran."""
    pedidos = cambio.model_dump(exclude_unset=True)
    pedidos = {c: v for c, v in pedidos.items() if v is not None or c in ("area_id", "correo")}
    return _cuentas(seguridad.modificar_usuario, usuario_id, pedidos, u.usuario)


@router.post("/{usuario_id}/contrasena", response_model=schemas.ContrasenaTemporal)
def restablecer_contrasena(usuario_id: int, u: Usuario = Depends(solo_ti)):
    """Pone una contrasena temporal (se muestra UNA vez), desbloquea la cuenta
    y cierra sus sesiones. La persona elige la suya al entrar."""
    return {"contrasena_temporal": _cuentas(seguridad.restablecer_contrasena, usuario_id, u.usuario)}


@router.post("/{usuario_id}/mfa/reiniciar", response_model=schemas.Cuenta)
def reiniciar_mfa(usuario_id: int, u: Usuario = Depends(solo_ti)):
    """Borra la verificacion en dos pasos (telefono perdido) y cierra sus
    sesiones: al entrar, la persona la vuelve a configurar."""
    _cuentas(mfa.reiniciar, usuario_id, u.usuario)
    return seguridad.obtener_cuenta(usuario_id)
