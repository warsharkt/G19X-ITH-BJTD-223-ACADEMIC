"""Quien firma los reportes (regla 10.3.9).

Dentro de RRHH, quien prepara no firma:
  - La Analista de RRHH carga los datos y genera los reportes.
  - La Responsable de RRHH (usuarios.firma_reportes) los aprueba o rechaza.

Suplencia: mientras la Responsable no esta (vacaciones, incapacidad), designa
a una Analista que firma en su lugar hasta una fecha. La Responsable puede
seguir firmando durante la suplencia. Nadie firma lo que pidio: si la
suplente preparo un reporte, lo firma la Responsable.

Cada reporte dice desde que se solicita quien lo va a firmar, para que
quien lo prepara sepa a quien se lo esta mandando.
"""
from datetime import date, timedelta

from sqlalchemy import text

from app import seguridad
from app.database import engine
from app.seguridad import ErrorDeUsuario, Usuario

CARGO_RESPONSABLE = "Responsable de RRHH"
CARGO_ANALISTA = "Analista de RRHH"
DIAS_MAXIMOS_SUPLENCIA = 90

MESES_CORTOS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _fecha(d: date) -> str:
    return f"{d.day} {MESES_CORTOS[d.month - 1]} {d.year}"


def _responsables(conn) -> list[dict]:
    filas = conn.execute(
        text(
            "SELECT usuario, nombre FROM usuarios "
            "WHERE activo AND rol = 'rrhh' AND firma_reportes ORDER BY id"
        )
    ).mappings().all()
    return [dict(f) for f in filas]


def _suplencia_vigente(conn, hoy: date | None = None) -> dict | None:
    """La suplencia de hoy, si la hay y la suplente sigue activa en RRHH."""
    fila = conn.execute(
        text(
            "SELECT s.id, s.suplente, u.nombre AS nombre_suplente, s.titular, "
            "  COALESCE(t.nombre, s.titular) AS nombre_titular, s.desde, s.hasta, s.motivo "
            "FROM suplencias s "
            "JOIN usuarios u ON u.usuario = s.suplente AND u.activo AND u.rol = 'rrhh' "
            "LEFT JOIN usuarios t ON t.usuario = s.titular "
            "WHERE s.cancelada_en IS NULL AND :hoy BETWEEN s.desde AND s.hasta "
            "ORDER BY s.id DESC LIMIT 1"
        ),
        {"hoy": hoy or date.today()},
    ).mappings().first()
    return dict(fila) if fila else None


def _firmantes(conn, solicitante: str | None) -> tuple[set[str], dict | None]:
    """(quienes pueden firmar, a quien se le manda) un reporte que pidio
    `solicitante`. Se le manda a la suplente si la hay: la Responsable no esta."""
    responsables = _responsables(conn)
    suplencia = _suplencia_vigente(conn)
    pueden = {r["usuario"] for r in responsables}
    if suplencia:
        pueden.add(suplencia["suplente"])
    pueden.discard(solicitante)

    designado = None
    if suplencia and suplencia["suplente"] != solicitante:
        designado = {
            "usuario": suplencia["suplente"],
            "nombre": suplencia["nombre_suplente"],
            "cargo": f"Suplente de {suplencia['nombre_titular']} hasta el {_fecha(suplencia['hasta'])}",
        }
    else:
        for r in responsables:
            if r["usuario"] != solicitante:
                designado = {**r, "cargo": CARGO_RESPONSABLE}
                break
    return pueden, designado


def pueden_firmar(conn, solicitante: str | None) -> set[str]:
    return _firmantes(conn, solicitante)[0]


def designado(conn, solicitante: str | None) -> dict | None:
    """{usuario, nombre, cargo} de quien va a firmar; None si no hay nadie
    (no hay Responsable activa, o la unica que firma es quien lo pidio)."""
    return _firmantes(conn, solicitante)[1]


def nombre_de(conn, usuario: str | None) -> str | None:
    if not usuario:
        return None
    return conn.execute(text("SELECT nombre FROM usuarios WHERE usuario = :u"), {"u": usuario}).scalar() or usuario


# --------------------------------------------------------------- suplencia
def estado(u: Usuario) -> dict:
    """Quien firma hoy. A la Responsable tambien le dice a quien puede
    designar como suplente (las Analistas activas)."""
    seguridad.asegurar_tabla()
    with engine.connect() as conn:
        candidatas = []
        if u.es_responsable:
            candidatas = [
                dict(f)
                for f in conn.execute(
                    text(
                        "SELECT usuario, nombre FROM usuarios "
                        "WHERE activo AND rol = 'rrhh' AND NOT firma_reportes ORDER BY nombre"
                    )
                ).mappings()
            ]
        return {
            "responsables": _responsables(conn),
            "suplencia": _suplencia_vigente(conn),
            "candidatas": candidatas,
            "puede_designar": u.es_responsable,
        }


def designar_suplente(titular: Usuario, suplente: str, hasta: date, motivo: str | None) -> dict:
    """La Responsable designa a una Analista que firma en su lugar desde hoy
    hasta `hasta`. Una sola suplencia a la vez. Queda en la bitacora de cuentas."""
    if not titular.es_responsable:
        raise ErrorDeUsuario("Solo la Responsable de RRHH designa a su suplente")
    hoy = date.today()
    if hasta < hoy:
        raise ErrorDeUsuario("La fecha final no puede ser anterior a hoy")
    if hasta > hoy + timedelta(days=DIAS_MAXIMOS_SUPLENCIA):
        raise ErrorDeUsuario(f"Una suplencia dura como máximo {DIAS_MAXIMOS_SUPLENCIA} días")
    motivo = (motivo or "").strip() or None
    seguridad.asegurar_tabla()
    with engine.begin() as conn:
        persona = conn.execute(
            text("SELECT rol, firma_reportes, activo FROM usuarios WHERE usuario = :u"), {"u": suplente}
        ).mappings().first()
        if persona is None or not persona["activo"] or persona["rol"] != "rrhh" or persona["firma_reportes"]:
            raise ErrorDeUsuario("La suplente debe ser una Analista de RRHH con cuenta activa")
        ya = conn.execute(
            text("SELECT 1 FROM suplencias WHERE cancelada_en IS NULL AND hasta >= :hoy"), {"hoy": hoy}
        ).first()
        if ya:
            raise ErrorDeUsuario("Ya hay una suplencia vigente: termínala antes de designar otra")
        conn.execute(
            text(
                "INSERT INTO suplencias (suplente, titular, desde, hasta, motivo) "
                "VALUES (:s, :t, :d, :h, :m)"
            ),
            {"s": suplente, "t": titular.usuario, "d": hoy, "h": hasta, "m": motivo},
        )
        seguridad.registrar(conn, suplente, "designar_suplente", titular.usuario,
                            {"desde": hoy, "hasta": hasta, "motivo": motivo})
    return estado(titular)


def terminar_suplencia(titular: Usuario) -> dict:
    """La Responsable regresa antes: la suplencia termina hoy."""
    if not titular.es_responsable:
        raise ErrorDeUsuario("Solo la Responsable de RRHH termina la suplencia")
    seguridad.asegurar_tabla()
    with engine.begin() as conn:
        fila = conn.execute(
            text(
                "UPDATE suplencias SET cancelada_por = :p, cancelada_en = now() "
                "WHERE cancelada_en IS NULL AND hasta >= :hoy RETURNING suplente"
            ),
            {"p": titular.usuario, "hoy": date.today()},
        ).first()
        if fila is None:
            raise ErrorDeUsuario("No hay ninguna suplencia vigente")
        seguridad.registrar(conn, fila[0], "terminar_suplencia", titular.usuario)
    return estado(titular)


def cargo_al_firmar(conn, usuario: str) -> str:
    """Con que cargo firma hoy esa persona (se guarda en la narrativa)."""
    if usuario in {r["usuario"] for r in _responsables(conn)}:
        return CARGO_RESPONSABLE
    suplencia = _suplencia_vigente(conn)
    if suplencia and suplencia["suplente"] == usuario:
        return f"Suplente de {suplencia['nombre_titular']}"
    return CARGO_RESPONSABLE
