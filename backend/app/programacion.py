"""Programacion mensual de reportes (paso 10, RF-07).

Cada mes, a partir del dia que configure RRHH, se generan los reportes del
ultimo mes CERRADO con datos (anterior al mes en curso: un mes a medias no se
reporta): el consolidado y cada area con indicadores. Nacen pendientes de
revision y sin solicitante, asi que los puede revisar cualquier persona de
RRHH (regla 10.3.9), y RRHH recibe un aviso conforme cada uno termina.

Quien la dispara (los dos usan revisar(), que es idempotente):
  - La API: al arrancar y despues cada PROGRAMACION_CADA_MINUTOS (60). Si el
    servidor estuvo apagado o dormido el dia programado, se pone al dia en
    cuanto vuelve.
  - scripts/programar.py, para el Programador de tareas de Windows o cron,
    por si la API no esta encendida.
Un mes se genera una sola vez: la tabla corridas_programadas lo garantiza
aunque los dos revisen al mismo tiempo.

En cada revision tambien se avisan los indicadores en rojo de ese mismo mes
cerrado (RF-09) y se mandan los correos pendientes, aunque la programacion
este desactivada.
"""
import logging
import os
import threading
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import text

from app import avisos, narrativa, trabajos
from app.database import ejecutar_sql, engine
from app.kpis import calcular_kpis
from app.llm import ConfiguracionIA, obtener_proveedor
from app.narrativa import MESES_ES

log = logging.getLogger(__name__)

_tabla_lista = False
_parar = threading.Event()
_despertar = threading.Event()  # revisar ya, sin esperar a la siguiente vuelta


def asegurar_tabla():
    global _tabla_lista
    if not _tabla_lista:
        trabajos.asegurar_tabla()  # columna narrativas.programada
        ejecutar_sql("programacion.sql")
        _tabla_lista = True


def hoy() -> date:
    """Fecha de hoy en la zona horaria de la empresa (no la del servidor)."""
    return datetime.now(ZoneInfo(os.getenv("ZONA_HORARIA", "America/Mexico_City"))).date()


def _mes(periodo: pd.Timestamp) -> str:
    return f"{MESES_ES[periodo.month - 1]} {periodo.year}"


# --------------------------------------------------------- configuracion
def leer() -> dict:
    asegurar_tabla()
    with engine.connect() as conn:
        return dict(
            conn.execute(
                text("SELECT activa, dia_del_mes, modificada_por, modificada_en FROM programacion WHERE id = 1")
            ).mappings().one()
        )


def guardar(activa: bool, dia_del_mes: int, usuario: str) -> dict:
    """Cambia la configuracion (solo RRHH; lo exige la API) y registra quien."""
    if not 1 <= dia_del_mes <= 28:
        raise ValueError("El día del mes debe estar entre 1 y 28 (todos los meses lo tienen)")
    asegurar_tabla()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE programacion SET activa = :a, dia_del_mes = :d, modificada_por = :u, "
                "modificada_en = now() WHERE id = 1"
            ),
            {"a": activa, "d": dia_del_mes, "u": usuario},
        )
    return leer()


def corridas(limite: int = 12) -> list[dict]:
    """Meses que ya genero la programacion, del mas reciente al mas antiguo."""
    asegurar_tabla()
    with engine.connect() as conn:
        filas = conn.execute(
            text(
                "SELECT to_char(periodo, 'YYYY-MM') AS periodo, iniciada_en, origen, narrativas "
                "FROM corridas_programadas ORDER BY periodo DESC LIMIT :limite"
            ),
            {"limite": limite},
        ).mappings().all()
    return [dict(f) for f in filas]


# ------------------------------------------------------------- ejecucion
def periodo_objetivo(df: pd.DataFrame, dia: date) -> pd.Timestamp | None:
    """Ultimo mes con datos anterior al mes en curso (None si no hay)."""
    cerrados = df.loc[df["periodo"] < pd.Timestamp(dia.year, dia.month, 1), "periodo"]
    return None if cerrados.empty else cerrados.max()


def _ya_generado(periodo: pd.Timestamp) -> bool:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT 1 FROM corridas_programadas WHERE periodo = :p"), {"p": periodo.date()}
        ).first() is not None


def _generar(periodo: pd.Timestamp, df: pd.DataFrame, origen: str) -> dict:
    try:
        proveedor = obtener_proveedor()
    except ConfiguracionIA as exc:
        avisos.avisar_programacion_fallida(periodo, str(exc))
        return {"mensaje": f"No se generaron los reportes de {_mes(periodo)}: {exc}"}

    with engine.begin() as conn:
        gano = conn.execute(
            text(
                "INSERT INTO corridas_programadas (periodo, origen) VALUES (:p, :o) "
                "ON CONFLICT (periodo) DO NOTHING RETURNING periodo"
            ),
            {"p": periodo.date(), "o": origen},
        ).first()
    if gano is None:  # otro proceso se adelanto
        return {"mensaje": f"Los reportes de {_mes(periodo)} ya se generaron."}

    ids = []
    for area_id in sorted(df.loc[df["periodo"] == periodo, "area_id"].unique()):  # 0 = consolidado, primero
        try:
            narrativa.validar_solicitud(df, periodo, int(area_id))
        except ValueError:
            continue  # sin indicadores con datos: no hay nada que reportar
        ids.append(trabajos.encolar(periodo, int(area_id), proveedor, df, programada=True))
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE corridas_programadas SET narrativas = :n WHERE periodo = :p"),
            {"n": len(ids), "p": periodo.date()},
        )
    log.info("Programacion mensual: %s reportes de %s solicitados", len(ids), _mes(periodo))
    return {
        "periodo": f"{periodo:%Y-%m}",
        "narrativas": ids,
        "mensaje": f"Se solicitaron {len(ids)} reportes de {_mes(periodo)}; quedan pendientes de revisión.",
    }


def revisar(origen: str = "api", dia: date | None = None) -> dict:
    """Avisa alertas nuevas y, si ya toca, genera los reportes del mes.

    Es idempotente: se puede llamar cuantas veces sea. Devuelve que hizo:
    {"alertas": avisos nuevos, "periodo": "AAAA-MM" o None,
     "narrativas": ids solicitados, "mensaje": texto para la persona}."""
    asegurar_tabla()
    dia = dia or hoy()
    df = calcular_kpis()
    objetivo = periodo_objetivo(df, dia)
    alertas = avisos.avisar_alertas(df, objetivo) if objetivo is not None else 0
    resultado = {"alertas": alertas, "periodo": None, "narrativas": []}

    conf = leer()
    if not conf["activa"]:
        resultado["mensaje"] = "La programación mensual está desactivada."
    elif dia.day < conf["dia_del_mes"]:
        resultado["mensaje"] = f"Los reportes se generan a partir del día {conf['dia_del_mes']} de cada mes."
    elif objetivo is None:
        resultado["mensaje"] = "No hay meses cerrados con datos."
    elif _ya_generado(objetivo):
        resultado["mensaje"] = f"Los reportes de {_mes(objetivo)} ya se generaron."
    else:
        resultado.update(_generar(objetivo, df, origen))

    avisos.programar_envio()  # correos que hayan quedado pendientes
    return resultado


# ----------------------------------------------------------- hilo de la API
def iniciar() -> threading.Thread | None:
    """Arranca la revision periodica dentro de la API (PROGRAMACION_EN_API=no la apaga)."""
    if os.getenv("PROGRAMACION_EN_API", "si").strip().lower() == "no":
        return None
    segundos = float(os.getenv("PROGRAMACION_CADA_MINUTOS", "60")) * 60
    _parar.clear()
    hilo = threading.Thread(target=_ciclo, args=(segundos,), daemon=True, name="programacion")
    hilo.start()
    return hilo


def detener():
    _parar.set()
    _despertar.set()


def revisar_pronto():
    """Pide al hilo de la API revisar ya (p. ej. RRHH acaba de activar la
    programacion). Si el hilo no esta corriendo, no hace nada."""
    _despertar.set()


def _ciclo(segundos: float):
    while not _parar.is_set():
        try:
            revisar("api")
        except Exception:  # sin BD, por ejemplo: se reintenta en la siguiente vuelta
            log.exception("La revision de la programacion mensual fallo")
        _despertar.wait(segundos)
        _despertar.clear()
