"""Modo demostracion para quien prueba o revisa el proyecto.

Se activa con MODO_DEMO=si y SOLO funciona con MODO_DATOS=sinteticos: con
datos reales queda apagado, igual que el candado de la IA en la nube.

Las medidas de seguridad funcionan igual que en produccion (contrasena,
verificacion en dos pasos obligatoria, bloqueo por intentos, permisos por rol,
bitacoras). Lo unico que agrega es ayuda para recorrerlas sin telefono:
  - La pantalla de inicio lista cuentas de demostracion de cada rol y su
    contrasena (scripts/demo.py las crea o restablece).
  - Al configurar el MFA o al entrar, muestra el codigo vigente que en
    produccion solo se veria en la app del telefono. Solo para cuentas con
    prefijo demo_: nunca revela el codigo de una cuenta real.
"""
import os
import time

import pyotp
from sqlalchemy import text

from app import mfa, seguridad
from app.database import engine
from app.llm import ConfiguracionIA, modo_datos
from app.seguridad import ErrorDeUsuario

PREFIJO = "demo_"

# usuario, nombre, rol, area (solo gerente), para que sirve en la revision
CUENTAS = [
    ("demo_direccion", "Andrea Salinas", "direccion", None,
     "Dirección General: solo el consolidado de la empresa."),
    ("demo_rrhh", "Ana Ríos", "rrhh", None,
     "Gerente de RRHH: todas las áreas; carga datos y solicita reportes."),
    ("demo_rrhh2", "Eva Muñoz", "rrhh", None,
     "Analista de RRHH: aprueba los reportes que solicitó Ana."),
    ("demo_gerente", "Luis Ortega", "gerente", "Ventas",
     "Gerente de Ventas: solo su área; la verificación en dos pasos es opcional."),
    ("demo_ti", "Carlos Peña", "admin_ti", None,
     "Soporte TI: administra cuentas; no ve datos de colaboradores."),
]


def motivo_inactivo() -> str | None:
    """None si el modo demo esta activo; si no, por que."""
    if os.getenv("MODO_DEMO", "no").strip().lower() != "si":
        return "MODO_DEMO no está activado"
    try:
        if modo_datos() != "sinteticos":
            return "El modo demostración solo funciona con MODO_DATOS=sinteticos (nunca con datos reales)"
    except ConfiguracionIA as exc:
        return str(exc)
    return None


def activo() -> bool:
    return motivo_inactivo() is None


def contrasena() -> str:
    return os.getenv("DEMO_CONTRASENA", "Demo-RRHH-2026")


def cuentas_publicas() -> list[dict]:
    return [
        {"usuario": u, "nombre": n, "rol": r, "descripcion": d}
        for u, n, r, _area, d in CUENTAS
    ]


def preparar_cuentas(por: str) -> list[str]:
    """Crea las cuentas de demostracion o las deja como nuevas: contrasena de
    demostracion, activas, desbloqueadas y SIN MFA (asi quien revisa ve como se
    configura). Todo queda en la bitacora de cuentas. Devuelve que hizo."""
    if (motivo := motivo_inactivo()) is not None:
        raise ErrorDeUsuario(motivo)
    seguridad.asegurar_tabla()
    hecho = []
    with engine.connect() as conn:
        areas = dict(conn.execute(text("SELECT nombre, id FROM areas")).all())
        existentes = dict(
            conn.execute(text("SELECT usuario, id FROM usuarios WHERE usuario LIKE 'demo\\_%'")).all()
        )
    for usuario, nombre, rol, area, _ in CUENTAS:
        area_id = areas[area] if area else None
        if usuario not in existentes:
            seguridad.crear_usuario(usuario, nombre, rol, contrasena(), area_id, por=por)
            hecho.append(f"{usuario}: creada")
            continue
        id_ = existentes[usuario]
        seguridad.modificar_usuario(id_, {"nombre": nombre, "rol": rol, "area_id": area_id, "activo": True}, por)
        seguridad.cambiar_contrasena(usuario, contrasena(), por=por)
        if seguridad.obtener_cuenta(id_)["mfa_activo"]:
            mfa.reiniciar(id_, por)
        with engine.begin() as conn:  # un MFA a medio configurar tambien se borra
            conn.execute(text("UPDATE usuarios SET mfa_secreto = NULL WHERE id = :i AND NOT mfa_activo"), {"i": id_})
        hecho.append(f"{usuario}: restablecida")
    return hecho


def codigo_vigente(usuario_id: int) -> dict:
    """El codigo que en este momento mostraria la app del telefono.

    Si el codigo actual ya se uso (el MFA solo acepta cada codigo una vez), da
    el siguiente, que el servidor ya acepta. LookupError si no aplica: modo
    demo apagado, cuenta que no es de demostracion o sin MFA por configurar."""
    if not activo():
        raise LookupError("El modo demostración no está activo")
    with engine.connect() as conn:
        fila = conn.execute(
            text("SELECT usuario, mfa_secreto, mfa_ultimo_paso FROM usuarios WHERE id = :i AND activo"),
            {"i": usuario_id},
        ).mappings().first()
    if fila is None or not fila["usuario"].startswith(PREFIJO):
        raise LookupError("Solo las cuentas de demostración muestran su código")
    if not fila["mfa_secreto"]:
        raise LookupError("Esta cuenta aún no tiene un código QR generado")
    totp = pyotp.TOTP(fila["mfa_secreto"])
    ahora = time.time()
    paso = int(ahora) // totp.interval
    if fila["mfa_ultimo_paso"] is not None and paso <= fila["mfa_ultimo_paso"]:
        paso = fila["mfa_ultimo_paso"] + 1
    return {
        "codigo": totp.generate_otp(paso),
        "segundos": max(1, int((paso + 1) * totp.interval - ahora)),
    }
