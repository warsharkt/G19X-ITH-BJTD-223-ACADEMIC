"""Modo demostracion para quien prueba o revisa el proyecto.

Se activa con MODO_DEMO=si y SOLO funciona con MODO_DATOS=sinteticos: con
datos reales queda apagado, igual que el candado de la IA en la nube.

El sistema se ve como en produccion: la pantalla de inicio no lista cuentas
ni contrasenas, y las cuentas son las del personal de la empresa (usuario
nombre.apellido); sus datos de acceso estan en el README. Las medidas de
seguridad funcionan igual (contrasena, verificacion en dos pasos obligatoria,
bloqueo por intentos, permisos por rol, bitacoras). Lo unico que agrega es un
telefono simulado que, al configurar el MFA o al entrar, muestra el codigo
vigente que en produccion solo se veria en la app del telefono. Solo para las
cuentas de CUENTAS: nunca revela el codigo de ninguna otra cuenta.
"""
import os
import time

import pyotp
from sqlalchemy import text

from app import mfa, seguridad
from app.database import engine
from app.llm import ConfiguracionIA, modo_datos
from app.seguridad import ErrorDeUsuario

# usuario, nombre, rol, area (solo gerente), firma reportes, cargo, que hace.
# En el orden del flujo: quien prepara, quien firma, quienes reciben.
CUENTAS = [
    ("eva.munoz", "Eva Muñoz", "rrhh", None, False, "Analista de RRHH",
     "Carga los datos del mes y genera los reportes con IA."),
    ("ana.rios", "Ana Ríos", "rrhh", None, True, "Responsable de RRHH",
     "Revisa y firma los reportes antes de que lleguen a Dirección."),
    ("andrea.salinas", "Andrea Salinas", "direccion", None, False, "Dirección General",
     "Recibe el consolidado firmado; puede pedir reportes a RRHH."),
    ("luis.ortega", "Luis Ortega", "gerente", "Ventas", False, "Gerente de Ventas",
     "Ve solo su área y recibe su reporte firmado."),
    ("carlos.pena", "Carlos Peña", "admin_ti", None, False, "Soporte TI",
     "Administra las cuentas sin ver datos de colaboradores."),
]
USUARIOS = frozenset(c[0] for c in CUENTAS)

# Hasta la v2.13 las cuentas se llamaban demo_*. Al prepararlas se renombran
# para que el historial (reportes, cargas, bitacoras) quede con el nombre
# nuevo; las demo_* que no estan aqui se desactivan.
ANTERIORES = {
    "demo_analista": "eva.munoz",
    "demo_rrhh": "ana.rios",
    "demo_direccion": "andrea.salinas",
    "demo_gerente": "luis.ortega",
    "demo_ti": "carlos.pena",
}

# Columnas que guardan un nombre de usuario como texto (sin llave foranea,
# para que la bitacora sobreviva a la cuenta). Las que aun no existen se saltan.
_REFERENCIAS = [
    ("usuarios_cambios", "usuario"), ("usuarios_cambios", "hecho_por"),
    ("narrativas", "solicitada_por"), ("narrativas", "revisada_por"),
    ("exportaciones", "usuario"), ("cargas", "subida_por"), ("cargas", "aplicada_por"),
    ("programacion", "modificada_por"), ("umbrales_cambios", "usuario"),
    ("suplencias", "suplente"), ("suplencias", "titular"), ("suplencias", "cancelada_por"),
    ("pedidos_reporte", "pedido_por"),
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
    return os.getenv("DEMO_CONTRASENA", "Nordika-2026")


def _renombrar(conn, anterior: str, nuevo: str, por: str):
    """Cambia el nombre de usuario en la cuenta y en todo el historial."""
    columnas = set(
        conn.execute(
            text(
                "SELECT table_name || '.' || column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema()"
            )
        ).scalars()
    )
    conn.execute(text("UPDATE usuarios SET usuario = :n WHERE usuario = :a"), {"n": nuevo, "a": anterior})
    for tabla, columna in _REFERENCIAS:
        if f"{tabla}.{columna}" in columnas:
            conn.execute(text(f"UPDATE {tabla} SET {columna} = :n WHERE {columna} = :a"), {"n": nuevo, "a": anterior})
    seguridad.registrar(conn, nuevo, "modificar", por, {"usuario": [anterior, nuevo]})


def preparar_cuentas(por: str) -> list[str]:
    """Crea las cuentas de demostracion o las deja como nuevas: contrasena de
    demostracion, activas, desbloqueadas y SIN MFA (asi quien revisa ve como se
    configura). Renombra las demo_* de versiones anteriores y desactiva las que
    sobran. Tambien termina las suplencias abiertas de estas cuentas. Todo
    queda en la bitacora de cuentas. Devuelve que hizo."""
    if (motivo := motivo_inactivo()) is not None:
        raise ErrorDeUsuario(motivo)
    seguridad.asegurar_tabla()
    hecho = []
    with engine.begin() as conn:
        areas = dict(conn.execute(text("SELECT nombre, id FROM areas")).all())
        actuales = set(conn.execute(text("SELECT usuario FROM usuarios")).scalars())
        for anterior, nuevo in ANTERIORES.items():
            if anterior in actuales and nuevo not in actuales:
                _renombrar(conn, anterior, nuevo, por)
                hecho.append(f"{anterior}: ahora es {nuevo}")
    with engine.connect() as conn:
        sobrantes = conn.execute(text("SELECT usuario, id FROM usuarios WHERE usuario LIKE 'demo\\_%' AND activo")).all()
        existentes = dict(
            conn.execute(text("SELECT usuario, id FROM usuarios WHERE usuario = ANY(:u)"), {"u": list(USUARIOS)}).all()
        )
    for usuario, id_ in sobrantes:
        seguridad.modificar_usuario(id_, {"activo": False, "firma_reportes": False}, por)
        hecho.append(f"{usuario}: desactivada (ya no se usa)")
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE suplencias SET cancelada_por = :p, cancelada_en = now() "
                "WHERE cancelada_en IS NULL AND suplente = ANY(:u)"
            ),
            {"p": por, "u": list(USUARIOS)},
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
    if fila is None or fila["usuario"] not in USUARIOS:
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
