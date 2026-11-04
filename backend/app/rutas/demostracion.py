"""Modo demostracion: el telefono simulado pide aqui el codigo vigente."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app import demo, schemas, seguridad
from app.seguridad import Usuario, sesion_actual

router = APIRouter(prefix="/demo", tags=["Demostración"])


@router.get("", response_model=schemas.Demo)
def ver_demo():
    """Si el modo demostracion esta activo (MODO_DEMO=si con datos sinteticos).
    No requiere sesion, asi que no dice que cuentas existen ni su contrasena:
    la pantalla de inicio se ve como en produccion."""
    return {"activo": demo.activo()}


def _codigo_demo(usuario_id: int) -> dict:
    try:
        return demo.codigo_vigente(usuario_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0]))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@router.post("/codigo", response_model=schemas.CodigoDemo)
def codigo_demo_al_entrar(solicitud: schemas.CodigoDemoSolicitud):
    """Codigo vigente de una cuenta de demostracion durante el segundo paso del
    inicio de sesion. Solo en modo demo y solo para las cuentas de demostracion."""
    u = seguridad.usuario_del_token(solicitud.mfa_token, "mfa")
    if u is None:
        raise HTTPException(status_code=401, detail="La verificación venció; vuelve a escribir tu usuario y contraseña")
    return _codigo_demo(u.id)


@router.get("/codigo-configuracion", response_model=schemas.CodigoDemo)
def codigo_demo_al_configurar(u: Usuario = Depends(sesion_actual)):
    """Codigo vigente del QR recien generado, para activar el MFA sin telefono.
    Solo en modo demo y solo para las cuentas de demostracion."""
    return _codigo_demo(u.id)
