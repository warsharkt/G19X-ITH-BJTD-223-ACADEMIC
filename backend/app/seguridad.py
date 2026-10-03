"""Autenticacion y control de acceso por rol (paso 6, RF-06).

- Contrasenas: scrypt (biblioteca estandar) con sal aleatoria por usuario;
  nunca se guarda la contrasena.
- Sesion: token JWT firmado (HS256) que caduca. Se envia en cada peticion
  como "Authorization: Bearer <token>". En cada peticion se vuelve a leer el
  usuario de la BD: desactivarlo o cambiarle el rol surte efecto de inmediato.
- Fuerza bruta: tras INTENTOS_MAXIMOS fallos seguidos la cuenta se bloquea
  MINUTOS_BLOQUEO minutos.

Que ve cada rol (PRD, seccion 5 y regla 10.3.2):
    direccion -> solo el consolidado corporativo (area 0)
    rrhh      -> consolidado y todas las areas
    gerente   -> solo su area
    admin_ti  -> catalogos y configuracion; ningun dato de colaboradores
"""
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text

from app.database import engine, ejecutar_sql
from app.kpis import CORPORATIVO

ROLES = ("direccion", "rrhh", "gerente", "admin_ti")
ROLES_CON_DATOS = ("direccion", "rrhh", "gerente")
LONGITUD_MINIMA = 10
INTENTOS_MAXIMOS = 5
MINUTOS_BLOQUEO = 15
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}
_ALGORITMO = "HS256"

esquema_oauth = OAuth2PasswordBearer(tokenUrl="auth/login")
_tabla_lista = False


@dataclass(frozen=True)
class Usuario:
    id: int
    usuario: str
    nombre: str
    rol: str
    area_id: int | None


class ErrorDeUsuario(ValueError):
    """Datos invalidos al crear o modificar un usuario."""


def asegurar_tabla():
    global _tabla_lista
    if not _tabla_lista:
        ejecutar_sql("usuarios.sql")
        _tabla_lista = True


# ------------------------------------------------------------ contrasenas
def hash_contrasena(contrasena: str) -> str:
    sal = secrets.token_bytes(16)
    clave = hashlib.scrypt(contrasena.encode("utf-8"), salt=sal, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${sal.hex()}${clave.hex()}"


def verificar_contrasena(contrasena: str, guardado: str) -> bool:
    try:
        _, n, r, p, sal, clave = guardado.split("$")
        calculada = hashlib.scrypt(
            contrasena.encode("utf-8"), salt=bytes.fromhex(sal), n=int(n), r=int(r), p=int(p)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculada.hex(), clave)


# Para usuarios que no existen tambien se calcula un scrypt: asi el tiempo de
# respuesta no revela que nombres de usuario existen.
_HASH_SENUELO = hash_contrasena(secrets.token_hex(16))


def validar_contrasena_nueva(contrasena: str, usuario: str):
    if len(contrasena) < LONGITUD_MINIMA:
        raise ErrorDeUsuario(f"La contraseña debe tener al menos {LONGITUD_MINIMA} caracteres")
    if usuario.lower() in contrasena.lower():
        raise ErrorDeUsuario("La contraseña no puede contener el nombre de usuario")


# ---------------------------------------------------------------- usuarios
def crear_usuario(usuario: str, nombre: str, rol: str, contrasena: str, area_id: int | None = None) -> int:
    """Crea un usuario y devuelve su id. ErrorDeUsuario si los datos no son validos."""
    asegurar_tabla()
    usuario = usuario.strip().lower()
    if not usuario or not nombre.strip():
        raise ErrorDeUsuario("Usuario y nombre son obligatorios")
    if rol not in ROLES:
        raise ErrorDeUsuario(f"Rol '{rol}' no valido. Opciones: {', '.join(ROLES)}")
    if rol == "gerente" and (area_id is None or area_id == CORPORATIVO):
        raise ErrorDeUsuario("Un gerente necesita un area (no puede ser el consolidado corporativo)")
    if rol != "gerente" and area_id is not None:
        raise ErrorDeUsuario("Solo los gerentes tienen area; los demas roles no la llevan")
    validar_contrasena_nueva(contrasena, usuario)
    with engine.begin() as conn:
        if area_id is not None and not conn.execute(
            text("SELECT 1 FROM areas WHERE id = :a"), {"a": area_id}
        ).first():
            raise ErrorDeUsuario(f"El area {area_id} no existe")
        if conn.execute(text("SELECT 1 FROM usuarios WHERE usuario = :u"), {"u": usuario}).first():
            raise ErrorDeUsuario(f"El usuario '{usuario}' ya existe")
        return conn.execute(
            text(
                "INSERT INTO usuarios (usuario, nombre, rol, area_id, contrasena_hash) "
                "VALUES (:u, :n, :r, :a, :h) RETURNING id"
            ),
            {"u": usuario, "n": nombre.strip(), "r": rol, "a": area_id, "h": hash_contrasena(contrasena)},
        ).scalar_one()


def cambiar_contrasena(usuario: str, contrasena: str):
    """Nueva contrasena; tambien desbloquea la cuenta."""
    asegurar_tabla()
    usuario = usuario.strip().lower()
    validar_contrasena_nueva(contrasena, usuario)
    with engine.begin() as conn:
        filas = conn.execute(
            text(
                "UPDATE usuarios SET contrasena_hash = :h, intentos_fallidos = 0, bloqueado_hasta = NULL "
                "WHERE usuario = :u"
            ),
            {"u": usuario, "h": hash_contrasena(contrasena)},
        ).rowcount
    if not filas:
        raise ErrorDeUsuario(f"El usuario '{usuario}' no existe")


def autenticar(usuario: str, contrasena: str) -> Usuario:
    """Usuario si la contrasena es correcta; HTTPException 401 si no.

    El mensaje es el mismo si el usuario no existe o la contrasena esta mal,
    para no revelar que cuentas existen. La cuenta bloqueada si se avisa.
    """
    asegurar_tabla()
    invalido = HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos")
    # Los errores se lanzan FUERA de la transaccion: lanzarlos dentro la
    # desharia, y el conteo de intentos fallidos nunca se guardaria.
    error = None
    with engine.begin() as conn:
        fila = conn.execute(
            text(
                "SELECT id, usuario, nombre, rol, area_id, contrasena_hash, activo, bloqueado_hasta "
                "FROM usuarios WHERE usuario = :u FOR UPDATE"
            ),
            {"u": usuario.strip().lower()},
        ).mappings().first()
        ahora = datetime.now(timezone.utc)
        if fila is None or not fila["activo"]:
            verificar_contrasena(contrasena, _HASH_SENUELO)
            error = invalido
        elif fila["bloqueado_hasta"] and fila["bloqueado_hasta"] > ahora:
            minutos = int((fila["bloqueado_hasta"] - ahora).total_seconds() // 60) + 1
            error = HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Cuenta bloqueada por intentos fallidos. Intenta de nuevo en {minutos} minuto(s).",
            )
        elif not verificar_contrasena(contrasena, fila["contrasena_hash"]):
            # Tras un bloqueo el contador no se reinicia: un nuevo fallo vuelve a
            # bloquear de inmediato a quien siga probando contrasenas.
            conn.execute(
                text(
                    "UPDATE usuarios SET intentos_fallidos = intentos_fallidos + 1, "
                    "bloqueado_hasta = CASE WHEN intentos_fallidos + 1 >= :max "
                    "  THEN now() + make_interval(mins => :min) ELSE NULL END "
                    "WHERE id = :id"
                ),
                {"id": fila["id"], "max": INTENTOS_MAXIMOS, "min": MINUTOS_BLOQUEO},
            )
            error = invalido
        else:
            conn.execute(
                text(
                    "UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL, ultimo_acceso = now() "
                    "WHERE id = :id"
                ),
                {"id": fila["id"]},
            )
    if error is not None:
        raise error
    return Usuario(fila["id"], fila["usuario"], fila["nombre"], fila["rol"], fila["area_id"])


# ------------------------------------------------------------------ tokens
def _secreto() -> str:
    secreto = os.getenv("JWT_SECRETO", "")
    if len(secreto) < 32:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Falta JWT_SECRETO en el .env (minimo 32 caracteres). Genera uno con: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"',
        )
    return secreto


def minutos_de_sesion() -> int:
    return int(os.getenv("JWT_MINUTOS", "60"))


def crear_token(u: Usuario) -> str:
    ahora = datetime.now(timezone.utc)
    datos = {"sub": str(u.id), "iat": ahora, "exp": ahora + timedelta(minutes=minutos_de_sesion())}
    return jwt.encode(datos, _secreto(), algorithm=_ALGORITMO)


def usuario_actual(token: str = Depends(esquema_oauth)) -> Usuario:
    """Dependencia de FastAPI: el usuario del token, o 401."""
    no_autenticado = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Sesión no válida o vencida; vuelve a iniciar sesión",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        datos = jwt.decode(token, _secreto(), algorithms=[_ALGORITMO], options={"require": ["exp", "sub"]})
        id_ = int(datos["sub"])
    except (jwt.PyJWTError, ValueError):
        raise no_autenticado
    asegurar_tabla()
    with engine.connect() as conn:
        fila = conn.execute(
            text("SELECT id, usuario, nombre, rol, area_id FROM usuarios WHERE id = :id AND activo"),
            {"id": id_},
        ).first()
    if fila is None:
        raise no_autenticado
    return Usuario(*fila)


# ----------------------------------------------------------------- permisos
def area_por_defecto(u: Usuario) -> int:
    return u.area_id if u.rol == "gerente" else CORPORATIVO


def areas_visibles(u: Usuario, todas: list[int]) -> list[int]:
    """Areas (incluido el 0 = corporativo) que el usuario puede ver o elegir."""
    if u.rol in ("rrhh", "admin_ti"):  # admin_ti: solo como catalogo, sin datos
        return list(todas)
    if u.rol == "direccion":
        return [CORPORATIVO]
    return [u.area_id]


def exigir_acceso_a_datos(u: Usuario, area_id: int):
    """403 si el usuario no puede ver los datos de esa area."""
    if u.rol not in ROLES_CON_DATOS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tu rol no tiene acceso a datos de colaboradores")
    if u.rol == "direccion" and area_id != CORPORATIVO:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Dirección solo ve el consolidado corporativo (area 0)")
    if u.rol == "gerente" and area_id != u.area_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puedes ver los datos de tu área")


def con_acceso_a_datos(u: Usuario = Depends(usuario_actual)) -> Usuario:
    """Dependencia: usuario con un rol que puede ver datos de colaboradores."""
    if u.rol not in ROLES_CON_DATOS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tu rol no tiene acceso a datos de colaboradores")
    return u
