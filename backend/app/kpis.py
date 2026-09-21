"""Motor analitico: calcula los KPIs de la seccion 10.2 del PRD.

Aqui NO hay IA. Todo es SQL + pandas con formulas deterministas, porque las
cifras que luego redactara el motor de lenguaje deben ser exactas y
verificables (regla 10.3.5).

Salida de calcular_kpis(): un DataFrame "largo", una fila por
(indicador, area, mes), con valor, tendencias y estado de semaforo.
    area_id = 0 -> consolidado corporativo (calculado con los datos crudos de
                   todas las areas juntas, NO como promedio de promedios).
"""
import numpy as np
import pandas as pd
from sqlalchemy import text

from app.database import RAIZ, engine

CORPORATIVO = 0

# Regla de tamano minimo de grupo (10.3.4): si el grupo de un area tiene menos
# de MIN_GRUPO personas, no se muestra el valor de los indicadores sensibles.
# El PRD deja el minimo "definido por politica interna": 5 es un valor tipico.
MIN_GRUPO = 5
INDICADORES_SUJETOS_A_MIN_GRUPO = {"cumplimiento_metas", "enps"}

# El eNPS va de -100 a 100 y su cero es arbitrario: un "cambio porcentual" no
# tiene sentido (ej. de +20 a -50), asi que solo se reporta variacion en puntos.
INDICADORES_SOLO_VARIACION_ABSOLUTA = {"enps"}

# Calendario de meses: del primer al ultimo mes con datos de productividad
# (fuente mensual con un registro por area y mes).
_MESES = """
meses AS (
    SELECT g::date AS mes, (g + interval '1 month')::date AS sig
    FROM generate_series(
        (SELECT MIN(periodo) FROM productividad)::timestamp,
        (SELECT MAX(periodo) FROM productividad)::timestamp,
        interval '1 month'
    ) AS g
)
"""

# Cada consulta devuelve: indicador, area_id, periodo, valor, n
#   n = tamano del grupo o muestra detras del valor (para la regla de minimo).
# GROUPING SETS calcula en una sola pasada el detalle por area y el consolidado
# corporativo (area_id NULL -> se convierte en 0).
CONSULTAS = {
    # --- Reclutamiento (ATS): mes = mes en que se cubrio la vacante ---------
    "contratacion": """
        WITH v AS (
            SELECT area_id,
                   date_trunc('month', fecha_contratacion)::date AS periodo,
                   fecha_contratacion - fecha_apertura AS dias,
                   costo_proceso
            FROM vacantes WHERE fecha_contratacion IS NOT NULL
        )
        SELECT 'tiempo_contratacion' AS indicador, COALESCE(area_id, 0) AS area_id, periodo,
               AVG(dias)::float8 AS valor, COUNT(*)::int AS n
        FROM v GROUP BY GROUPING SETS ((area_id, periodo), (periodo))
        UNION ALL
        SELECT 'costo_por_contratacion', COALESCE(area_id, 0), periodo,
               (SUM(costo_proceso) / COUNT(*))::float8, COUNT(*)::int
        FROM v GROUP BY GROUPING SETS ((area_id, periodo), (periodo))
    """,
    # --- Desempeno: metas logradas / metas asignadas -------------------------
    "cumplimiento_metas": """
        SELECT 'cumplimiento_metas' AS indicador, COALESCE(e.area_id, 0) AS area_id,
               md.periodo,
               (100.0 * SUM(md.metas_logradas) / SUM(md.metas_asignadas))::float8 AS valor,
               COUNT(DISTINCT md.empleado_id)::int AS n
        FROM metas_desempeno md JOIN empleados e ON e.id = md.empleado_id
        GROUP BY GROUPING SETS ((e.area_id, md.periodo), (md.periodo))
    """,
    # --- Capacitacion: cobertura = empleados inscritos / empleados objetivo --
    # Objetivo = empleados activos en el mes. "Capacitado" = inscrito en al
    # menos un programa del mes (definicion a validar con RRHH).
    "cobertura_capacitacion": f"""
        WITH {_MESES},
        activos AS (
            SELECT m.mes AS periodo, e.area_id, e.id AS empleado_id
            FROM meses m JOIN empleados e
              ON e.fecha_ingreso < m.sig AND (e.fecha_baja IS NULL OR e.fecha_baja >= m.mes)
        ),
        inscritos AS (
            SELECT DISTINCT p.periodo, i.empleado_id
            FROM inscripciones_capacitacion i
            JOIN programas_capacitacion p ON p.id = i.programa_id
        )
        SELECT 'cobertura_capacitacion' AS indicador, COALESCE(a.area_id, 0) AS area_id,
               a.periodo,
               (100.0 * COUNT(i.empleado_id) / COUNT(*))::float8 AS valor,
               COUNT(*)::int AS n
        FROM activos a
        LEFT JOIN inscritos i ON i.periodo = a.periodo AND i.empleado_id = a.empleado_id
        GROUP BY GROUPING SETS ((a.area_id, a.periodo), (a.periodo))
    """,
    # --- Capacitacion: finalizados / inscritos -------------------------------
    "tasa_finalizacion": """
        SELECT 'tasa_finalizacion' AS indicador, COALESCE(e.area_id, 0) AS area_id,
               p.periodo,
               (100.0 * COUNT(*) FILTER (WHERE i.completado) / COUNT(*))::float8 AS valor,
               COUNT(*)::int AS n
        FROM inscripciones_capacitacion i
        JOIN programas_capacitacion p ON p.id = i.programa_id
        JOIN empleados e ON e.id = i.empleado_id
        GROUP BY GROUPING SETS ((e.area_id, p.periodo), (p.periodo))
    """,
    # --- Rotacion: bajas del periodo / headcount promedio x 100 --------------
    # headcount promedio = (headcount al inicio del mes + al inicio del mes
    # siguiente) / 2. Se calcula por separado voluntaria e involuntaria.
    "rotacion": f"""
        WITH {_MESES},
        base AS (
            SELECT m.mes AS periodo, COALESCE(e.area_id, 0) AS area_id,
                COUNT(*) FILTER (WHERE e.fecha_ingreso < m.mes
                                   AND (e.fecha_baja IS NULL OR e.fecha_baja >= m.mes)) AS hc_inicio,
                COUNT(*) FILTER (WHERE e.fecha_ingreso < m.sig
                                   AND (e.fecha_baja IS NULL OR e.fecha_baja >= m.sig)) AS hc_fin,
                COUNT(*) FILTER (WHERE e.fecha_baja >= m.mes AND e.fecha_baja < m.sig) AS bajas,
                COUNT(*) FILTER (WHERE e.fecha_baja >= m.mes AND e.fecha_baja < m.sig
                                   AND e.tipo_baja = 'voluntaria') AS bajas_vol,
                COUNT(*) FILTER (WHERE e.fecha_baja >= m.mes AND e.fecha_baja < m.sig
                                   AND e.tipo_baja = 'involuntaria') AS bajas_invol
            FROM meses m CROSS JOIN empleados e
            GROUP BY GROUPING SETS ((m.mes, e.area_id), (m.mes))
        ),
        prom AS (
            SELECT *, (hc_inicio + hc_fin) / 2.0 AS hc_prom FROM base WHERE hc_inicio + hc_fin > 0
        )
        SELECT 'rotacion_total' AS indicador, area_id, periodo,
               (100.0 * bajas / hc_prom)::float8 AS valor, ROUND(hc_prom)::int AS n FROM prom
        UNION ALL
        SELECT 'rotacion_voluntaria', area_id, periodo,
               (100.0 * bajas_vol / hc_prom)::float8, ROUND(hc_prom)::int FROM prom
        UNION ALL
        SELECT 'rotacion_involuntaria', area_id, periodo,
               (100.0 * bajas_invol / hc_prom)::float8, ROUND(hc_prom)::int FROM prom
    """,
    # --- Clima: eNPS = % promotores (9-10) - % detractores (0-6) -------------
    "enps": """
        SELECT 'enps' AS indicador, COALESCE(area_id, 0) AS area_id, periodo,
               (100.0 * (COUNT(*) FILTER (WHERE puntaje >= 9)
                       - COUNT(*) FILTER (WHERE puntaje <= 6)) / COUNT(*))::float8 AS valor,
               COUNT(*)::int AS n
        FROM respuestas_clima WHERE dimension = 'enps'
        GROUP BY GROUPING SETS ((area_id, periodo), (periodo))
    """,
    # --- Productividad: horas efectivas / horas disponibles ------------------
    # n = FTE equivalentes (160 horas disponibles al mes = 1 persona).
    "indice_productividad": """
        SELECT 'indice_productividad' AS indicador, COALESCE(area_id, 0) AS area_id, periodo,
               (100.0 * SUM(horas_efectivas) / SUM(horas_disponibles))::float8 AS valor,
               ROUND(SUM(horas_disponibles) / 160.0)::int AS n
        FROM productividad
        GROUP BY GROUPING SETS ((area_id, periodo), (periodo))
    """,
}


def inicializar_umbrales():
    """Crea la tabla `umbrales` con valores iniciales (idempotente)."""
    sql = (RAIZ / "db" / "umbrales.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        # conexion nativa de psycopg: permite varias sentencias en un execute
        conn.connection.driver_connection.execute(sql)


def semaforo(valor, sentido, umbral_atencion, umbral_critico):
    """Devuelve 'verde', 'amarillo', 'rojo' o 'sin_dato' segun los umbrales."""
    if valor is None or pd.isna(valor):
        return "sin_dato"
    if sentido == "mayor_es_peor":
        if valor >= umbral_critico:
            return "rojo"
        return "amarillo" if valor >= umbral_atencion else "verde"
    if valor <= umbral_critico:
        return "rojo"
    return "amarillo" if valor <= umbral_atencion else "verde"


def _extraer(conn):
    frames = [pd.read_sql(text(sql), conn) for sql in CONSULTAS.values()]
    df = pd.concat(frames, ignore_index=True)
    df["periodo"] = pd.to_datetime(df["periodo"])
    df["area_id"] = df["area_id"].astype(int)
    df["valor"] = df["valor"].astype(float)
    df["n"] = df["n"].astype(int)
    return df


def _aplicar_min_grupo(df):
    """Regla 10.3.4: oculta el valor si el grupo del area es menor al minimo.

    El grupo se mide de forma conservadora: el MENOR entre las personas que
    respaldan el valor (n) y el tamano real del equipo (headcount promedio).
    Asi, si alguien se va y su reemplazo entra el mismo mes, un equipo de 4
    no aparece como si fuera de 5.
    """
    equipo = df.loc[df["indicador"] == "rotacion_total", ["area_id", "periodo", "n"]]
    equipo = equipo.rename(columns={"n": "tam_equipo"})
    df = df.merge(equipo, on=["area_id", "periodo"], how="left")
    grupo = df[["n", "tam_equipo"]].min(axis=1)
    df["suprimido"] = (
        (df["area_id"] != CORPORATIVO)
        & df["indicador"].isin(INDICADORES_SUJETOS_A_MIN_GRUPO)
        & (grupo < MIN_GRUPO)
    )
    df.loc[df["suprimido"], "valor"] = np.nan
    return df.drop(columns="tam_equipo")


def _agregar_tendencias(df):
    """Variacion contra el mes anterior y contra el mismo mes del anio anterior."""
    llaves = ["indicador", "area_id", "periodo"]
    for sufijo, meses in (("mes_ant", 1), ("anio_ant", 12)):
        previo = df[llaves + ["valor"]].rename(columns={"valor": "valor_previo"})
        previo["periodo"] = previo["periodo"] + pd.DateOffset(months=meses)
        df = df.merge(previo, on=llaves, how="left")
        df[f"var_{sufijo}"] = df["valor"] - df["valor_previo"]
        # el % solo se calcula sobre una base positiva
        base = df["valor_previo"].where(df["valor_previo"] > 0)
        df[f"var_{sufijo}_pct"] = df[f"var_{sufijo}"] / base * 100
        df.loc[df["indicador"].isin(INDICADORES_SOLO_VARIACION_ABSOLUTA), f"var_{sufijo}_pct"] = np.nan
        df = df.drop(columns="valor_previo")
    return df


def calcular_kpis():
    """Calcula todos los KPIs para todas las areas y meses con datos."""
    inicializar_umbrales()
    with engine.connect() as conn:
        df = _extraer(conn)
        umbrales = pd.read_sql(text("SELECT * FROM umbrales"), conn)
        areas = pd.read_sql(text("SELECT id AS area_id, nombre AS area FROM areas"), conn)

    areas = pd.concat(
        [pd.DataFrame({"area_id": [CORPORATIVO], "area": ["Corporativo"]}), areas],
        ignore_index=True,
    )
    df = _aplicar_min_grupo(df)
    df = _agregar_tendencias(df)
    df = df.merge(areas, on="area_id", how="left")
    df = df.merge(umbrales, on="indicador", how="left")
    for col in ("umbral_atencion", "umbral_critico"):
        df[col] = df[col].astype(float)

    def estado(fila):
        if fila["suprimido"]:
            return "suprimido"
        return semaforo(
            fila["valor"], fila["sentido"], fila["umbral_atencion"], fila["umbral_critico"]
        )

    df["estado"] = df.apply(estado, axis=1)

    columnas = [
        "indicador", "nombre", "unidad", "area_id", "area", "periodo", "valor", "n",
        "suprimido", "var_mes_ant", "var_mes_ant_pct", "var_anio_ant", "var_anio_ant_pct",
        "estado", "sentido", "umbral_atencion", "umbral_critico",
    ]
    return df[columnas].sort_values(["indicador", "area_id", "periodo"]).reset_index(drop=True)