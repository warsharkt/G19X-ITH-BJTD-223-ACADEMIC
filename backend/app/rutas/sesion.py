"""Inicio de sesion, verificacion en dos pasos y cambio de contrasena."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import SQLAlchemyError

from app import mfa, schemas, seguridad
from app.rutas.comun import ids_de_areas
from app.seguridad import ErrorDeUsuario, Usuario, areas_visibles, sesion_actual

router = APIRouter(prefix="/auth", tags=["Sesión"])


def _origen(request: Request) -> str:
    """IP de quien intenta entrar. Detras de nginx, uvicorn la toma de
    X-Forwarded-For (scripts/arranque.py usa --proxy-headers)."""
    return request.client.host if request.client else "desconocido"


def _token_de_sesion(u: Usuario) -> dict:
    return {
        "access_token": seguridad.crear_token(u),
        "token_type": "bearer",
        "expira_en_minutos": seguridad.minutos_de_sesion(),
    }


@router.post("/login", response_model=schemas.Token)
def login(request: Request, formulario: OAuth2PasswordRequestForm = Depends()):
    """Inicia sesion con usuario y contrasena; devuelve un token que caduca.

    Con verificacion en dos pasos activa, no devuelve el token: devuelve
    `mfa_requerido` y un `mfa_token` para mandar con el codigo a POST
    /auth/mfa. En /docs, el boton "Authorize" solo sirve para cuentas sin MFA.
    Tras varios intentos fallidos seguidos desde un mismo equipo, ese equipo
    queda bloqueado unos minutos para esa cuenta.
    """
    try:
        u = seguridad.autenticar(formulario.username, formulario.password, _origen(request))
        if u.mfa_activo:
            return {
                "mfa_requerido": True,
                "mfa_token": seguridad.crear_token(u, "mfa"),
                "expira_en_minutos": seguridad.MINUTOS_PASO_MFA,
            }
        return _token_de_sesion(u)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@router.post("/mfa", response_model=schemas.Token)
def segundo_paso(request: Request, paso: schemas.MfaPaso):
    """Segundo paso: el codigo de 6 digitos de la app o un codigo de respaldo."""
    try:
        u = seguridad.usuario_del_token(paso.mfa_token, "mfa")
        if u is None:
            raise HTTPException(
                status_code=401, detail="La verificación venció; vuelve a escribir tu usuario y contraseña"
            )
        mfa.verificar_entrada(u, paso.codigo, _origen(request))
        return _token_de_sesion(u)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@router.post("/salir", status_code=204)
def salir(u: Usuario = Depends(sesion_actual)):
    """Cierra la sesion: el token (y los de tus otros dispositivos) deja de
    servir de inmediato, aunque alguien lo haya copiado."""
    try:
        seguridad.cerrar_sesion(u)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    return Response(status_code=204)


@router.get("/yo", response_model=schemas.UsuarioOut)
def yo(u: Usuario = Depends(sesion_actual)):
    """Quien eres, que areas puedes consultar y si tienes algo pendiente
    (contrasena temporal o MFA por configurar)."""
    return {
        **u.__dict__,
        "areas_permitidas": areas_visibles(u, ids_de_areas()),
        "mfa_obligatorio": u.rol in seguridad.roles_con_mfa(),
        "codigos_respaldo_restantes": mfa.respaldos_restantes(u.id) if u.mfa_activo else 0,
    }


@router.post("/contrasena", response_model=schemas.Token)
def cambiar_mi_contrasena(request: Request, cambio: schemas.CambioContrasena, u: Usuario = Depends(sesion_actual)):
    """Cambia tu contrasena (obligatorio si era temporal). Cierra tus otras
    sesiones y devuelve un token nuevo para esta. Una contrasena actual
    equivocada cuenta como intento fallido de inicio de sesion."""
    try:
        nuevo = seguridad.cambiar_mi_contrasena(u, cambio.actual, cambio.nueva, _origen(request))
    except ErrorDeUsuario as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    return _token_de_sesion(nuevo)


@router.post("/mfa/configurar", response_model=schemas.MfaConfiguracion)
def configurar_mfa(u: Usuario = Depends(sesion_actual)):
    """Genera el QR para la app de autenticacion. Se activa con POST /auth/mfa/activar."""
    try:
        return mfa.iniciar_configuracion(u)
    except ErrorDeUsuario as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@router.post("/mfa/activar", response_model=schemas.CodigosRespaldo)
def activar_mfa(solicitud: schemas.MfaActivar, u: Usuario = Depends(sesion_actual)):
    """Confirma con un codigo de la app. Devuelve los codigos de respaldo (una sola vez)."""
    try:
        return {"codigos": mfa.activar(u, solicitud.codigo)}
    except ErrorDeUsuario as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
