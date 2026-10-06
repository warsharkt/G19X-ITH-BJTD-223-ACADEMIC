"""Edicion de los umbrales del semaforo (paso 10, RF-12) y su bitacora.

Solo RRHH los cambia (lo exige la API): un umbral decide que se pinta de rojo
y a quien le llega una alerta, asi que es una decision de negocio, no de TI
(regla 10.3.3). Cada cambio guarda quien lo hizo, cuando y los valores de
antes y despues en `umbrales_cambios` (RF-11).
"""
import math

from sqlalchemy import text

from app.database import engine
from app.kpis import inicializar_umbrales

# Rango razonable de cada unidad: atrapa errores de dedo (75 en vez de 7.5
# sigue siendo posible, pero 750 % no).
RANGOS = {"%": (0, 100), "puntos": (-100, 100), "días": (0, None), "MXN": (0, None)}

_COLUMNAS = (
    "indicador, nombre, unidad, sentido, "
    "umbral_atencion::float8 AS umbral_atencion, umbral_critico::float8 AS umbral_critico"
)


class UmbralInvalido(ValueError):
    """Los valores no tienen sentido para ese indicador."""


def listar() -> list[dict]:
    inicializar_umbrales()
    with engine.connect() as conn:
        return [dict(f) for f in conn.execute(text(f"SELECT {_COLUMNAS} FROM umbrales ORDER BY indicador")).mappings()]


def _validar(actual: dict, atencion: float, critico: float):
    if not (math.isfinite(atencion) and math.isfinite(critico)):
        raise UmbralInvalido("Los umbrales deben ser números")
    minimo, maximo = RANGOS.get(actual["unidad"], (None, None))
    for valor in (atencion, critico):
        if (minimo is not None and valor < minimo) or (maximo is not None and valor > maximo):
            rango = f"entre {minimo} y {maximo}" if maximo is not None else f"de {minimo} o más"
            raise UmbralInvalido(f"{actual['nombre']} se mide en {actual['unidad']}: los umbrales van {rango}")
    if actual["sentido"] == "mayor_es_peor" and critico < atencion:
        raise UmbralInvalido(
            f"En {actual['nombre']} un valor más alto es peor: el umbral crítico debe ser mayor "
            "o igual que el de atención"
        )
    if actual["sentido"] == "menor_es_peor" and critico > atencion:
        raise UmbralInvalido(
            f"En {actual['nombre']} un valor más bajo es peor: el umbral crítico debe ser menor "
            "o igual que el de atención"
        )


def actualizar(indicador: str, atencion: float, critico: float, usuario: str) -> dict | None:
    """Cambia los umbrales de un indicador y deja el cambio en la bitacora.

    Devuelve el umbral actualizado, None si el indicador no existe, o lanza
    UmbralInvalido. Si los valores no cambian, no se registra nada."""
    inicializar_umbrales()
    with engine.begin() as conn:
        actual = conn.execute(
            text(f"SELECT {_COLUMNAS} FROM umbrales WHERE indicador = :i FOR UPDATE"), {"i": indicador}
        ).mappings().first()
        if actual is None:
            return None
        actual = dict(actual)
        _validar(actual, atencion, critico)
        if (actual["umbral_atencion"], actual["umbral_critico"]) == (atencion, critico):
            return actual
        conn.execute(
            text("UPDATE umbrales SET umbral_atencion = :a, umbral_critico = :c WHERE indicador = :i"),
            {"i": indicador, "a": atencion, "c": critico},
        )
        conn.execute(
            text(
                "INSERT INTO umbrales_cambios "
                "(indicador, atencion_antes, critico_antes, atencion_nuevo, critico_nuevo, usuario) "
                "VALUES (:i, :aa, :ca, :a, :c, :u)"
            ),
            {"i": indicador, "aa": actual["umbral_atencion"], "ca": actual["umbral_critico"],
             "a": atencion, "c": critico, "u": usuario},
        )
    return {**actual, "umbral_atencion": atencion, "umbral_critico": critico}


def cambios(limite: int = 20) -> list[dict]:
    """Bitacora de cambios, del mas reciente al mas antiguo."""
    inicializar_umbrales()
    with engine.connect() as conn:
        filas = conn.execute(
            text(
                "SELECT c.id, c.indicador, u.nombre, u.unidad, "
                "c.atencion_antes::float8 AS atencion_antes, c.critico_antes::float8 AS critico_antes, "
                "c.atencion_nuevo::float8 AS atencion_nuevo, c.critico_nuevo::float8 AS critico_nuevo, "
                "c.usuario, c.cambiado_en "
                "FROM umbrales_cambios c JOIN umbrales u USING (indicador) "
                "ORDER BY c.id DESC LIMIT :limite"
            ),
            {"limite": limite},
        ).mappings().all()
    return [dict(f) for f in filas]
