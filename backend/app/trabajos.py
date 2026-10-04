"""Generacion de narrativas en segundo plano (RF-07).

En CPU el modelo tarda minutos por reporte: la API no hace esperar al
usuario. Registra la solicitud en la tabla `narrativas` como "en_proceso",
responde de inmediato con su id y un solo hilo de trabajo la redacta
(uno a la vez: un modelo local en CPU no gana nada con peticiones en
paralelo, solo se vuelven todas mas lentas).

Si el modelo responde pero no pasa los guardarrailes, se pide de nuevo desde
cero (hasta NARRATIVA_RONDAS veces en total). Si no esta disponible, no se
insiste: queda en "error" con el motivo para que RRHH lo vea.
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from sqlalchemy import text

from app import schemas
from app.database import engine, ejecutar_sql
from app.narrativa import NarrativaNoGenerada, generar_narrativa

RONDAS = int(os.getenv("NARRATIVA_RONDAS", "2"))

# Reemplazable en pruebas por un ejecutor que corre la tarea en el momento.
ejecutor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="narrativa")
_tabla_lista = False

_COLUMNAS = (
    "id, area_id, to_char(periodo, 'YYYY-MM') AS periodo, estado, solicitada_en, terminada_en, "
    "proveedor, modelo, version_prompt, rondas, error, detalle_error, solicitada_por, "
    "revision, revisada_por, revisada_en, comentario_revision"
)


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
    periodo: pd.Timestamp, area_id: int, proveedor, df: pd.DataFrame, solicitante: str | None = None
) -> int:
    """Registra la solicitud (con quien la pidio) y la manda al hilo de trabajo. Devuelve su id."""
    asegurar_tabla()
    with engine.begin() as conn:
        id_ = conn.execute(
            text(
                "INSERT INTO narrativas (area_id, periodo, proveedor, modelo, solicitada_por) "
                "VALUES (:a, :p, :prov, :mod, :sol) RETURNING id"
            ),
            {"a": area_id, "p": periodo.date(), "prov": proveedor.nombre, "mod": proveedor.modelo,
             "sol": solicitante},
        ).scalar_one()
    ejecutor.submit(_ejecutar, id_, periodo, area_id, proveedor, df)
    return id_


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
        resultado = schemas.Narrativa(**n).model_dump(mode="json")
        _actualizar(
            id_, estado="lista", resultado=json.dumps(resultado, ensure_ascii=False),
            version_prompt=n["version_prompt"], terminada=True,
        )
        return
    _actualizar(
        id_, estado="error", error=motivo, detalle_error=json.dumps(detalle, ensure_ascii=False), terminada=True
    )


def _actualizar(id_: int, terminada=False, **campos):
    asignaciones = [
        f"{c} = CAST(:{c} AS jsonb)" if c in ("resultado", "detalle_error") else f"{c} = :{c}"
        for c in campos
    ]
    if terminada:
        asignaciones.append("terminada_en = now()")
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE narrativas SET {', '.join(asignaciones)} WHERE id = :id"), {"id": id_, **campos})


def obtener(id_: int) -> dict | None:
    asegurar_tabla()
    with engine.connect() as conn:
        fila = conn.execute(
            text(f"SELECT {_COLUMNAS}, resultado FROM narrativas WHERE id = :id"), {"id": id_}
        ).mappings().first()
    if fila is None:
        return None
    return {**fila, "narrativa": fila["resultado"]}


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
    return [{**f, "narrativa": None} for f in filas]


# ------------------------------------------------------------------ revision
class RevisionNoPermitida(Exception):
    """La narrativa no se puede revisar; `conflicto` distingue 409 de 403."""

    def __init__(self, mensaje: str, conflicto: bool = True):
        super().__init__(mensaje)
        self.conflicto = conflicto


def revisar(id_: int, decision: str, revisor: str, comentario: str | None) -> dict | None:
    """Aprueba o rechaza una narrativa lista (RF-05) y registra quien (RF-11).

    Devuelve la narrativa actualizada, None si no existe, o lanza
    RevisionNoPermitida. La decision es definitiva. El UPDATE lleva todas las
    condiciones: si dos personas revisan a la vez, solo una gana.
    """
    asegurar_tabla()
    with engine.begin() as conn:
        actualizada = conn.execute(
            text(
                "UPDATE narrativas SET revision = :d, revisada_por = :u, revisada_en = now(), "
                "comentario_revision = :c "
                "WHERE id = :id AND estado = 'lista' AND revision = 'pendiente' "
                "AND solicitada_por IS DISTINCT FROM :u RETURNING id"
            ),
            {"id": id_, "d": decision, "u": revisor, "c": comentario},
        ).first()
    if actualizada:
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
    raise RevisionNoPermitida(
        "No puedes revisar una narrativa que tú solicitaste: debe hacerlo otra persona de RRHH",
        conflicto=False,
    )
