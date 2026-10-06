"""Autenticacion, cuentas y control de acceso por rol (pasos 6, 6.1 y 6.2).

- Contrasenas: scrypt (biblioteca estandar) con sal aleatoria por usuario;
  nunca se guarda la contrasena.
- Sesion: token JWT firmado (HS256) que caduca. Se envia en cada peticion
  como "Authorization: Bearer <token>". En cada peticion se vuelve a leer el
  usuario de la BD: desactivarlo o cambiarle el rol surte efecto de inmediato.
  El token lleva la version de sesion de la cuenta: al restablecer la
  contrasena o el MFA, los tokens anteriores dejan de servir.
- Fuerza bruta: tras INTENTOS_MAXIMOS fallos seguidos (contrasena o codigo de
  MFA) la cuenta se bloquea MINUTOS_BLOQUEO minutos.
- Pendientes: con una contrasena temporal, o sin MFA en un rol que lo exige
  (app/mfa.py), la sesion solo sirve para resolverlo; todo lo demas da 403.
- Cuentas: solo admin_ti las administra (lo exige la API) y nadie cambia su
  propio rol ni se desactiva. Cada cambio queda en `usuarios_cambios`
  (RF-11): quien, cuando y que, nunca contrasenas ni secretos.

Que ve cada rol (PRD, seccion 5 y regla 10.3.2):
    direccion -> solo el consolidado corporativo (area 0)
    rrhh      -> consolidado y todas las areas
    gerente   -> solo su area
    admin_ti  -> catalogos, configuracion y cuentas; ningun dato de colaboradores
"""
import hashlib
import hmac
import json
import os
import re
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
MINUTOS_PASO_MFA = 5  # para escribir el codigo tras la contrasena
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}
_ALGORITMO = "HS256"
# Sin letras ni numeros que se confundan (0/O, 1/l/I) al dictar una temporal
_ALFABETO_TEMPORAL = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"

esquema_oauth = OAuth2PasswordBearer(tokenUrl="auth/login")
_tabla_lista = False


@dataclass(frozen=True)
class Usuario:
    id: int
    usuario: str
    nombre: str
    rol: str
    area_id: int | None
    # "cambiar_contrasena" o "configurar_mfa": algo que resolver antes de usar el sistema
    pendiente: str | None = None
    mfa_activo: bool = False
    version_sesion: int = 0


class ErrorDeUsuario(ValueError):
    """Datos invalidos al crear o modificar un usuario."""


def asegurar_tabla():
    global _tabla_lista
    if not _tabla_lista:
        ejecutar_sql("usuarios.sql")
        _tabla_lista = True


def roles_con_mfa() -> set[str]:
    """Roles que deben usar MFA. Por defecto Direccion, TI y RRHH: los que ven
    todo o administran. Los gerentes pueden activarlo si quieren."""
    valor = os.getenv("MFA_OBLIGATORIO", "direccion,admin_ti,rrhh")
    return {r.strip() for r in valor.split(",") if r.strip()}


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


def generar_contrasena_temporal() -> str:
    """12 caracteres al azar en 3 grupos (p. ej. "k7Mq-3xPa-9tRe"), faciles de dictar."""
    grupos = ["".join(secrets.choice(_ALFABETO_TEMPORAL) for _ in range(4)) for _ in range(3)]
    return "-".join(grupos)


# --------------------------------------------------------------- bitacora
def registrar(conn, usuario: str, accion: str, hecho_por: str, detalle: dict | None = None):
    """Agrega a la bitacora de cuentas. Nunca recibe contrasenas ni secretos."""
    conn.execute(
        text(
            "INSERT INTO usuarios_cambios (usuario, accion, detalle, hecho_por) "
            "VALUES (:u, :a, CAST(:d AS jsonb), :p)"
        ),
        {"u": usuario, "a": accion, "d": json.dumps(detalle or {}, ensure_ascii=False, default=str), "p": hecho_por},
    )


def cambios(limite: int = 50, usuario: str | None = None) -> list[dict]:
    """Bitacora de cuentas, de lo mas reciente a lo mas antiguo."""
    asegurar_tabla()
    filtro, params = "", {"limite": limite}
    if usuario:
        filtro, params["u"] = "WHERE usuario = :u", usuario
    with engine.connect() as conn:
        filas = conn.execute(
            text(
                f"SELECT id, usuario, accion, detalle, hecho_por, hecho_en FROM usuarios_cambios {filtro} "
                "ORDER BY id DESC LIMIT :limite"
            ),
            params,
        ).mappings().all()
    return [dict(f) for f in filas]


# ---------------------------------------------------------------- usuarios
_PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_COLUMNAS_CUENTA = (
    "id, usuario, nombre, rol, area_id, correo, activo, debe_cambiar_contrasena, mfa_activo, "
    "creado_en, ultimo_acceso, COALESCE(bloqueado_hasta > now(), false) AS bloqueado"
)


def normalizar_correo(correo: str | None) -> str | None:
    """Correo en minusculas, None si viene vacio; ErrorDeUsuario si no parece un correo."""
    correo = (correo or "").strip().lower()
    if not correo:
        return None
    if not _PATRON_CORREO.match(correo):
        raise ErrorDeUsuario(f"'{correo}' no es un correo valido")
    return correo


def _validar_rol_y_area(conn, rol: str, area_id: int | None):
    if rol not in ROLES:
        raise ErrorDeUsuario(f"Rol '{rol}' no valido. Opciones: {', '.join(ROLES)}")
    if rol == "gerente" and (area_id is None or area_id == CORPORATIVO):
        raise ErrorDeUsuario("Un gerente necesita un area (no puede ser el consolidado corporativo)")
    if rol != "gerente" and area_id is not None:
        raise ErrorDeUsuario("Solo los gerentes tienen area; los demas roles no la llevan")
    if area_id is not None and not conn.execute(text("SELECT 1 FROM areas WHERE id = :a"), {"a": area_id}).first():
        raise ErrorDeUsuario(f"El area {area_id} no existe")


def crear_usuario(
    usuario: str,
    nombre: str,
    rol: str,
    contrasena: str,
    area_id: int | None = None,
    correo: str | None = None,
    por: str = "consola",
    temporal: bool = False,
) -> int:
    """Crea un usuario y devuelve su id. ErrorDeUsuario si los datos no son validos.

    temporal=True: la persona debe cambiar la contrasena al entrar (cuentas que
    crea TI desde el panel). correo es opcional: sirve para el correo de avisos."""
    asegurar_tabla()
    usuario = usuario.strip().lower()
    correo = normalizar_correo(correo)
    if not usuario or not nombre.strip():
        raise ErrorDeUsuario("Usuario y nombre son obligatorios")
    validar_contrasena_nueva(contrasena, usuario)
    with engine.begin() as conn:
        _validar_rol_y_area(conn, rol, area_id)
        if conn.execute(text("SELECT 1 FROM usuarios WHERE usuario = :u"), {"u": usuario}).first():
            raise ErrorDeUsuario(f"El usuario '{usuario}' ya existe")
        id_ = conn.execute(
            text(
                "INSERT INTO usuarios (usuario, nombre, rol, area_id, contrasena_hash, correo, debe_cambiar_contrasena) "
                "VALUES (:u, :n, :r, :a, :h, :c, :t) RETURNING id"
            ),
            {"u": usuario, "n": nombre.strip(), "r": rol, "a": area_id, "h": hash_contrasena(contrasena),
             "c": correo, "t": temporal},
        ).scalar_one()
        registrar(conn, usuario, "crear", por,
                  {"nombre": nombre.strip(), "rol": rol, "area_id": area_id, "correo": correo})
    return id_


def obtener_cuenta(usuario_id: int) -> dict | None:
    asegurar_tabla()
    with engine.connect() as conn:
        fila = conn.execute(
            text(f"SELECT {_COLUMNAS_CUENTA} FROM usuarios WHERE id = :i"), {"i": usuario_id}
        ).mappings().first()
    return dict(fila) if fila else None


def listar_cuentas() -> list[dict]:
    asegurar_tabla()
    with engine.connect() as conn:
        return [dict(f) for f in conn.execute(text(f"SELECT {_COLUMNAS_CUENTA} FROM usuarios ORDER BY usuario")).mappings()]


def _cuenta_para_cambiar(conn, usuario_id: int):
    fila = conn.execute(
        text("SELECT id, usuario, nombre, rol, area_id, correo, activo FROM usuarios WHERE id = :i FOR UPDATE"),
        {"i": usuario_id},
    ).mappings().first()
    if fila is None:
        raise LookupError(f"El usuario {usuario_id} no existe")
    return dict(fila)


def modificar_usuario(usuario_id: int, cambios_pedidos: dict, por: str) -> dict:
    """Cambia nombre, rol, area, correo o si esta activo, y lo registra.

    cambios_pedidos trae solo los campos a cambiar. Al pasar a un rol sin area,
    el area se quita sola. Nadie cambia su propio rol ni se desactiva.
    LookupError si no existe; ErrorDeUsuario si los datos no son validos."""
    asegurar_tabla()
    permitidos = {"nombre", "rol", "area_id", "correo", "activo"}
    if set(cambios_pedidos) - permitidos:
        raise ErrorDeUsuario(f"Solo se puede cambiar: {', '.join(sorted(permitidos))}")
    with engine.begin() as conn:
        actual = _cuenta_para_cambiar(conn, usuario_id)
        nuevo = {**actual, **cambios_pedidos}
        if "rol" in cambios_pedidos and nuevo["rol"] != "gerente" and "area_id" not in cambios_pedidos:
            nuevo["area_id"] = None
        nuevo["nombre"] = (nuevo["nombre"] or "").strip()
        if not nuevo["nombre"]:
            raise ErrorDeUsuario("El nombre es obligatorio")
        if "correo" in cambios_pedidos:
            nuevo["correo"] = normalizar_correo(nuevo["correo"])
        if actual["usuario"] == por and (nuevo["rol"] != actual["rol"] or not nuevo["activo"]):
            raise ErrorDeUsuario("No puedes cambiar tu propio rol ni desactivar tu cuenta: pídeselo a otra persona de TI")
        _validar_rol_y_area(conn, nuevo["rol"], nuevo["area_id"])

        diferencias = {c: [actual[c], nuevo[c]] for c in permitidos if actual[c] != nuevo[c]}
        if diferencias:
            conn.execute(
                text(
                    "UPDATE usuarios SET nombre = :nombre, rol = :rol, area_id = :area_id, correo = :correo, "
                    "activo = :activo WHERE id = :id"
                ),
                nuevo,
            )
            accion = "modificar"
            if set(diferencias) == {"activo"}:
                accion = "reactivar" if nuevo["activo"] else "desactivar"
            registrar(conn, actual["usuario"], accion, por, diferencias)
    return obtener_cuenta(usuario_id)


def restablecer_contrasena(usuario_id: int, por: str) -> str:
    """Pone una contrasena temporal (que se devuelve UNA vez para entregarla),
    obliga a cambiarla al entrar, desbloquea la cuenta y cierra sus sesiones."""
    asegurar_tabla()
    temporal = generar_contrasena_temporal()
    with engine.begin() as conn:
        actual = _cuenta_para_cambiar(conn, usuario_id)
        if actual["usuario"] == por:
            raise ErrorDeUsuario("Tu propia contraseña cámbiala desde Mi cuenta")
        conn.execute(
            text(
                "UPDATE usuarios SET contrasena_hash = :h, debe_cambiar_contrasena = true, intentos_fallidos = 0, "
                "bloqueado_hasta = NULL, version_sesion = version_sesion + 1 WHERE id = :i"
            ),
            {"i": usuario_id, "h": hash_contrasena(temporal)},
        )
        registrar(conn, actual["usuario"], "restablecer_contrasena", por)
    return temporal


def cambiar_contrasena(usuario: str, contrasena: str, por: str = "consola"):
    """Contrasena definitiva desde la consola (scripts/crear_usuario.py).
    Tambien desbloquea la cuenta y cierra sus sesiones."""
    asegurar_tabla()
    usuario = usuario.strip().lower()
    validar_contrasena_nueva(contrasena, usuario)
    with engine.begin() as conn:
        filas = conn.execute(
            text(
                "UPDATE usuarios SET contrasena_hash = :h, debe_cambiar_contrasena = false, intentos_fallidos = 0, "
                "bloqueado_hasta = NULL, version_sesion = version_sesion + 1 WHERE usuario = :u"
            ),
            {"u": usuario, "h": hash_contrasena(contrasena)},
        ).rowcount
        if not filas:
            raise ErrorDeUsuario(f"El usuario '{usuario}' no existe")
        registrar(conn, usuario, "restablecer_contrasena", por)


def cambiar_mi_contrasena(u: Usuario, actual: str, nueva: str) -> Usuario:
    """La persona cambia su contrasena (obligatorio si era temporal). Cierra sus
    otras sesiones; devuelve el usuario con la version nueva para darle token."""
    asegurar_tabla()
    validar_contrasena_nueva(nueva, u.usuario)
    if actual == nueva:
        raise ErrorDeUsuario("La contraseña nueva debe ser distinta de la actual")
    with engine.begin() as conn:
        guardado = conn.execute(
            text("SELECT contrasena_hash FROM usuarios WHERE id = :i FOR UPDATE"), {"i": u.id}
        ).scalar_one()
        if not verificar_contrasena(actual, guardado):
            raise ErrorDeUsuario("La contraseña actual no es correcta")
        conn.execute(
            text(
                "UPDATE usuarios SET contrasena_hash = :h, debe_cambiar_contrasena = false, "
                "version_sesion = version_sesion + 1 WHERE id = :i"
            ),
            {"i": u.id, "h": hash_contrasena(nueva)},
        )
        registrar(conn, u.usuario, "cambiar_contrasena", u.usuario)
    return _leer_usuario(u.id)


def cambiar_correo(usuario: str, correo: str | None, por: str = "consola"):
    """Pone o quita (correo vacio) el correo de un usuario."""
    asegurar_tabla()
    usuario = usuario.strip().lower()
    correo = normalizar_correo(correo)
    with engine.begin() as conn:
        antes = conn.execute(text("SELECT correo FROM usuarios WHERE usuario = :u FOR UPDATE"), {"u": usuario}).first()
        if antes is None:
            raise ErrorDeUsuario(f"El usuario '{usuario}' no existe")
        conn.execute(text("UPDATE usuarios SET correo = :c WHERE usuario = :u"), {"u": usuario, "c": correo})
        if antes[0] != correo:
            registrar(conn, usuario, "modificar", por, {"correo": [antes[0], correo]})


# ------------------------------------------------------------ autenticacion
def _pendiente(fila) -> str | None:
    if fila["debe_cambiar_contrasena"]:
        return "cambiar_contrasena"
    if fila["rol"] in roles_con_mfa() and not fila["mfa_activo"]:
        return "configurar_mfa"
    return None


def _a_usuario(fila) -> Usuario:
    return Usuario(
        fila["id"], fila["usuario"], fila["nombre"], fila["rol"], fila["area_id"],
        _pendiente(fila), fila["mfa_activo"], fila["version_sesion"],
    )


_COLUMNAS_SESION = "id, usuario, nombre, rol, area_id, debe_cambiar_contrasena, mfa_activo, version_sesion"


def _leer_usuario(usuario_id: int) -> Usuario | None:
    with engine.connect() as conn:
        fila = conn.execute(
            text(f"SELECT {_COLUMNAS_SESION} FROM usuarios WHERE id = :id AND activo"), {"id": usuario_id}
        ).mappings().first()
    return _a_usuario(fila) if fila else None


def registrar_fallo(conn, usuario_id: int):
    """Un fallo mas (contrasena o codigo). Tras un bloqueo el contador no se
    reinicia: un nuevo fallo vuelve a bloquear de inmediato."""
    conn.execute(
        text(
            "UPDATE usuarios SET intentos_fallidos = intentos_fallidos + 1, "
            "bloqueado_hasta = CASE WHEN intentos_fallidos + 1 >= :max "
            "  THEN now() + make_interval(mins => :min) ELSE NULL END "
            "WHERE id = :id"
        ),
        {"id": usuario_id, "max": INTENTOS_MAXIMOS, "min": MINUTOS_BLOQUEO},
    )


def registrar_entrada(conn, usuario_id: int):
    conn.execute(
        text("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL, ultimo_acceso = now() WHERE id = :id"),
        {"id": usuario_id},
    )


def error_si_bloqueada(fila) -> HTTPException | None:
    ahora = datetime.now(timezone.utc)
    if fila["bloqueado_hasta"] and fila["bloqueado_hasta"] > ahora:
        minutos = int((fila["bloqueado_hasta"] - ahora).total_seconds() // 60) + 1
        return HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Cuenta bloqueada por intentos fallidos. Intenta de nuevo en {minutos} minuto(s).",
        )
    return None


def autenticar(usuario: str, contrasena: str) -> Usuario:
    """Usuario si la contrasena es correcta; HTTPException 401 si no.

    El mensaje es el mismo si el usuario no existe o la contrasena esta mal,
    para no revelar que cuentas existen. La cuenta bloqueada si se avisa.
    Con MFA activo, el contador de fallos NO se reinicia aqui sino al acertar
    el codigo: si no, quien sabe la contrasena podria probar codigos sin fin
    alternandolos con entradas correctas.
    """
    asegurar_tabla()
    invalido = HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos")
    # Los errores se lanzan FUERA de la transaccion: lanzarlos dentro la
    # desharia, y el conteo de intentos fallidos nunca se guardaria.
    error = None
    with engine.begin() as conn:
        fila = conn.execute(
            text(
                f"SELECT {_COLUMNAS_SESION}, contrasena_hash, activo, bloqueado_hasta "
                "FROM usuarios WHERE usuario = :u FOR UPDATE"
            ),
            {"u": usuario.strip().lower()},
        ).mappings().first()
        if fila is None or not fila["activo"]:
            verificar_contrasena(contrasena, _HASH_SENUELO)
            error = invalido
        elif (bloqueo := error_si_bloqueada(fila)) is not None:
            error = bloqueo
        elif not verificar_contrasena(contrasena, fila["contrasena_hash"]):
            registrar_fallo(conn, fila["id"])
            error = invalido
        elif not fila["mfa_activo"]:
            registrar_entrada(conn, fila["id"])
    if error is not None:
        raise error
    return _a_usuario(fila)


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


def crear_token(u: Usuario, proposito: str = "sesion") -> str:
    """proposito "sesion": el token de uso normal. "mfa": solo sirve para
    escribir el codigo de MFA tras la contrasena, y dura pocos minutos."""
    ahora = datetime.now(timezone.utc)
    minutos = MINUTOS_PASO_MFA if proposito == "mfa" else minutos_de_sesion()
    datos = {"sub": str(u.id), "ver": u.version_sesion, "tipo": proposito, "iat": ahora,
             "exp": ahora + timedelta(minutes=minutos)}
    return jwt.encode(datos, _secreto(), algorithm=_ALGORITMO)


def usuario_del_token(token: str, proposito: str = "sesion") -> Usuario | None:
    """Usuario activo del token si es valido, del proposito pedido y de la
    version de sesion vigente; None si no."""
    try:
        datos = jwt.decode(
            token, _secreto(), algorithms=[_ALGORITMO], options={"require": ["exp", "sub", "ver", "tipo"]}
        )
        id_ = int(datos["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
    if datos["tipo"] != proposito:
        return None
    asegurar_tabla()
    u = _leer_usuario(id_)
    if u is None or u.version_sesion != datos["ver"]:
        return None
    return u


def sesion_actual(token: str = Depends(esquema_oauth)) -> Usuario:
    """Dependencia: el usuario del token, aunque tenga algo pendiente (cambiar
    la contrasena temporal o configurar el MFA). Solo para /auth/*."""
    u = usuario_del_token(token)
    if u is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sesión no válida o vencida; vuelve a iniciar sesión",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return u


PENDIENTES = {
    "cambiar_contrasena": "Antes de continuar debes cambiar tu contraseña temporal",
    "configurar_mfa": "Antes de continuar debes configurar la verificación en dos pasos (MFA)",
}


def usuario_actual(u: Usuario = Depends(sesion_actual)) -> Usuario:
    """Dependencia de casi toda la API: usuario con sesion y sin pendientes, o 401/403."""
    if u.pendiente:
        raise HTTPException(status.HTTP_403_FORBIDDEN, PENDIENTES[u.pendiente])
    return u


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
