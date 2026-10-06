"""Avisos dentro de la app y correo opcional sin datos (paso 10, RF-09).

Que se avisa y a quien:
  - Indicadores en rojo del ultimo mes cerrado con datos (lo revisa
    app/programacion.py cada hora): los del consolidado a
    Direccion y RRHH; los de un area a su gerente y a RRHH (regla 10.3.3).
    Un aviso por area con todos sus indicadores en rojo.
  - Reporte listo para revisar: a RRHH, salvo a quien lo solicito (10.3.9).
  - Reporte programado que no se pudo generar: a RRHH.
  - Reporte aprobado: a su audiencia (Direccion si es el consolidado, el
    gerente si es de un area) y a quien lo solicito. Rechazado: a quien lo
    solicito. Nunca a quien lo reviso.

Una fila por persona en la tabla `avisos`. La `clave` evita repetir un
evento: revisar las alertas cada hora no genera avisos nuevos.

Correo (opcional): si el .env tiene SMTP_HOST, a quien tenga correo le llega
UN correo con "tienes N avisos nuevos" y la liga al sistema. Nunca lleva el
titulo del aviso ni cifras: con datos reales, nada de RRHH sale por correo.

Un aviso que falla nunca tumba lo que lo provoco (una revision, una
narrativa): el error queda en el log y ya.
"""
import functools
import logging
import os
import smtplib
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage

import pandas as pd
from sqlalchemy import text

from app import seguridad
from app.database import ejecutar_sql, engine
from app.kpis import CORPORATIVO
from app.marca import PRODUCTO, empresa
from app.narrativa import MESES_ES
from app.seguridad import Usuario

log = logging.getLogger(__name__)

DIAS_PARA_CORREO = 7  # un aviso mas viejo ya no se manda por correo
SEGUNDOS_SMTP = 20
_tabla_lista = False

# Reemplazable en pruebas. Un solo hilo: los correos salen en orden y el
# envio nunca hace esperar a quien provoco el aviso.
ejecutor_correo = ThreadPoolExecutor(max_workers=1, thread_name_prefix="correo")


def asegurar_tabla():
    global _tabla_lista
    if not _tabla_lista:
        seguridad.asegurar_tabla()  # llave foranea a usuarios
        ejecutar_sql("avisos.sql")
        _tabla_lista = True


def _tolerante(fn):
    """Si el aviso falla, se registra en el log y quien avisaba sigue normal."""

    @functools.wraps(fn)
    def envoltura(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            log.exception("No se pudo generar el aviso (%s)", fn.__name__)
            return 0

    return envoltura


def _mes(periodo) -> str:
    p = pd.Timestamp(periodo)
    return f"{MESES_ES[p.month - 1]} {p.year}"


def _nombre_area(conn, area_id: int) -> str:
    if area_id == CORPORATIVO:
        return "Corporativo"
    nombre = conn.execute(text("SELECT nombre FROM areas WHERE id = :a"), {"a": area_id}).scalar()
    return nombre or f"Área {area_id}"


# ---------------------------------------------------------- destinatarios
def _audiencia(conn, area_id: int, con_rrhh: bool) -> set[int]:
    """Personas activas a las que les toca un area: Direccion si es el
    consolidado, su gerente si es un area, y RRHH si se pide."""
    return set(
        conn.execute(
            text(
                "SELECT id FROM usuarios WHERE activo AND ("
                "  (:corp AND rol = 'direccion') OR"
                "  (NOT :corp AND rol = 'gerente' AND area_id = :a) OR"
                "  (:rrhh AND rol = 'rrhh'))"
            ),
            {"corp": area_id == CORPORATIVO, "a": area_id, "rrhh": con_rrhh},
        ).scalars()
    )


def _rrhh(conn) -> set[int]:
    return set(conn.execute(text("SELECT id FROM usuarios WHERE activo AND rol = 'rrhh'")).scalars())


def _ids(conn, *usuarios: str | None) -> set[int]:
    nombres = [u for u in usuarios if u]
    if not nombres:
        return set()
    return set(
        conn.execute(text("SELECT id FROM usuarios WHERE usuario = ANY(:u)"), {"u": nombres}).scalars()
    )


def _crear(conn, destinatarios: set[int], tipo: str, area_id: int, titulo: str, enlace: str, clave: str) -> int:
    creados = 0
    for usuario_id in destinatarios:
        creados += conn.execute(
            text(
                "INSERT INTO avisos (usuario_id, tipo, area_id, titulo, enlace, clave) "
                "VALUES (:u, :t, :a, :ti, :e, :c) ON CONFLICT (usuario_id, clave) DO NOTHING"
            ),
            {"u": usuario_id, "t": tipo, "a": area_id, "ti": titulo, "e": enlace, "c": clave},
        ).rowcount
    return creados


# ---------------------------------------------------------------- eventos
@_tolerante
def avisar_alertas(df: pd.DataFrame, periodo=None) -> int:
    """Avisa de los indicadores en rojo de un mes (por defecto, el ultimo con
    datos). Devuelve cuantos avisos nuevos se crearon.

    La clave incluye que indicadores estan en rojo: si despues se suma otro
    (nuevos datos o un umbral mas estricto), se avisa otra vez con la lista
    completa; si nada cambia, no se repite."""
    asegurar_tabla()
    periodo = pd.Timestamp(periodo) if periodo is not None else df["periodo"].max()
    rojos = df[(df["periodo"] == periodo) & (df["estado"] == "rojo")].sort_values("indicador")
    creados = 0
    with engine.begin() as conn:
        for area_id, grupo in rojos.groupby("area_id"):
            area_id = int(area_id)
            n = len(grupo)
            titulo = (
                f"{grupo['area'].iloc[0]}, {_mes(periodo)}: {n} "
                f"{'indicador' if n == 1 else 'indicadores'} en rojo ({', '.join(grupo['nombre'])})"
            )
            clave = f"alerta:{area_id}:{periodo:%Y-%m}:{','.join(grupo['indicador'])}"
            enlace = f"/tablero?area={area_id}&periodo={periodo:%Y-%m}"
            creados += _crear(conn, _audiencia(conn, area_id, con_rrhh=True), "alerta", area_id, titulo, enlace, clave)
    if creados:
        programar_envio()
    return creados


def _narrativa(conn, id_: int):
    return conn.execute(
        text(
            "SELECT id, area_id, periodo, estado, solicitada_por, programada, revision, revisada_por "
            "FROM narrativas WHERE id = :id"
        ),
        {"id": id_},
    ).mappings().first()


@_tolerante
def avisar_narrativa_terminada(id_: int) -> int:
    """Reporte listo: RRHH lo revisa (salvo quien lo pidio, que no puede).
    Reporte programado con error: RRHH se entera (nadie lo estaba esperando)."""
    asegurar_tabla()
    with engine.begin() as conn:
        t = _narrativa(conn, id_)
        if t is None:
            return 0
        lugar = f"{_nombre_area(conn, t['area_id'])}, {_mes(t['periodo'])}"
        if t["estado"] == "lista":
            tipo, titulo = "revision", f"Reporte de {lugar} listo para revisión"
        elif t["estado"] == "error" and t["programada"]:
            tipo, titulo = "error", f"No se pudo generar el reporte programado de {lugar}"
        else:
            return 0
        destinatarios = _rrhh(conn) - _ids(conn, t["solicitada_por"])
        creados = _crear(conn, destinatarios, tipo, t["area_id"], titulo, f"/narrativas/{id_}", f"{tipo}:{id_}")
    if creados:
        programar_envio()
    return creados


@_tolerante
def avisar_revision(id_: int) -> int:
    """Aprobado: a su audiencia y a quien lo pidio. Rechazado: a quien lo pidio."""
    asegurar_tabla()
    with engine.begin() as conn:
        t = _narrativa(conn, id_)
        if t is None or t["revision"] == "pendiente":
            return 0
        lugar = f"{_nombre_area(conn, t['area_id'])}, {_mes(t['periodo'])}"
        if t["revision"] == "aprobada":
            tipo, titulo = "aprobado", f"Reporte de {lugar} aprobado: ya se puede descargar"
            destinatarios = _audiencia(conn, t["area_id"], con_rrhh=False) | _ids(conn, t["solicitada_por"])
        else:
            tipo, titulo = "rechazado", f"Reporte de {lugar} rechazado: revisa el motivo"
            destinatarios = _ids(conn, t["solicitada_por"])
        destinatarios -= _ids(conn, t["revisada_por"])
        creados = _crear(conn, destinatarios, tipo, t["area_id"], titulo, f"/narrativas/{id_}", f"{tipo}:{id_}")
    if creados:
        programar_envio()
    return creados


@_tolerante
def avisar_programacion_fallida(periodo, motivo: str) -> int:
    """La programacion no pudo arrancar (p. ej. la IA no esta configurada).
    Un solo aviso por mes, aunque se vuelva a intentar cada hora."""
    asegurar_tabla()
    titulo = f"La programación mensual no pudo generar los reportes de {_mes(periodo)}: {motivo}"
    with engine.begin() as conn:
        creados = _crear(
            conn, _rrhh(conn), "error", CORPORATIVO, titulo, "/configuracion",
            f"programacion:{pd.Timestamp(periodo):%Y-%m}",
        )
    if creados:
        programar_envio()
    return creados


# ---------------------------------------------------------------- lectura
def _areas_de(u: Usuario) -> list[int] | None:
    """Areas cuyos avisos puede ver HOY (None = todas). admin_ti no recibe
    avisos: todos hablan de datos de colaboradores."""
    if u.rol == "rrhh":
        return None
    if u.rol == "direccion":
        return [CORPORATIVO]
    if u.rol == "gerente":
        return [u.area_id]
    return []


def listar(u: Usuario, solo_no_leidos: bool = False, limite: int = 50) -> dict:
    """Avisos de la persona, del mas reciente al mas antiguo, y cuantos no ha leido."""
    asegurar_tabla()
    areas = _areas_de(u)
    if areas == []:
        return {"no_leidos": 0, "avisos": []}
    filtros, params = ["usuario_id = :u"], {"u": u.id, "limite": limite}
    if areas is not None:
        filtros.append("area_id = ANY(:a)")
        params["a"] = areas
    donde = " AND ".join(filtros)
    with engine.connect() as conn:
        no_leidos = conn.execute(
            text(f"SELECT COUNT(*) FROM avisos WHERE {donde} AND leido_en IS NULL"), params
        ).scalar_one()
        filas = conn.execute(
            text(
                "SELECT id, tipo, area_id, titulo, enlace, creado_en, leido_en FROM avisos "
                f"WHERE {donde}{' AND leido_en IS NULL' if solo_no_leidos else ''} "
                "ORDER BY id DESC LIMIT :limite"
            ),
            params,
        ).mappings().all()
    return {"no_leidos": no_leidos, "avisos": [dict(f) for f in filas]}


def marcar_leido(u: Usuario, id_: int) -> bool:
    """False si el aviso no existe o es de otra persona."""
    asegurar_tabla()
    with engine.begin() as conn:
        return conn.execute(
            text(
                "UPDATE avisos SET leido_en = COALESCE(leido_en, now()) "
                "WHERE id = :id AND usuario_id = :u RETURNING id"
            ),
            {"id": id_, "u": u.id},
        ).first() is not None


def marcar_todos(u: Usuario) -> int:
    asegurar_tabla()
    with engine.begin() as conn:
        return conn.execute(
            text("UPDATE avisos SET leido_en = now() WHERE usuario_id = :u AND leido_en IS NULL"), {"u": u.id}
        ).rowcount


# ----------------------------------------------------------------- correo
def configuracion_smtp() -> dict | None:
    """Datos del servidor de correo del .env; None si el correo esta apagado."""
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        return None
    usuario = os.getenv("SMTP_USUARIO", "").strip()
    return {
        "host": host,
        "puerto": int(os.getenv("SMTP_PUERTO", "587")),
        "usuario": usuario,
        "contrasena": os.getenv("SMTP_CONTRASENA", ""),
        "remitente": os.getenv("SMTP_REMITENTE", "").strip() or usuario,
        "app_url": os.getenv("APP_URL", "http://localhost:5173").strip().rstrip("/"),
    }


def programar_envio():
    """Manda en segundo plano los correos pendientes (si el correo esta activo)."""
    if configuracion_smtp() is not None:
        ejecutor_correo.submit(enviar_correos)


def contenido_correo(nombre: str, nuevos: int, app_url: str) -> tuple[str, str]:
    """Asunto y cuerpo. SOLO el conteo y la liga: ni titulos, ni areas, ni cifras."""
    avisos = "1 aviso nuevo" if nuevos == 1 else f"{nuevos} avisos nuevos"
    asunto = f"{PRODUCTO}: tienes {avisos}"
    cuerpo = (
        f"Hola, {nombre}:\n\n"
        f"Tienes {avisos} en {PRODUCTO} ({empresa()}).\n"
        f"Entra para verlos: {app_url}/avisos\n\n"
        "Por seguridad, este correo no incluye datos: el detalle solo se ve dentro del sistema, "
        "con tu usuario y contraseña.\n"
    )
    return asunto, cuerpo


def _enviar(conf: dict, destinatario: str, asunto: str, cuerpo: str):
    mensaje = EmailMessage()
    mensaje["From"] = conf["remitente"]
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(cuerpo)
    if conf["puerto"] == 465:
        servidor = smtplib.SMTP_SSL(conf["host"], 465, timeout=SEGUNDOS_SMTP)
    else:
        servidor = smtplib.SMTP(conf["host"], conf["puerto"], timeout=SEGUNDOS_SMTP)
    with servidor:
        if conf["puerto"] != 465:
            servidor.ehlo()
            if servidor.has_extn("starttls"):
                servidor.starttls()
                servidor.ehlo()
            elif conf["usuario"] and conf["host"] not in ("localhost", "127.0.0.1"):
                # nunca mandar la contrasena sin cifrar fuera de este equipo
                raise smtplib.SMTPException(f"{conf['host']} no ofrece STARTTLS; no se envía la contraseña sin cifrar")
        if conf["usuario"]:
            servidor.login(conf["usuario"], conf["contrasena"])
        servidor.send_message(mensaje)


def enviar_correos() -> int:
    """Un correo por persona con avisos nuevos que aun no se le avisaron por
    correo. Devuelve cuantos correos salieron. Si uno falla, sus avisos
    quedan pendientes para el siguiente intento."""
    conf = configuracion_smtp()
    if conf is None:
        return 0
    asegurar_tabla()
    pendientes_sql = (
        "a.usuario_id = u.id AND a.leido_en IS NULL AND a.correo_enviado_en IS NULL "
        "AND a.creado_en > now() - make_interval(days => :dias)"
    )
    with engine.connect() as conn:
        personas = conn.execute(
            text(
                "SELECT u.id, u.nombre, u.correo FROM usuarios u WHERE u.activo AND u.correo IS NOT NULL "
                f"AND EXISTS (SELECT 1 FROM avisos a WHERE {pendientes_sql})"
            ),
            {"dias": DIAS_PARA_CORREO},
        ).mappings().all()
    enviados = 0
    for p in personas:
        # se apartan antes de enviar: dos envios a la vez no mandan el mismo aviso
        with engine.begin() as conn:
            ids = conn.execute(
                text(
                    "UPDATE avisos a SET correo_enviado_en = now() FROM usuarios u "
                    f"WHERE u.id = :u AND {pendientes_sql} RETURNING a.id"
                ),
                {"u": p["id"], "dias": DIAS_PARA_CORREO},
            ).scalars().all()
        if not ids:
            continue
        try:
            _enviar(conf, p["correo"], *contenido_correo(p["nombre"], len(ids), conf["app_url"]))
        except (smtplib.SMTPException, OSError) as exc:
            log.warning("No se pudo enviar el correo de avisos a %s: %s", p["correo"], exc)
            with engine.begin() as conn:
                conn.execute(text("UPDATE avisos SET correo_enviado_en = NULL WHERE id = ANY(:ids)"), {"ids": ids})
            continue
        enviados += 1
    return enviados
