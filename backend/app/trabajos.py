"""Generacion de narrativas en segundo plano (RF-07).

En CPU el modelo tarda minutos por reporte: la API no hace esperar al
usuario. Registra la solicitud en la tabla `narrativas` como "en_proceso",
responde de inmediato con su id y un solo hilo de trabajo la redacta
(uno a la vez: un modelo local en CPU no gana nada con peticiones en
paralelo, solo se vuelven todas mas lentas).

Si el modelo responde pero no pasa los guardarrailes, se pide de nuevo desde
cero (hasta NARRATIVA_RONDAS veces en total). Si no esta disponible, no se
insiste: queda en "error" con el motivo para que RRHH lo vea. Los motivos de
cada rechazo se guardan aunque una ronda posterior salga bien (bitacora y
metrica de "correctos al primer intento").

Cada reporte dice quien lo va a firmar (app/firmas.py) y, ya revisado,
quien lo firmo y con que cargo.

Al terminar, y al revisarla, se avisa a quien corresponde (app/avisos.py).
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from sqlalchemy import text

from app import avisos, firmas, schemas
from app.origen import actual as origen_de_la_peticion
from app.database import engine, ejecutar_sql
from app.narrativa import INTENTOS, NarrativaNoGenerada, generar_narrativa

RONDAS = int(os.getenv("NARRATIVA_RONDAS", "2"))
# Reportes en espera a partir de los cuales ya no se aceptan pedidos a mano. En
# CPU cada uno tarda minutos y van de uno en uno: sin tope, los programados del
# mes esperarian detras. Los programados siempre entran.
COLA_MAXIMA = 20

# Reemplazable en pruebas por un ejecutor que corre la tarea en el momento.
ejecutor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="narrativa")
_tabla_lista = False

_COLUMNAS = (
    "id, area_id, to_char(periodo, 'YYYY-MM') AS periodo, estado, solicitada_en, terminada_en, "
    "proveedor, modelo, version_prompt, rondas, error, detalle_error, solicitada_por, "
    "revision, revisada_por, revisada_en, comentario_revision, programada, nota_rrhh, firmada_como, "
    # Un solo hilo genera los reportes, en orden: los que estan en proceso con
    # id menor van antes (incluido el que se esta generando).
    "CASE WHEN estado = 'en_proceso' THEN (SELECT COUNT(*) FROM narrativas n2 "
    "  WHERE n2.estado = 'en_proceso' AND n2.id < narrativas.id) END AS antes_en_cola"
)


class SolicitudRechazada(Exception):
    """No se acepta la solicitud; `estado` es el codigo HTTP."""

    def __init__(self, mensaje: str, estado: int):
        super().__init__(mensaje)
        self.estado = estado


def asegurar_tabla():
    """Crea la tabla `narrativas` si no existe (idempotente, una vez por proceso)."""
    global _tabla_lista
    if _tabla_lista:
        return
    ejecutar_sql("narrativas.sql")
    _tabla_lista = True


def marcar_interrumpidas() -> int:
    """Al arrancar la API: lo que quedo "en_proceso" murio con el proceso anterior."""
    asegurar_tabla()
    with engine.begin() as conn:
        return conn.execute(
            text(
                "UPDATE narrativas SET estado = 'error', terminada_en = now(), "
                "error = 'Interrumpida: el servidor se reinició mientras se generaba. Solicítala de nuevo.' "
                "WHERE estado = 'en_proceso'"
            )
        ).rowcount


def encolar(
    periodo: pd.Timestamp,
    area_id: int,
    proveedor,
    df: pd.DataFrame,
    solicitante: str | None = None,
    programada: bool = False,
) -> int:
    """Registra la solicitud (con quien la pidio, o programada = la pidio la
    programacion mensual) y la manda al hilo de trabajo. Devuelve su id.

    Una solicitud a mano se rechaza (SolicitudRechazada) si ese mismo reporte
    ya esta en camino o si la cola esta llena."""
    asegurar_tabla()
    with engine.begin() as conn:
        if not programada:
            _revisar_cola(conn, periodo, area_id)
        id_ = conn.execute(
            text(
                "INSERT INTO narrativas (area_id, periodo, proveedor, modelo, solicitada_por, programada) "
                "VALUES (:a, :p, :prov, :mod, :sol, :prog) RETURNING id"
            ),
            {"a": area_id, "p": periodo.date(), "prov": proveedor.nombre, "mod": proveedor.modelo,
             "sol": solicitante, "prog": programada},
        ).scalar_one()
    ejecutor.submit(_ejecutar, id_, periodo, area_id, proveedor, df)
    return id_


def _revisar_cola(conn, periodo: pd.Timestamp, area_id: int):
    # de uno en uno: dos clics seguidos no pasan los dos por esta revision
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('narrativas:cola'))"))
    igual, en_cola = conn.execute(
        text(
            "SELECT MIN(id) FILTER (WHERE area_id = :a AND periodo = :p), COUNT(*) "
            "FROM narrativas WHERE estado = 'en_proceso'"
        ),
        {"a": area_id, "p": periodo.date()},
    ).one()
    if igual is not None:
        raise SolicitudRechazada(f"Este reporte ya se está generando (número {igual}): espera a que termine", 409)
    if en_cola >= COLA_MAXIMA:
        raise SolicitudRechazada(f"Hay {en_cola} reportes en espera: inténtalo cuando avance la cola", 429)


def _ejecutar(id_: int, periodo, area_id, proveedor, df):
    detalle, motivo = [], "Error inesperado"
    for ronda in range(1, RONDAS + 1):
        _actualizar(id_, rondas=ronda)
        try:
            n = generar_narrativa(periodo, area_id, proveedor=proveedor, df=df)
        except NarrativaNoGenerada as exc:
            motivo = exc.motivo
            detalle += [f"Ronda {ronda}: {d}" for d in exc.detalle] or [f"Ronda {ronda}: {exc.motivo}"]
            if not exc.reintentable:
                break
            continue
        except Exception as exc:  # que un fallo inesperado no deje la fila "en_proceso" para siempre
            motivo, detalle = f"Error inesperado: {exc}", detalle + [repr(exc)]
            break
        # Los rechazos de rondas anteriores tambien cuentan: cada ronda fallida
        # agoto sus INTENTOS llamadas al modelo.
        n["advertencias"] = detalle + n["advertencias"]
        n["intentos"] += (ronda - 1) * INTENTOS
        resultado = schemas.Narrativa(**n).model_dump(mode="json")
        _actualizar(
            id_, estado="lista", resultado=json.dumps(resultado, ensure_ascii=False),
            version_prompt=n["version_prompt"], terminada=True,
        )
        avisos.avisar_narrativa_terminada(id_)
        return
    _actualizar(
        id_, estado="error", error=motivo, detalle_error=json.dumps(detalle, ensure_ascii=False), terminada=True
    )
    avisos.avisar_narrativa_terminada(id_)


def _actualizar(id_: int, terminada=False, **campos):
    asignaciones = [
        f"{c} = CAST(:{c} AS jsonb)" if c in ("resultado", "detalle_error") else f"{c} = :{c}"
        for c in campos
    ]
    if terminada:
        asignaciones.append("terminada_en = now()")
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE narrativas SET {', '.join(asignaciones)} WHERE id = :id"), {"id": id_, **campos})


def _firma(conn, fila, designados: dict, nombres: dict | None = None) -> dict | None:
    """Quien firma: el que ya la reviso, o a quien se le va a mandar.
    nombres: {usuario: nombre} ya consultados (el historial los trae juntos)."""
    if fila["revisada_por"]:
        revisor = fila["revisada_por"]
        nombre = nombres.get(revisor, revisor) if nombres is not None else firmas.nombre_de(conn, revisor)
        return {"usuario": revisor, "nombre": nombre, "cargo": fila["firmada_como"] or firmas.CARGO_RESPONSABLE}
    if fila["estado"] == "error":
        return None
    solicitante = fila["solicitada_por"]
    if solicitante not in designados:
        designados[solicitante] = firmas.designado(conn, solicitante)
    return designados[solicitante]


def obtener(id_: int) -> dict | None:
    asegurar_tabla()
    with engine.connect() as conn:
        fila = conn.execute(
            text(f"SELECT {_COLUMNAS}, resultado FROM narrativas WHERE id = :id"), {"id": id_}
        ).mappings().first()
        if fila is None:
            return None
        return {**fila, "narrativa": fila["resultado"], "firma": _firma(conn, fila, {})}


def listar(
    area_ids: list[int] | None = None,
    periodo: pd.Timestamp | None = None,
    limite: int = 20,
    revision: str | None = None,
) -> list[dict]:
    """Historial (lo mas reciente primero), sin el cuerpo de cada narrativa.

    area_ids: solo esas areas (None = todas). revision: solo las narrativas
    listas con esa revision (pendiente, aprobada o rechazada)."""
    asegurar_tabla()
    filtros, params = [], {"limite": limite}
    if revision is not None:
        filtros.append("estado = 'lista' AND revision = :r")
        params["r"] = revision
    if area_ids is not None:
        filtros.append("area_id = ANY(:a)")
        params["a"] = list(area_ids)
    if periodo is not None:
        filtros.append("periodo = :p")
        params["p"] = periodo.date()
    donde = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    with engine.connect() as conn:
        filas = conn.execute(
            text(f"SELECT {_COLUMNAS} FROM narrativas {donde} ORDER BY id DESC LIMIT :limite"), params
        ).mappings().all()
        # Una consulta para todos los nombres de quien firmo, no una por fila
        # (100 reportes eran 101 consultas: segundos con una base remota)
        revisores = list({f["revisada_por"] for f in filas if f["revisada_por"]})
        nombres = dict(conn.execute(
            text("SELECT usuario, nombre FROM usuarios WHERE usuario = ANY(:u)"), {"u": revisores}
        ).all()) if revisores else {}
        designados = {}
        return [{**f, "narrativa": None, "firma": _firma(conn, f, designados, nombres)} for f in filas]


# ------------------------------------------------------------------ revision
class RevisionNoPermitida(Exception):
    """La narrativa no se puede revisar; `conflicto` distingue 409 de 403."""

    def __init__(self, mensaje: str, conflicto: bool = True):
        super().__init__(mensaje)
        self.conflicto = conflicto


def revisar(
    id_: int, decision: str, revisor: str, comentario: str | None, nota: str | None = None
) -> dict | None:
    """Aprueba o rechaza una narrativa lista (RF-05) y registra quien (RF-11).

    Solo firma la Responsable de RRHH o su suplente vigente, y nunca quien
    la pidio. nota: la "Nota de RRHH" que se agrega al aprobar, aparte del
    texto de la IA (que nunca se edita).

    Devuelve la narrativa actualizada, None si no existe, o lanza
    RevisionNoPermitida. La decision es definitiva. El UPDATE lleva todas las
    condiciones: si dos personas revisan a la vez, solo una gana.
    """
    asegurar_tabla()
    nota = ((nota or "").strip() or None) if decision == "aprobada" else None
    with engine.begin() as conn:
        solicitante = conn.execute(
            text("SELECT solicitada_por FROM narrativas WHERE id = :id"), {"id": id_}
        ).scalar()
        pueden = firmas.pueden_firmar(conn, solicitante)
        cargo = firmas.cargo_al_firmar(conn, revisor)
        actualizada = conn.execute(
            text(
                "UPDATE narrativas SET revision = :d, revisada_por = :u, revisada_en = now(), "
                "comentario_revision = :c, nota_rrhh = :n, firmada_como = :cargo, revisada_desde = :o "
                "WHERE id = :id AND estado = 'lista' AND revision = 'pendiente' "
                "AND solicitada_por IS DISTINCT FROM :u AND :u = ANY(:pueden) RETURNING id"
            ),
            {"id": id_, "d": decision, "u": revisor, "c": comentario, "n": nota, "cargo": cargo,
             "pueden": list(pueden), "o": origen_de_la_peticion.get()},
        ).first()
    if actualizada:
        avisos.avisar_revision(id_)
        return obtener(id_)
    trabajo = obtener(id_)
    if trabajo is None:
        return None
    if trabajo["estado"] != "lista":
        raise RevisionNoPermitida("Solo se pueden revisar las narrativas terminadas (estado lista)")
    if trabajo["revision"] != "pendiente":
        raise RevisionNoPermitida(
            f"Esta narrativa ya fue {trabajo['revision']} por {trabajo['revisada_por']}; "
            "si hace falta otra versión, solicita una nueva"
        )
    if trabajo["solicitada_por"] == revisor:
        raise RevisionNoPermitida(
            "No puedes revisar una narrativa que tú solicitaste: debe hacerlo otra persona de RRHH",
            conflicto=False,
        )
    firma = trabajo["firma"]
    quien = f"{firma['nombre']} ({firma['cargo']})" if firma else "la Responsable de RRHH"
    raise RevisionNoPermitida(f"Este reporte lo firma {quien}", conflicto=False)


# ------------------------------------------------------------------ pedidos
def registrar_pedido(area_id: int, periodo, comentario: str | None, pedido_por: str) -> tuple[int, int]:
    """Direccion o un gerente pide a RRHH un reporte fuera de calendario: se
    guarda y se avisa a las Analistas, que son quienes lo preparan.
    Devuelve (id del pedido, cuantas Analistas recibieron el aviso)."""
    asegurar_tabla()
    with engine.begin() as conn:
        id_ = conn.execute(
            text(
                "INSERT INTO pedidos_reporte (area_id, periodo, comentario, pedido_por) "
                "VALUES (:a, :p, :c, :u) RETURNING id"
            ),
            {"a": area_id, "p": periodo.date(), "c": (comentario or "").strip() or None, "u": pedido_por},
        ).scalar_one()
    return id_, avisos.avisar_pedido(id_)


# --------------------------------------------------------------- exportacion
def registrar_exportacion(id_: int, formato: str, usuario: str) -> None:
    """Bitacora de distribucion: quien descargo el reporte, en que formato y cuando (RF-11)."""
    asegurar_tabla()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO exportaciones (narrativa_id, formato, usuario, origen) VALUES (:i, :f, :u, :o)"),
            {"i": id_, "f": formato, "u": usuario, "o": origen_de_la_peticion.get()},
        )
