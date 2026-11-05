"""Autenticacion, cuentas y control de acceso por rol (pasos 6, 6.1 y 6.2).

- Contrasenas: scrypt (biblioteca estandar) con sal aleatoria por usuario;
  nunca se guarda la contrasena.
- Sesion: token JWT firmado (HS256) que caduca. Se envia en cada peticion
  como "Authorization: Bearer <token>". En cada peticion se vuelve a leer el
  usuario de la BD: desactivarlo o cambiarle el rol surte efecto de inmediato.
  El token lleva la version de sesion de la cuenta: al restablecer la
  contrasena o el MFA, los tokens anteriores dejan de servir.
- Fuerza bruta: tras INTENTOS_MAXIMOS fallos seguidos (contrasena o codigo de
  MFA) desde un mismo origen (IP), ese origen queda bloqueado MINUTOS_BLOQUEO
  minutos para ese usuario; la persona puede seguir entrando desde su equipo.
  Si se bloquean ORIGENES_PARA_BLOQUEO_TOTAL origenes, se bloquea el usuario
  completo. Va por el nombre escrito, exista o no la cuenta: el bloqueo no
  revela que cuentas existen. Ademas nginx limita los intentos por IP.
- Cerrar sesion (POST /auth/salir) sube la version de sesion: el token deja
  de servir aunque alguien lo haya copiado.
- Firma de reportes: el permiso (firma_reportes) solo lo da o lo quita una
  Responsable de RRHH, o la consola del servidor. TI no: si TI restablece la
  contrasena o la verificacion en dos pasos de alguien que firma, ese
  permiso se suspende y se cancela su suplencia, hasta que otra Responsable
  lo devuelva. Asi una sola persona de TI no puede firmar reportes.
- Pendientes: con una contrasena temporal, sin MFA en un rol que lo exige
  (app/mfa.py) o sin la aprobacion de RRHH, la sesion solo sirve para
  resolverlo; todo lo demas da 403.
- Aprobacion: lo que TI hace y da acceso a datos de colaboradores (crear la
  cuenta, cambiarle rol o area, restablecer su contrasena o su MFA) deja la
  cuenta en espera hasta que una Responsable de RRHH la apruebe. TI no ve
  datos: tampoco puede abrirse una cuenta que los vea.
- Cuentas: solo admin_ti las administra (lo exige la API) y nadie cambia su
  propio rol ni se desactiva. Cada cambio queda en `usuarios_cambios`
  (RF-11): quien, cuando y que, nunca contrasenas ni secretos.

Que ve cada rol (PRD, seccion 5 y regla 10.3.2):
    direccion -> solo el consolidado corporativo (area 0)
    rrhh      -> consolidado y todas las areas
    gerente   -> solo su area
    admin_ti  -> catalogos, configuracion y cuentas; ningun dato de colaboradores

Dentro de RRHH (regla 10.3.9), quien prepara no firma:
    Analista de RRHH    -> carga los datos y genera los reportes
    Responsable de RRHH -> (firma_reportes) aprueba o rechaza los reportes
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

from app.origen import actual as origen_de_la_peticion
from app.database import engine, ejecutar_sql
from app.kpis import CORPORATIVO

ROLES = ("direccion", "rrhh", "gerente", "admin_ti")
ROLES_CON_DATOS = ("direccion", "rrhh", "gerente")
LONGITUD_MINIMA = 10
INTENTOS_MAXIMOS = 5             # por cuenta y origen
MINUTOS_BLOQUEO = 15
ORIGENES_PARA_BLOQUEO_TOTAL = 3  # origenes bloqueados a la vez -> toda la cuenta
MINUTOS_PASO_MFA = 5  # para escribir el codigo tras la contrasena
HORAS_CONTRASENA_TEMPORAL = 72  # despues, TI debe generar otra
DIAS_BITACORA_ACCESOS = 365
USUARIO_INEXISTENTE = "(usuario inexistente)"
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
    firma_reportes: bool = False  # Responsable de RRHH: firma los reportes

    @property
    def es_analista(self) -> bool:
        return self.rol == "rrhh" and not self.firma_reportes

    @property
    def es_responsable(self) -> bool:
        return self.rol == "rrhh" and self.firma_reportes


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


# Lo que la gente mas usa, sin los numeros y simbolos que le agrega al final para
# llegar al minimo ("Password123!" -> "password"). Solo atrapa lo mas obvio.
_PALABRAS_COMUNES = frozenset({
    "abc", "abcd", "abcde", "abcdef", "admin", "administrador", "administrator", "amor", "bienvenido", "bienvenida",
    "changeme", "clave", "contrasena", "contraseña", "demo", "empresa", "hola", "iloveyou", "letmein", "login",
    "master", "mexico", "monkey", "nordika", "pass", "passw0rd", "password", "qwerty", "qwertyuiop", "recursos",
    "rrhh", "secret", "secreto", "seguridad", "sistema", "talentia", "teamo", "test", "usuario", "welcome",
})
_SECUENCIAS = ("01234567890123456789", "abcdefghijklmnopqrstuvwxyz", "qwertyuiop", "asdfghjkl", "zxcvbnm")
_RELLENO = "0123456789!@#$%&*.-_ "


def _es_trivial(contrasena: str) -> bool:
    c = contrasena.lower()
    return (
        len(set(c)) < 4  # aaaaaaaaaa, 1212121212
        or c in (c + c)[1:-1]  # un patron que se repite: abcabcabca
        or any(c in s or c in s[::-1] for s in _SECUENCIAS)  # 1234567890, abcdefghij
        or c.strip(_RELLENO) in _PALABRAS_COMUNES
    )


def validar_contrasena_nueva(contrasena: str, usuario: str):
    if len(contrasena) < LONGITUD_MINIMA:
        raise ErrorDeUsuario(f"La contraseña debe tener al menos {LONGITUD_MINIMA} caracteres")
    if usuario.lower() in contrasena.lower():
        raise ErrorDeUsuario("La contraseña no puede contener el nombre de usuario")
    if _es_trivial(contrasena):
        raise ErrorDeUsuario("Esa contraseña es demasiado común o fácil de adivinar: elige otra")


def generar_contrasena_temporal() -> str:
    """12 caracteres al azar en 3 grupos (p. ej. "k7Mq-3xPa-9tRe"), faciles de dictar."""
    grupos = ["".join(secrets.choice(_ALFABETO_TEMPORAL) for _ in range(4)) for _ in range(3)]
    return "-".join(grupos)


# --------------------------------------------------------------- bitacora
def registrar(conn, usuario: str, accion: str, hecho_por: str, detalle: dict | None = None):
    """Agrega a la bitacora de cuentas, con la IP de la peticion (None desde la
    consola o el arranque). Nunca recibe contrasenas ni secretos."""
    conn.execute(
        text(
            "INSERT INTO usuarios_cambios (usuario, accion, detalle, hecho_por, origen) "
            "VALUES (:u, :a, CAST(:d AS jsonb), :p, :o)"
        ),
        {"u": usuario, "a": accion, "d": json.dumps(detalle or {}, ensure_ascii=False, default=str), "p": hecho_por,
         "o": origen_de_la_peticion.get()},
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
                f"SELECT id, usuario, accion, detalle, hecho_por, hecho_en, origen FROM usuarios_cambios {filtro} "
                "ORDER BY id DESC LIMIT :limite"
            ),
            params,
        ).mappings().all()
    return [dict(f) for f in filas]


def accesos(limite: int = 100, usuario: str | None = None) -> list[dict]:
    """Bitacora de accesos, de lo mas reciente a lo mas antiguo."""
    asegurar_tabla()
    filtro, params = "", {"limite": limite}
    if usuario:
        filtro, params["u"] = "WHERE usuario = :u", usuario
    with engine.connect() as conn:
        filas = conn.execute(
            text(f"SELECT id, usuario, evento, origen, momento FROM accesos {filtro} ORDER BY id DESC LIMIT :limite"),
            params,
        ).mappings().all()
    return [dict(f) for f in filas]


# ---------------------------------------------------------------- usuarios
_PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_COLUMNAS_CUENTA = (
    "id, usuario, nombre, rol, area_id, correo, activo, debe_cambiar_contrasena, mfa_activo, firma_reportes, "
    "acceso_aprobado, creado_en, ultimo_acceso, (COALESCE(bloqueado_hasta > now(), false) OR EXISTS ("
    "  SELECT 1 FROM bloqueos_acceso b WHERE b.usuario = usuarios.usuario AND b.bloqueado_hasta > now()"
    ")) AS bloqueado"
)


def normalizar_correo(correo: str | None) -> str | None:
    """Correo en minusculas, None si viene vacio; ErrorDeUsuario si no parece un correo."""
    correo = (correo or "").strip().lower()
    if not correo:
        return None
    if not _PATRON_CORREO.match(correo):
        raise ErrorDeUsuario(f"'{correo}' no es un correo valido")
    return correo


def _validar_rol_y_area(conn, rol: str, area_id: int | None, firma_reportes: bool = False):
    if firma_reportes and rol != "rrhh":
        raise ErrorDeUsuario("Solo una persona de RRHH puede ser Responsable de firmar los reportes")
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
    firma_reportes: bool = False,
) -> int:
    """Crea un usuario y devuelve su id. ErrorDeUsuario si los datos no son validos.

    temporal=True: la persona debe cambiar la contrasena al entrar (cuentas que
    crea TI desde el panel) y, si la cuenta ve datos de colaboradores, espera la
    aprobacion de RRHH. correo es opcional: sirve para el correo de avisos.
    firma_reportes=True: Responsable de RRHH (firma); si no, Analista."""
    asegurar_tabla()
    usuario = usuario.strip().lower()
    correo = normalizar_correo(correo)
    if not usuario or not nombre.strip():
        raise ErrorDeUsuario("Usuario y nombre son obligatorios")
    validar_contrasena_nueva(contrasena, usuario)
    with engine.begin() as conn:
        _validar_rol_y_area(conn, rol, area_id, firma_reportes)
        if conn.execute(text("SELECT 1 FROM usuarios WHERE usuario = :u"), {"u": usuario}).first():
            raise ErrorDeUsuario(f"El usuario '{usuario}' ya existe")
        id_ = conn.execute(
            text(
                "INSERT INTO usuarios (usuario, nombre, rol, area_id, contrasena_hash, correo, debe_cambiar_contrasena, "
                "firma_reportes, acceso_aprobado, temporal_vence) VALUES (:u, :n, :r, :a, :h, :c, :t, :f, :ok, "
                "CASE WHEN :t THEN now() + make_interval(hours => :horas) END) RETURNING id"
            ),
            {"u": usuario, "n": nombre.strip(), "r": rol, "a": area_id, "h": hash_contrasena(contrasena),
             "c": correo, "t": temporal, "f": firma_reportes, "horas": HORAS_CONTRASENA_TEMPORAL,
             "ok": not (temporal and rol in ROLES_CON_DATOS)},
        ).scalar_one()
        # el bloqueo va por nombre: lo que alguien intento antes con ese nombre no aplica
        conn.execute(text("DELETE FROM bloqueos_acceso WHERE usuario = :u"), {"u": usuario})
        registrar(conn, usuario, "crear", por,
                  {"nombre": nombre.strip(), "rol": rol, "area_id": area_id, "correo": correo,
                   "firma_reportes": firma_reportes})
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
        text(
            "SELECT id, usuario, nombre, rol, area_id, correo, activo, firma_reportes "
            "FROM usuarios WHERE id = :i FOR UPDATE"
        ),
        {"i": usuario_id},
    ).mappings().first()
    if fila is None:
        raise LookupError(f"El usuario {usuario_id} no existe")
    return dict(fila)


def pedir_aprobacion(conn, usuario_id: int):
    """TI toco un acceso a datos de colaboradores: queda en espera de RRHH."""
    conn.execute(
        text("UPDATE usuarios SET acceso_aprobado = false WHERE id = :i AND rol = ANY(:r)"),
        {"i": usuario_id, "r": list(ROLES_CON_DATOS)},
    )


def resolver_aprobacion(usuario_id: int, aprobada: bool, por: str) -> dict:
    """Una Responsable de RRHH aprueba el acceso que dejo en espera TI, o lo
    rechaza: la cuenta se desactiva, y seguiria en espera aunque TI la reactive."""
    asegurar_tabla()
    with engine.begin() as conn:
        actual = _cuenta_para_cambiar(conn, usuario_id)
        if actual["usuario"] == por:
            raise ErrorDeUsuario("Tu propio acceso lo aprueba otra Responsable de RRHH")
        espera = conn.execute(text("SELECT NOT acceso_aprobado FROM usuarios WHERE id = :i"), {"i": usuario_id}).scalar()
        if not espera or not actual["activo"]:
            raise ErrorDeUsuario("Esa cuenta no está esperando aprobación")
        conn.execute(
            text(
                "UPDATE usuarios SET acceso_aprobado = :a, activo = :a, "
                "version_sesion = version_sesion + CASE WHEN :a THEN 0 ELSE 1 END WHERE id = :i"
            ),
            {"a": aprobada, "i": usuario_id},
        )
        registrar(conn, actual["usuario"], "aprobar_acceso" if aprobada else "rechazar_acceso", por)
    return obtener_cuenta(usuario_id)


def modificar_usuario(usuario_id: int, cambios_pedidos: dict, por: str, desde_panel: bool = False) -> dict:
    """Cambia nombre, rol, area, correo, si firma los reportes o si esta
    activo, y lo registra.

    cambios_pedidos trae solo los campos a cambiar. Al pasar a un rol sin area,
    el area se quita sola, y al salir de RRHH deja de firmar. Nadie cambia su
    propio rol ni se desactiva. desde_panel=True (TI): un cambio de rol o area
    que da acceso a datos queda en espera de la aprobacion de RRHH.
    LookupError si no existe; ErrorDeUsuario si los datos no son validos."""
    asegurar_tabla()
    permitidos = {"nombre", "rol", "area_id", "correo", "activo", "firma_reportes"}
    if set(cambios_pedidos) - permitidos:
        raise ErrorDeUsuario(f"Solo se puede cambiar: {', '.join(sorted(permitidos))}")
    with engine.begin() as conn:
        actual = _cuenta_para_cambiar(conn, usuario_id)
        nuevo = {**actual, **cambios_pedidos}
        if "rol" in cambios_pedidos and nuevo["rol"] != "gerente" and "area_id" not in cambios_pedidos:
            nuevo["area_id"] = None
        if nuevo["rol"] != "rrhh" and "firma_reportes" not in cambios_pedidos:
            nuevo["firma_reportes"] = False
        nuevo["nombre"] = (nuevo["nombre"] or "").strip()
        if not nuevo["nombre"]:
            raise ErrorDeUsuario("El nombre es obligatorio")
        if "correo" in cambios_pedidos:
            nuevo["correo"] = normalizar_correo(nuevo["correo"])
        if actual["usuario"] == por and (
            nuevo["rol"] != actual["rol"] or not nuevo["activo"] or nuevo["firma_reportes"] != actual["firma_reportes"]
        ):
            raise ErrorDeUsuario("No puedes cambiar tu propio rol ni desactivar tu cuenta: pídeselo a otra persona de TI")
        _validar_rol_y_area(conn, nuevo["rol"], nuevo["area_id"], nuevo["firma_reportes"])

        diferencias = {c: [actual[c], nuevo[c]] for c in permitidos if actual[c] != nuevo[c]}
        if diferencias:
            conn.execute(
                text(
                    "UPDATE usuarios SET nombre = :nombre, rol = :rol, area_id = :area_id, correo = :correo, "
                    "activo = :activo, firma_reportes = :firma_reportes WHERE id = :id"
                ),
                nuevo,
            )
            if desde_panel and {"rol", "area_id"} & set(diferencias):
                pedir_aprobacion(conn, usuario_id)
            accion = "modificar"
            if set(diferencias) == {"activo"}:
                accion = "reactivar" if nuevo["activo"] else "desactivar"
            registrar(conn, actual["usuario"], accion, por, diferencias)
    return obtener_cuenta(usuario_id)


def _desbloquear(conn, usuario_id: int):
    conn.execute(
        text("DELETE FROM bloqueos_acceso WHERE usuario = (SELECT usuario FROM usuarios WHERE id = :i)"),
        {"i": usuario_id},
    )


def suspender_firma(conn, cuenta: dict, por: str, motivo: str) -> bool:
    """Quita el permiso de firmar y cancela la suplencia abierta de la cuenta.
    Se usa cuando TI toma el control de su acceso (contrasena o MFA): quien
    restablece el acceso no debe poder firmar con esa cuenta. Devuelve si
    la cuenta firmaba (como Responsable o como suplente)."""
    suplencias = conn.execute(
        text(
            "UPDATE suplencias SET cancelada_por = :p, cancelada_en = now() "
            "WHERE cancelada_en IS NULL AND suplente = :u RETURNING id"
        ),
        {"p": por, "u": cuenta["usuario"]},
    ).all()
    if cuenta["firma_reportes"]:
        conn.execute(text("UPDATE usuarios SET firma_reportes = false WHERE id = :i"), {"i": cuenta["id"]})
    if cuenta["firma_reportes"] or suplencias:
        registrar(conn, cuenta["usuario"], "suspender_firma", por,
                  {"firma_reportes": [cuenta["firma_reportes"], False], "motivo": motivo,
                   "suplencias_canceladas": len(suplencias)})
        return True
    return False


def restablecer_contrasena(usuario_id: int, por: str) -> tuple[str, bool]:
    """Pone una contrasena temporal (que se devuelve UNA vez para entregarla),
    obliga a cambiarla al entrar, desbloquea la cuenta y cierra sus sesiones.
    Si la cuenta firmaba reportes, el permiso se suspende (lo devuelve otra
    Responsable), y si ve datos queda en espera de la aprobacion de RRHH: la
    temporal la conoce TI. Devuelve la temporal y si se suspendio la firma."""
    asegurar_tabla()
    temporal = generar_contrasena_temporal()
    with engine.begin() as conn:
        actual = _cuenta_para_cambiar(conn, usuario_id)
        if actual["usuario"] == por:
            raise ErrorDeUsuario("Tu propia contraseña cámbiala desde Mi cuenta")
        conn.execute(
            text(
                "UPDATE usuarios SET contrasena_hash = :h, debe_cambiar_contrasena = true, intentos_fallidos = 0, "
                "bloqueado_hasta = NULL, version_sesion = version_sesion + 1, "
                "temporal_vence = now() + make_interval(hours => :horas) WHERE id = :i"
            ),
            {"i": usuario_id, "h": hash_contrasena(temporal), "horas": HORAS_CONTRASENA_TEMPORAL},
        )
        pedir_aprobacion(conn, usuario_id)
        _desbloquear(conn, usuario_id)
        registrar(conn, actual["usuario"], "restablecer_contrasena", por)
        suspendida = suspender_firma(conn, actual, por, "se restableció su contraseña")
    return temporal, suspendida


def cambiar_firma(usuario_id: int, firma: bool, por: str) -> dict:
    """Da o quita el permiso de firmar reportes. Lo llama una Responsable de
    RRHH desde la API (nunca TI) o la consola del servidor.

    Para darlo, la cuenta debe ser de RRHH, estar activa y haber entrado ya
    con su propia contrasena y su verificacion en dos pasos: asi el permiso
    no llega a una cuenta cuya contrasena temporal conoce TI."""
    asegurar_tabla()
    with engine.begin() as conn:
        actual = _cuenta_para_cambiar(conn, usuario_id)
        if actual["usuario"] == por:
            raise ErrorDeUsuario("Tu propio permiso de firma lo cambia otra Responsable de RRHH")
        if firma:
            estado = conn.execute(
                text("SELECT debe_cambiar_contrasena, mfa_activo, acceso_aprobado FROM usuarios WHERE id = :i"),
                {"i": usuario_id},
            ).mappings().one()
            if actual["rol"] != "rrhh" or not actual["activo"]:
                raise ErrorDeUsuario("Solo una cuenta activa de RRHH puede firmar los reportes")
            if estado["debe_cambiar_contrasena"] or not estado["mfa_activo"]:
                raise ErrorDeUsuario(
                    "Esa persona debe entrar primero, cambiar su contraseña temporal y activar su verificación "
                    "en dos pasos: así nadie más conoce su acceso"
                )
            if not estado["acceso_aprobado"]:
                raise ErrorDeUsuario("Primero aprueba el acceso de esa persona")
        if actual["firma_reportes"] != firma:
            conn.execute(text("UPDATE usuarios SET firma_reportes = :f WHERE id = :i"), {"f": firma, "i": usuario_id})
            registrar(conn, actual["usuario"], "dar_firma" if firma else "quitar_firma", por,
                      {"firma_reportes": [actual["firma_reportes"], firma]})
    return obtener_cuenta(usuario_id)


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
                "bloqueado_hasta = NULL, version_sesion = version_sesion + 1, temporal_vence = NULL WHERE usuario = :u"
            ),
            {"u": usuario, "h": hash_contrasena(contrasena)},
        ).rowcount
        if not filas:
            raise ErrorDeUsuario(f"El usuario '{usuario}' no existe")
        conn.execute(
            text("DELETE FROM bloqueos_acceso WHERE usuario = :u"),
            {"u": usuario},
        )
        registrar(conn, usuario, "restablecer_contrasena", por)


def cambiar_mi_contrasena(u: Usuario, actual: str, nueva: str, origen: str = "local") -> Usuario:
    """La persona cambia su contrasena (obligatorio si era temporal). Cierra sus
    otras sesiones; devuelve el usuario con la version nueva para darle token.

    Una contrasena actual equivocada cuenta como intento fallido, igual que al
    entrar: si no, con una sesion robada se podria adivinar la contrasena sin
    limite y despues entrar desde cualquier equipo."""
    asegurar_tabla()
    validar_contrasena_nueva(nueva, u.usuario)
    if actual == nueva:
        raise ErrorDeUsuario("La contraseña nueva debe ser distinta de la actual")
    error = None  # se lanza fuera de la transaccion para que el fallo se guarde
    with engine.begin() as conn:
        guardado = conn.execute(
            text("SELECT contrasena_hash FROM usuarios WHERE id = :i FOR UPDATE"), {"i": u.id}
        ).scalar_one()
        if (bloqueo := error_si_bloqueada(conn, u.usuario, origen)) is not None:
            error = bloqueo
        elif not verificar_contrasena(actual, guardado):
            registrar_fallo(conn, u.usuario, origen)
            error = ErrorDeUsuario("La contraseña actual no es correcta")
    if error is not None:
        raise error
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE usuarios SET contrasena_hash = :h, debe_cambiar_contrasena = false, temporal_vence = NULL, "
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
    if not fila["acceso_aprobado"]:
        return "aprobacion"
    return None


def _a_usuario(fila) -> Usuario:
    return Usuario(
        fila["id"], fila["usuario"], fila["nombre"], fila["rol"], fila["area_id"],
        _pendiente(fila), fila["mfa_activo"], fila["version_sesion"], fila["firma_reportes"],
    )


_COLUMNAS_SESION = (
    "id, usuario, nombre, rol, area_id, debe_cambiar_contrasena, mfa_activo, version_sesion, firma_reportes, "
    "acceso_aprobado, temporal_vence"
)


def _leer_usuario(usuario_id: int) -> Usuario | None:
    with engine.connect() as conn:
        fila = conn.execute(
            text(f"SELECT {_COLUMNAS_SESION} FROM usuarios WHERE id = :id AND activo"), {"id": usuario_id}
        ).mappings().first()
    return _a_usuario(fila) if fila else None


def registrar_fallo(conn, usuario: str, origen: str):
    """Un fallo mas (contrasena o codigo) de ese nombre de usuario desde ese
    origen, exista o no la cuenta. Tras un bloqueo el contador no se reinicia:
    un nuevo fallo desde ahi vuelve a bloquear. Purga lo que ya no sirve."""
    conn.execute(
        text(
            "INSERT INTO bloqueos_acceso (usuario, origen, intentos, bloqueado_hasta) "
            "VALUES (:u, :o, 1, CASE WHEN 1 >= :max THEN now() + make_interval(mins => :min) END) "
            "ON CONFLICT (usuario, origen) DO UPDATE SET intentos = bloqueos_acceso.intentos + 1, "
            "actualizado_en = now(), bloqueado_hasta = CASE WHEN bloqueos_acceso.intentos + 1 >= :max "
            "  THEN now() + make_interval(mins => :min) ELSE NULL END"
        ),
        {"u": usuario, "o": origen, "max": INTENTOS_MAXIMOS, "min": MINUTOS_BLOQUEO},
    )
    conn.execute(text(
        "DELETE FROM bloqueos_acceso WHERE actualizado_en < now() - make_interval(days => 1) "
        "AND (bloqueado_hasta IS NULL OR bloqueado_hasta < now())"
    ))
    conn.execute(
        text(
            "INSERT INTO accesos (usuario, evento, origen) VALUES "
            "(COALESCE((SELECT usuario FROM usuarios WHERE usuario = :u), :x), 'fallo', :o)"
        ),
        {"u": usuario, "x": USUARIO_INEXISTENTE, "o": origen},
    )
    conn.execute(
        text("DELETE FROM accesos WHERE momento < now() - make_interval(days => :d)"), {"d": DIAS_BITACORA_ACCESOS}
    )


def registrar_entrada(conn, usuario_id: int, usuario: str, origen: str):
    conn.execute(
        text("DELETE FROM bloqueos_acceso WHERE usuario = :u AND origen = :o"), {"u": usuario, "o": origen}
    )
    conn.execute(
        text("UPDATE usuarios SET intentos_fallidos = 0, ultimo_acceso = now() WHERE id = :id"), {"id": usuario_id}
    )
    conn.execute(
        text("INSERT INTO accesos (usuario, evento, origen) VALUES (:u, 'entrada', :o)"), {"u": usuario, "o": origen}
    )


def error_si_bloqueada(conn, usuario: str, origen: str) -> HTTPException | None:
    """429 si ese nombre de usuario esta bloqueado desde este origen, o desde
    ORIGENES_PARA_BLOQUEO_TOTAL origenes a la vez (entonces, para todos).
    Igual para una cuenta que no existe: el 429 no revela cuales existen."""
    ahora = datetime.now(timezone.utc)
    del_origen, bloqueados, primero = conn.execute(
        text(
            "SELECT MAX(bloqueado_hasta) FILTER (WHERE origen = :o), COUNT(*), MIN(bloqueado_hasta) "
            "FROM bloqueos_acceso WHERE usuario = :u AND bloqueado_hasta > now()"
        ),
        {"u": usuario, "o": origen},
    ).one()
    total = primero if bloqueados >= ORIGENES_PARA_BLOQUEO_TOTAL else None
    hasta = max((h for h in (total, del_origen) if h), default=None)
    if hasta:
        minutos = int((hasta - ahora).total_seconds() // 60) + 1
        donde = "por intentos fallidos desde varios equipos" if total else "en este equipo por intentos fallidos"
        return HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Cuenta bloqueada {donde}. Intenta de nuevo en {minutos} minuto(s) o pide a TI que la desbloquee.",
        )
    return None


def autenticar(usuario: str, contrasena: str, origen: str = "local") -> Usuario:
    """Usuario si la contrasena es correcta; HTTPException 401 si no.
    origen: IP de quien intenta entrar (el bloqueo es por usuario y origen).

    Una cuenta que no existe (o desactivada) se comporta igual que una con la
    contrasena mal, tambien al bloquearse: no se revela que cuentas existen.
    Con MFA activo, el contador de fallos NO se reinicia aqui sino al acertar
    el codigo: si no, quien sabe la contrasena podria probar codigos sin fin
    alternandolos con entradas correctas.
    """
    asegurar_tabla()
    invalido = HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos")
    nombre = usuario.strip().lower()
    # Los errores se lanzan FUERA de la transaccion: lanzarlos dentro la
    # desharia, y el conteo de intentos fallidos nunca se guardaria.
    error = None
    with engine.begin() as conn:
        fila = conn.execute(
            text(f"SELECT {_COLUMNAS_SESION}, contrasena_hash, activo FROM usuarios WHERE usuario = :u FOR UPDATE"),
            {"u": nombre},
        ).mappings().first()
        existe = fila is not None and fila["activo"]
        if (bloqueo := error_si_bloqueada(conn, nombre, origen)) is not None:
            error = bloqueo
        elif not verificar_contrasena(contrasena, fila["contrasena_hash"] if existe else _HASH_SENUELO) or not existe:
            registrar_fallo(conn, nombre, origen)
            error = invalido
        elif fila["temporal_vence"] and fila["temporal_vence"] < datetime.now(timezone.utc):
            error = HTTPException(status.HTTP_401_UNAUTHORIZED, "Tu contraseña temporal venció: pide a TI una nueva")
        elif not fila["mfa_activo"]:
            registrar_entrada(conn, fila["id"], nombre, origen)
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


def cerrar_sesion(u: Usuario):
    """Invalida los tokens de la cuenta (todos sus dispositivos): sin esto, un
    token copiado seguiria sirviendo hasta caducar aunque la persona salga."""
    with engine.begin() as conn:
        conn.execute(text("UPDATE usuarios SET version_sesion = version_sesion + 1 WHERE id = :i"), {"i": u.id})


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
    "aprobacion": "Tu acceso espera la aprobación de la Responsable de RRHH",
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


def solo_rrhh(u: Usuario = Depends(usuario_actual)) -> Usuario:
    """Dependencia: la programacion mensual la cambia solo RRHH (regla 10.3.10)."""
    if u.rol != "rrhh":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo Recursos Humanos puede cambiar esta configuración")
    return u


def solo_responsable(u: Usuario = Depends(usuario_actual)) -> Usuario:
    """Dependencia: los umbrales los cambia solo la Responsable de RRHH (regla
    10.3.3). Un umbral decide que sale en rojo en los reportes, asi que quien
    los prepara (la Analista) no lo mueve."""
    if not u.es_responsable:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo la Responsable de RRHH puede cambiar los umbrales")
    return u


def solo_ti(u: Usuario = Depends(usuario_actual)) -> Usuario:
    """Dependencia: las cuentas las administra solo TI. Quien administra cuentas
    no aprueba reportes, y RRHH no puede crearse una segunda cuenta (regla 10.3.9)."""
    if u.rol != "admin_ti":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo Administración de TI puede administrar cuentas")
    return u


def ti_o_rrhh(u: Usuario = Depends(usuario_actual)) -> Usuario:
    """Dependencia: ver las cuentas y su bitacora, TI y RRHH (para auditar a TI)."""
    if u.rol not in ("admin_ti", "rrhh"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo TI y Recursos Humanos pueden ver las cuentas")
    return u


def solo_analista(u: Usuario = Depends(usuario_actual)) -> Usuario:
    """Dependencia: cargar datos y generar reportes es trabajo de la Analista
    de RRHH. La Responsable los firma: quien prepara no firma (regla 10.3.9)."""
    if u.rol != "rrhh":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Los reportes y la carga de datos los prepara Recursos Humanos. Si necesitas un reporte, pídeselo a RRHH.",
        )
    if u.firma_reportes:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Tú firmas los reportes: los prepara una Analista de RRHH, así siempre los revisa alguien distinto.",
        )
    return u
