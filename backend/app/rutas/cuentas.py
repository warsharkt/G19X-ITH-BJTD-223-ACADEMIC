"""Administracion de cuentas (RF-11, RF-12): solo TI las cambia; TI y RRHH las ven.

TI nunca da el permiso de firmar reportes (lo da una Responsable, en
/firmas/responsables), y todo lo que TI le hace a una cuenta de RRHH le
llega como aviso a RRHH: asi una sola persona de TI no puede crearse, ni
apropiarse de, una cuenta que firma (regla 10.3.9).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app import avisos, mfa, schemas, seguridad
from app.seguridad import ErrorDeUsuario, Usuario, solo_ti, ti_o_rrhh

router = APIRouter(prefix="/usuarios", tags=["Cuentas"])

SIN_FIRMA = "El permiso de firmar reportes lo da una Responsable de RRHH, no Administración de TI"


def _avisar_a_rrhh(cuenta: dict | None, quien: str, que: str, firma_suspendida: bool = False):
    """Aviso a RRHH si la cuenta es (o era) de RRHH."""
    if cuenta is None:
        return
    titulo = f"{quien} (TI) {que} la cuenta de RRHH de {cuenta['nombre']} ({cuenta['usuario']})"
    if firma_suspendida:
        titulo += ". Ya no puede firmar reportes hasta que otra Responsable le devuelva el permiso"
    avisos.avisar_cuenta(titulo)


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
    if nueva.firma_reportes:
        raise HTTPException(status_code=403, detail=SIN_FIRMA)
    temporal = seguridad.generar_contrasena_temporal()
    id_ = _cuentas(
        lambda: seguridad.crear_usuario(
            nueva.usuario, nueva.nombre, nueva.rol, temporal, nueva.area_id, nueva.correo, por=u.usuario, temporal=True,
        )
    )
    cuenta = seguridad.obtener_cuenta(id_)
    if cuenta["rol"] == "rrhh":
        _avisar_a_rrhh(cuenta, u.usuario, "creó")
    return {"cuenta": cuenta, "contrasena_temporal": temporal}


@router.patch("/{usuario_id}", response_model=schemas.Cuenta)
def modificar_cuenta(usuario_id: int, cambio: schemas.CuentaCambio, u: Usuario = Depends(solo_ti)):
    """Cambia nombre, rol, area, correo o desactiva/reactiva una cuenta. Nadie
    cambia su propio rol ni se desactiva. Las cuentas no se borran."""
    pedidos = cambio.model_dump(exclude_unset=True)
    pedidos = {c: v for c, v in pedidos.items() if v is not None or c in ("area_id", "correo")}
    if "firma_reportes" in pedidos:
        raise HTTPException(status_code=403, detail=SIN_FIRMA)
    antes = seguridad.obtener_cuenta(usuario_id)
    despues = _cuentas(seguridad.modificar_usuario, usuario_id, pedidos, u.usuario)
    if antes != despues and "rrhh" in (antes["rol"], despues["rol"]):
        _avisar_a_rrhh(despues, u.usuario, "modificó")
    return despues


@router.post("/{usuario_id}/contrasena", response_model=schemas.ContrasenaTemporal)
def restablecer_contrasena(usuario_id: int, u: Usuario = Depends(solo_ti)):
    """Pone una contrasena temporal (se muestra UNA vez), desbloquea la cuenta
    y cierra sus sesiones. La persona elige la suya al entrar. Si firmaba
    reportes, pierde el permiso hasta que otra Responsable se lo devuelva."""
    temporal, suspendida = _cuentas(seguridad.restablecer_contrasena, usuario_id, u.usuario)
    cuenta = seguridad.obtener_cuenta(usuario_id)
    if cuenta["rol"] == "rrhh":
        _avisar_a_rrhh(cuenta, u.usuario, "restableció la contraseña de", suspendida)
    return {"contrasena_temporal": temporal}


@router.post("/{usuario_id}/mfa/reiniciar", response_model=schemas.Cuenta)
def reiniciar_mfa(usuario_id: int, u: Usuario = Depends(solo_ti)):
    """Borra la verificacion en dos pasos (telefono perdido) y cierra sus
    sesiones: al entrar, la persona la vuelve a configurar. Si firmaba
    reportes, pierde el permiso hasta que otra Responsable se lo devuelva."""
    suspendida = _cuentas(mfa.reiniciar, usuario_id, u.usuario, True)
    cuenta = seguridad.obtener_cuenta(usuario_id)
    if cuenta["rol"] == "rrhh":
        _avisar_a_rrhh(cuenta, u.usuario, "reinició la verificación en dos pasos de", suspendida)
    return cuenta
