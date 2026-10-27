"""Modo demostracion para quien prueba o revisa el proyecto.

Se activa con MODO_DEMO=si y SOLO funciona con MODO_DATOS=sinteticos: con
datos reales queda apagado, igual que el candado de la IA en la nube.

Sirve para que quien ve la demostracion entienda el producto sin configurar
nada: la pantalla de inicio muestra una tarjeta por rol y se entra con un
clic, sin contrasena ni verificacion en dos pasos, y desde el menu se cambia
de rol para recorrer el flujo completo (la Analista prepara, la Responsable
firma, Direccion recibe). La pantalla avisa que en produccion se pide la
verificacion en dos pasos.

Lo que NO cambia: las cuentas reales siempre entran con contrasena y MFA,
los permisos por rol y las bitacoras funcionan igual, y la entrada de un clic
solo sirve para cuentas con prefijo demo_ mientras el modo siga activo (el
token deja de valer si se apaga). Quien quiera ver el MFA puede entrar con
usuario y contrasena: el telefono simulado muestra el codigo vigente, tambien
solo para cuentas demo_.
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

# usuario, nombre, rol, area (solo gerente), firma reportes, cargo, que hace.
# En el orden del flujo: quien prepara, quien firma, quienes reciben.
CUENTAS = [
    ("demo_analista", "Eva Muñoz", "rrhh", None, False, "Analista de RRHH",
     "Carga los datos del mes y genera los reportes con IA."),
    ("demo_rrhh", "Ana Ríos", "rrhh", None, True, "Responsable de RRHH",
     "Revisa y firma los reportes antes de que lleguen a Dirección."),
    ("demo_direccion", "Andrea Salinas", "direccion", None, False, "Dirección General",
     "Recibe el consolidado firmado; puede pedir reportes a RRHH."),
    ("demo_gerente", "Luis Ortega", "gerente", "Ventas", False, "Gerente de Ventas",
     "Ve solo su área y recibe su reporte firmado."),
    ("demo_ti", "Carlos Peña", "admin_ti", None, False, "Soporte TI",
     "Administra las cuentas sin ver datos de colaboradores."),
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
        {"usuario": u, "nombre": n, "rol": r, "cargo": c, "descripcion": d}
        for u, n, r, _area, _firma, c, d in CUENTAS
    ]


def preparar_cuentas(por: str) -> list[str]:
    """Crea las cuentas de demostracion o las deja como nuevas: contrasena de
    demostracion, activas, desbloqueadas y SIN MFA (asi quien revisa ve como se
    configura). Las cuentas demo_ que ya no estan en la lista se desactivan.
    Tambien termina cualquier suplencia abierta. Todo queda en la bitacora de
    cuentas. Devuelve que hizo."""
    if (motivo := motivo_inactivo()) is not None:
        raise ErrorDeUsuario(motivo)
    seguridad.asegurar_tabla()
    hecho = []
    with engine.connect() as conn:
        areas = dict(conn.execute(text("SELECT nombre, id FROM areas")).all())
        existentes = dict(
            conn.execute(text("SELECT usuario, id FROM usuarios WHERE usuario LIKE 'demo\\_%'")).all()
        )
    vigentes = {c[0] for c in CUENTAS}
    for usuario, id_ in existentes.items():
        if usuario not in vigentes:
            seguridad.modificar_usuario(id_, {"activo": False, "firma_reportes": False}, por)
            hecho.append(f"{usuario}: desactivada (ya no se usa)")
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE suplencias SET cancelada_por = :p, cancelada_en = now() "
                "WHERE cancelada_en IS NULL AND suplente LIKE 'demo\\_%'"
            ),
            {"p": por},
        )
    for usuario, nombre, rol, area, firma, _cargo, _ in CUENTAS:
        area_id = areas[area] if area else None
        if usuario not in existentes:
            seguridad.crear_usuario(usuario, nombre, rol, contrasena(), area_id, por=por, firma_reportes=firma)
            hecho.append(f"{usuario}: creada")
            continue
        id_ = existentes[usuario]
        seguridad.modificar_usuario(
            id_, {"nombre": nombre, "rol": rol, "area_id": area_id, "activo": True, "firma_reportes": firma}, por
        )
        seguridad.cambiar_contrasena(usuario, contrasena(), por=por)
        if seguridad.obtener_cuenta(id_)["mfa_activo"]:
            mfa.reiniciar(id_, por)
        with engine.begin() as conn:  # un MFA a medio configurar tambien se borra
            conn.execute(text("UPDATE usuarios SET mfa_secreto = NULL WHERE id = :i AND NOT mfa_activo"), {"i": id_})
        hecho.append(f"{usuario}: restablecida")
    return hecho


def entrar(usuario: str) -> seguridad.Usuario:
    """Cuenta de demostracion para entrar con un clic. LookupError si el modo
    demo esta apagado o la cuenta no es de demostracion o no esta activa."""
    if not activo():
        raise LookupError("El modo demostración no está activo")
    usuario = usuario.strip().lower()
    if usuario not in {c[0] for c in CUENTAS}:
        raise LookupError("Solo las cuentas de demostración entran con un clic")
    seguridad.asegurar_tabla()
    with engine.begin() as conn:
        id_ = conn.execute(
            text("SELECT id FROM usuarios WHERE usuario = :u AND activo"), {"u": usuario}
        ).scalar()
        if id_ is None:
            raise LookupError("La cuenta de demostración no existe: corre python -m scripts.demo")
        seguridad.registrar_entrada(conn, id_)
    return seguridad._leer_usuario(id_)


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
