"""Verificacion en dos pasos con codigos TOTP (hito 6.1).

La persona escanea un QR con una app (Google Authenticator, Microsoft
Authenticator, etc.) y, al entrar, despues de la contrasena escribe el codigo
de 6 digitos que muestra la app. Obligatorio para los roles de
seguridad.roles_con_mfa() (Direccion, TI y RRHH por defecto); los gerentes
pueden activarlo.

- Un codigo sirve una sola vez (mfa_ultimo_paso), aunque siga vigente.
- Se aceptan el codigo actual y los de 30 s antes y despues (relojes desfasados).
- Al activarlo se entregan CODIGOS_RESPALDO codigos de un solo uso para cuando
  no se tenga el telefono. Solo se guarda su hash y se muestran una vez.
- Si se pierde todo, TI reinicia el MFA de la cuenta (queda en la bitacora) y
  la persona lo vuelve a configurar al entrar.
- Los codigos equivocados cuentan como intentos fallidos: tras
  INTENTOS_MAXIMOS la cuenta se bloquea, igual que con la contrasena.
- El secreto se guarda cifrado (AES-256-GCM) con una llave que no vive en la
  base: MFA_LLAVE en el .env o, si no esta, el archivo llaves/mfa.key, que se
  genera solo la primera vez. Quien copie la base no puede generar codigos.
  El cifrado va atado a la cuenta: copiar el secreto de una cuenta a otra no
  sirve. Si la llave se pierde, TI reinicia el MFA de cada cuenta.
"""
import base64
import binascii
import hashlib
import hmac
import os
import secrets
import time

import pyotp
import qrcode
import qrcode.image.svg
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, status
from sqlalchemy import text

from app import seguridad
from app.database import RAIZ, engine
from app.marca import PRODUCTO
from app.seguridad import ErrorDeUsuario, Usuario

EMISOR = PRODUCTO  # el nombre que muestra la app del telefono
CODIGOS_RESPALDO = 10
_ALFABETO_RESPALDO = "abcdefghjkmnpqrstuvwxyz23456789"
_VERSION_CIFRADO = "v1:"


class MfaInvalido(ErrorDeUsuario):
    """Codigo incorrecto o MFA en un estado que no permite la operacion."""


class LlaveMfaInvalida(RuntimeError):
    """MFA_LLAVE o el archivo de la llave no tienen una llave valida."""


# ------------------------------------------------------- secreto cifrado
def archivo_de_llave():
    return RAIZ / "llaves" / "mfa.key"


def _leer_o_crear_archivo() -> str:
    ruta = archivo_de_llave()
    try:
        return ruta.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        pass
    nueva = base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode()
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        # "x": si otro proceso la creo al mismo tiempo, se usa la suya
        with open(ruta, "x", encoding="ascii") as f:
            f.write(nueva + "\n")
        os.chmod(ruta, 0o600)
        print(f"Se genero la llave del MFA en {ruta}. Respaldala aparte de la base de datos.")
        return nueva
    except FileExistsError:
        return ruta.read_text(encoding="ascii").strip()
    except OSError as exc:
        raise LlaveMfaInvalida(f"No se pudo crear la llave del MFA en {ruta} ({exc}). Pon MFA_LLAVE en el .env")


def _llave() -> bytes:
    """La llave de 32 bytes: MFA_LLAVE, o el archivo (se crea si no existe)."""
    texto = os.getenv("MFA_LLAVE", "").strip() or _leer_o_crear_archivo()
    try:
        llave = base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))
    except (binascii.Error, ValueError):
        llave = b""
    if len(llave) != 32:
        raise LlaveMfaInvalida(
            "MFA_LLAVE no es una llave valida (32 bytes en base64). Genera una con: "
            'python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"'
        )
    return llave


def _contexto(usuario_id: int) -> bytes:
    return f"{PRODUCTO}:usuarios:{usuario_id}:mfa_secreto".encode()


def cifrar_secreto(usuario_id: int, secreto: str) -> str:
    nonce = secrets.token_bytes(12)
    cifrado = AESGCM(_llave()).encrypt(nonce, secreto.encode(), _contexto(usuario_id))
    return _VERSION_CIFRADO + base64.urlsafe_b64encode(nonce + cifrado).decode()


def descifrar_secreto(usuario_id: int, guardado: str | None) -> str | None:
    """El secreto en claro, o None si no hay o no se puede leer (otra llave,
    otra cuenta o texto sin cifrar: nunca se acepta un secreto en claro)."""
    if not guardado or not guardado.startswith(_VERSION_CIFRADO):
        return None
    try:
        crudo = base64.urlsafe_b64decode(guardado[len(_VERSION_CIFRADO):])
        return AESGCM(_llave()).decrypt(crudo[:12], crudo[12:], _contexto(usuario_id)).decode()
    except (binascii.Error, ValueError, InvalidTag):
        return None


def cifrar_pendientes() -> int:
    """Cifra los secretos que quedaron en claro de versiones anteriores. Lo
    llama la API al arrancar. Devuelve cuantos cifro."""
    _llave()  # al arrancar: crea el archivo la primera vez y avisa si MFA_LLAVE no sirve
    with engine.begin() as conn:
        filas = conn.execute(
            text("SELECT id, mfa_secreto FROM usuarios WHERE mfa_secreto IS NOT NULL "
                 "AND mfa_secreto NOT LIKE 'v1:%' FOR UPDATE")
        ).all()
        for id_, secreto in filas:
            conn.execute(
                text("UPDATE usuarios SET mfa_secreto = :s WHERE id = :i"),
                {"s": cifrar_secreto(id_, secreto), "i": id_},
            )
    return len(filas)


def _secreto_ilegible() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        "No se pudo leer la verificación en dos pasos de tu cuenta: entra con un código de respaldo "
        "o pide a TI que la reinicie",
    )


# ---------------------------------------------------------------- codigos
def _paso_valido(secreto: str, codigo: str, ultimo_paso: int | None) -> int | None:
    """Paso de tiempo (30 s) del codigo si es valido y no se habia usado; None si no."""
    codigo = codigo.strip().replace(" ", "")
    if not (len(codigo) == 6 and codigo.isdigit()):
        return None
    totp = pyotp.TOTP(secreto)
    ahora = int(time.time()) // totp.interval
    for paso in (ahora - 1, ahora, ahora + 1):
        if hmac.compare_digest(totp.generate_otp(paso), codigo) and (ultimo_paso is None or paso > ultimo_paso):
            return paso
    return None


def _normalizar_respaldo(codigo: str) -> str:
    return codigo.strip().lower().replace("-", "").replace(" ", "")


def _hash_respaldo(codigo: str) -> str:
    # 10 caracteres al azar de 31 posibles (~50 bits) y con limite de intentos:
    # un hash rapido basta (no son contrasenas elegidas por personas)
    return hashlib.sha256(_normalizar_respaldo(codigo).encode()).hexdigest()


def _nuevos_respaldos() -> list[str]:
    codigos = []
    for _ in range(CODIGOS_RESPALDO):
        c = "".join(secrets.choice(_ALFABETO_RESPALDO) for _ in range(10))
        codigos.append(f"{c[:5]}-{c[5:]}")
    return codigos


def qr_svg(uri: str) -> str:
    """El QR del otpauth:// como imagen SVG en data URI (para un <img>)."""
    imagen = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    return "data:image/svg+xml;base64," + base64.b64encode(imagen.to_string()).decode()


# ----------------------------------------------------------- configurarlo
def iniciar_configuracion(u: Usuario) -> dict:
    """Genera un secreto nuevo (aun sin activar) y lo devuelve con su QR."""
    seguridad.asegurar_tabla()
    if u.mfa_activo:
        raise MfaInvalido("La verificación en dos pasos ya está activa. Si cambiaste de teléfono, pide a TI que la reinicie")
    secreto = pyotp.random_base32()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE usuarios SET mfa_secreto = :s, mfa_ultimo_paso = NULL WHERE id = :i AND NOT mfa_activo"),
            {"s": cifrar_secreto(u.id, secreto), "i": u.id},
        )
    uri = pyotp.TOTP(secreto).provisioning_uri(name=u.usuario, issuer_name=EMISOR)
    return {"secreto": secreto, "uri": uri, "qr": qr_svg(uri)}


def activar(u: Usuario, codigo: str) -> list[str]:
    """Confirma con un codigo de la app y activa el MFA. Devuelve los codigos de
    respaldo, que no se vuelven a mostrar."""
    seguridad.asegurar_tabla()
    with engine.begin() as conn:
        fila = conn.execute(
            text("SELECT mfa_secreto, mfa_activo FROM usuarios WHERE id = :i FOR UPDATE"), {"i": u.id}
        ).mappings().one()
        if fila["mfa_activo"]:
            raise MfaInvalido("La verificación en dos pasos ya está activa")
        if not fila["mfa_secreto"]:
            raise MfaInvalido("Primero genera el código QR")
        secreto = descifrar_secreto(u.id, fila["mfa_secreto"])
        if secreto is None:
            raise MfaInvalido("No se pudo leer el código QR generado: genera uno nuevo")
        paso = _paso_valido(secreto, codigo, None)
        if paso is None:
            raise MfaInvalido("El código no es correcto. Revisa que la hora de tu teléfono sea la correcta")
        codigos = _nuevos_respaldos()
        conn.execute(
            text("UPDATE usuarios SET mfa_activo = true, mfa_ultimo_paso = :p WHERE id = :i"),
            {"p": paso, "i": u.id},
        )
        conn.execute(text("DELETE FROM codigos_respaldo WHERE usuario_id = :i"), {"i": u.id})
        for c in codigos:
            conn.execute(
                text("INSERT INTO codigos_respaldo (usuario_id, codigo_hash) VALUES (:i, :h)"),
                {"i": u.id, "h": _hash_respaldo(c)},
            )
        seguridad.registrar(conn, u.usuario, "activar_mfa", u.usuario)
    return codigos


def respaldos_restantes(usuario_id: int) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT COUNT(*) FROM codigos_respaldo WHERE usuario_id = :i AND usado_en IS NULL"),
            {"i": usuario_id},
        ).scalar_one()


def reiniciar(usuario_id: int, por: str):
    """TI borra el MFA de una cuenta (telefono perdido): al entrar lo vuelve a
    configurar. Cierra sus sesiones. Nadie reinicia el suyo."""
    seguridad.asegurar_tabla()
    with engine.begin() as conn:
        actual = conn.execute(
            text("SELECT usuario FROM usuarios WHERE id = :i FOR UPDATE"), {"i": usuario_id}
        ).scalar()
        if actual is None:
            raise LookupError(f"El usuario {usuario_id} no existe")
        if actual == por:
            raise ErrorDeUsuario("No puedes reiniciar tu propia verificación en dos pasos: pídeselo a otra persona de TI")
        conn.execute(
            text(
                "UPDATE usuarios SET mfa_secreto = NULL, mfa_activo = false, mfa_ultimo_paso = NULL, "
                "version_sesion = version_sesion + 1 WHERE id = :i"
            ),
            {"i": usuario_id},
        )
        conn.execute(text("DELETE FROM codigos_respaldo WHERE usuario_id = :i"), {"i": usuario_id})
        seguridad.registrar(conn, actual, "reiniciar_mfa", por)


# ---------------------------------------------------------- al entrar
def verificar_entrada(u: Usuario, codigo: str) -> Usuario:
    """Segundo paso del inicio de sesion: codigo de la app o de respaldo.

    401 si no es correcto (y cuenta como intento fallido), 429 si la cuenta
    esta bloqueada. Al acertar se reinicia el contador de fallos."""
    error = None
    with engine.begin() as conn:
        fila = conn.execute(
            text(
                "SELECT id, usuario, mfa_secreto, mfa_activo, mfa_ultimo_paso, bloqueado_hasta "
                "FROM usuarios WHERE id = :i AND activo FOR UPDATE"
            ),
            {"i": u.id},
        ).mappings().first()
        if fila is None or not fila["mfa_activo"]:
            error = HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión no válida o vencida; vuelve a iniciar sesión")
        elif (bloqueo := seguridad.error_si_bloqueada(fila)) is not None:
            error = bloqueo
        elif (secreto := descifrar_secreto(u.id, fila["mfa_secreto"])) is not None and (
            paso := _paso_valido(secreto, codigo, fila["mfa_ultimo_paso"])
        ) is not None:
            conn.execute(text("UPDATE usuarios SET mfa_ultimo_paso = :p WHERE id = :i"), {"p": paso, "i": u.id})
            seguridad.registrar_entrada(conn, u.id)
        elif conn.execute(
            text(
                "UPDATE codigos_respaldo SET usado_en = now() "
                "WHERE usuario_id = :i AND codigo_hash = :h AND usado_en IS NULL RETURNING id"
            ),
            {"i": u.id, "h": _hash_respaldo(codigo)},
        ).first():
            seguridad.registrar_entrada(conn, u.id)
            seguridad.registrar(conn, fila["usuario"], "usar_codigo_respaldo", fila["usuario"])
        else:
            seguridad.registrar_fallo(conn, u.id)
            # con la llave perdida o cambiada, solo sirven los codigos de respaldo
            error = _secreto_ilegible() if secreto is None else HTTPException(
                status.HTTP_401_UNAUTHORIZED, "El código no es correcto"
            )
    if error is not None:
        raise error
    return u
