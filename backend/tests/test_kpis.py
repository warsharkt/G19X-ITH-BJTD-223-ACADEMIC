"""Pruebas del motor analitico (paso 3).

Idea central: RECONCILIAR. Cada cifra que calcula el motor con SQL se
recalcula aqui de forma independiente, en Python puro, desde las filas
crudas de la base. Si coinciden, el motor cumple la metrica de exito de
"100% de coincidencia contra los sistemas fuente" (seccion 11 del PRD).

Requisito: PostgreSQL arriba y datos cargados (python -m scripts.seed).
Ejecutar desde la carpeta backend:  python -m pytest -q
"""
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import text

from app.database import engine
from app.kpis import MIN_GRUPO, calcular_kpis, semaforo


@pytest.fixture(scope="module")
def kpis():
    return calcular_kpis()


def sig_mes(d):
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def serie(kpis, indicador, area):
    f = kpis[(kpis["indicador"] == indicador) & (kpis["area"] == area)]
    return f.set_index("periodo")


# ---------------------------------------------------------------- semaforo
def test_semaforo_mayor_es_peor():
    assert semaforo(1.0, "mayor_es_peor", 2.0, 3.5) == "verde"
    assert semaforo(2.0, "mayor_es_peor", 2.0, 3.5) == "amarillo"  # el limite ya alerta
    assert semaforo(3.5, "mayor_es_peor", 2.0, 3.5) == "rojo"


def test_semaforo_menor_es_peor():
    assert semaforo(15, "menor_es_peor", 10, 0) == "verde"
    assert semaforo(10, "menor_es_peor", 10, 0) == "amarillo"
    assert semaforo(-5, "menor_es_peor", 10, 0) == "rojo"


def test_semaforo_sin_dato():
    assert semaforo(float("nan"), "mayor_es_peor", 2.0, 3.5) == "sin_dato"
    assert semaforo(None, "menor_es_peor", 10, 0) == "sin_dato"


# ---------------------------------------------------------- reconciliacion
def test_rotacion_reconcilia_con_calculo_independiente(kpis):
    """Tasa de rotacion de Operaciones, mes por mes, recalculada en Python."""
    with engine.connect() as conn:
        filas = conn.execute(
            text(
                "SELECT e.fecha_ingreso, e.fecha_baja FROM empleados e "
                "JOIN areas a ON a.id = e.area_id WHERE a.nombre = 'Operaciones'"
            )
        ).all()

    def activo_al(corte, ingreso, baja):
        return ingreso < corte and (baja is None or baja >= corte)

    s = serie(kpis, "rotacion_total", "Operaciones")
    assert len(s) == 24
    for periodo, fila in s.iterrows():
        mes = periodo.date()
        sig = sig_mes(mes)
        inicio = sum(activo_al(mes, i, b) for i, b in filas)
        fin = sum(activo_al(sig, i, b) for i, b in filas)
        bajas = sum(1 for _, b in filas if b is not None and mes <= b < sig)
        esperado = 100 * bajas / ((inicio + fin) / 2)
        assert fila["valor"] == pytest.approx(esperado, abs=1e-9), f"rotacion {mes}"


def test_rotacion_total_es_voluntaria_mas_involuntaria(kpis):
    for area in ("Corporativo", "Operaciones", "TI"):
        total = serie(kpis, "rotacion_total", area)["valor"]
        vol = serie(kpis, "rotacion_voluntaria", area)["valor"]
        invol = serie(kpis, "rotacion_involuntaria", area)["valor"]
        pd.testing.assert_series_equal(total, vol + invol, check_names=False, atol=1e-9)


def test_enps_corporativo_reconcilia(kpis):
    """El consolidado se calcula con las respuestas crudas, no promediando areas."""
    mes = date(2026, 3, 1)
    with engine.connect() as conn:
        puntajes = [
            r[0]
            for r in conn.execute(
                text("SELECT puntaje FROM respuestas_clima WHERE dimension = 'enps' AND periodo = :m"),
                {"m": mes},
            )
        ]
    promotores = sum(p >= 9 for p in puntajes)
    detractores = sum(p <= 6 for p in puntajes)
    esperado = 100 * (promotores - detractores) / len(puntajes)

    real = serie(kpis, "enps", "Corporativo").loc[pd.Timestamp(mes), "valor"]
    assert real == pytest.approx(esperado, abs=1e-9)


def test_cumplimiento_metas_corporativo_reconcilia(kpis):
    mes = date(2026, 6, 1)
    with engine.connect() as conn:
        logradas, asignadas = conn.execute(
            text(
                "SELECT SUM(metas_logradas), SUM(metas_asignadas) "
                "FROM metas_desempeno WHERE periodo = :m"
            ),
            {"m": mes},
        ).one()
    real = serie(kpis, "cumplimiento_metas", "Corporativo").loc[pd.Timestamp(mes), "valor"]
    assert real == pytest.approx(100 * logradas / asignadas, abs=1e-9)


def test_tiempo_contratacion_reconcilia(kpis):
    with engine.connect() as conn:
        filas = conn.execute(
            text(
                "SELECT fecha_apertura, fecha_contratacion FROM vacantes "
                "WHERE fecha_contratacion IS NOT NULL"
            )
        ).all()
    por_mes = {}
    for apertura, contratacion in filas:
        clave = contratacion.replace(day=1)
        por_mes.setdefault(clave, []).append((contratacion - apertura).days)

    s = serie(kpis, "tiempo_contratacion", "Corporativo")
    assert len(s) == len(por_mes)
    for mes, dias in por_mes.items():
        assert s.loc[pd.Timestamp(mes), "valor"] == pytest.approx(sum(dias) / len(dias))


# --------------------------------------------------------------- tendencias
def test_tendencias_mes_anterior_y_anio_anterior(kpis):
    s = serie(kpis, "enps", "Operaciones")["valor"]
    mes = pd.Timestamp("2026-04-01")
    fila = serie(kpis, "enps", "Operaciones").loc[mes]
    assert fila["var_mes_ant"] == pytest.approx(s[mes] - s[pd.Timestamp("2026-03-01")])
    assert fila["var_anio_ant"] == pytest.approx(s[mes] - s[pd.Timestamp("2025-04-01")])


def test_enps_solo_tiene_variacion_en_puntos(kpis):
    """Un % sobre un eNPS que cruza el cero no tiene sentido (ej. -390%)."""
    s = serie(kpis, "enps", "Operaciones")
    assert s["var_mes_ant"].notna().sum() == 23
    assert s["var_mes_ant_pct"].isna().all()
    assert s["var_anio_ant_pct"].isna().all()


def test_variacion_porcentual_de_un_indicador_positivo(kpis):
    s = serie(kpis, "cumplimiento_metas", "Corporativo")
    mes, previo = pd.Timestamp("2026-06-01"), pd.Timestamp("2026-05-01")
    esperado = (s.loc[mes, "valor"] - s.loc[previo, "valor"]) / s.loc[previo, "valor"] * 100
    assert s.loc[mes, "var_mes_ant_pct"] == pytest.approx(esperado)


def test_primer_mes_no_tiene_variacion_contra_mes_anterior(kpis):
    primero = serie(kpis, "enps", "Operaciones").iloc[0]
    assert pd.isna(primero["var_mes_ant"])
    assert pd.isna(primero["var_anio_ant"])


# ------------------------------------------- reglas de negocio y escenario
def test_area_pequena_se_suprime(kpis):
    """Legal tiene 4 personas: clima y desempeno no se deben mostrar (10.3.4)."""
    for indicador in ("enps", "cumplimiento_metas"):
        s = serie(kpis, indicador, "Legal")
        assert s["suprimido"].all()
        assert s["valor"].isna().all()
        assert (s["estado"] == "suprimido").all()


def test_baja_y_reemplazo_el_mismo_mes_no_destapa_area_pequena(kpis):
    """Si en Legal sale una persona y entra su reemplazo el mismo mes, hay 5
    personas evaluadas pero el equipo sigue siendo de 4: debe seguir oculto."""
    s = serie(kpis, "cumplimiento_metas", "Legal")
    meses_con_5 = s[s["n"] >= MIN_GRUPO]
    if meses_con_5.empty:
        pytest.skip("Con estos datos Legal no tuvo baja y reemplazo el mismo mes")
    assert meses_con_5["suprimido"].all()


def test_area_grande_y_corporativo_no_se_suprimen(kpis):
    for area in ("Operaciones", "Corporativo"):
        assert not serie(kpis, "enps", area)["suprimido"].any()


def test_escenario_crisis_operaciones(kpis):
    """Ene-may 2026: eNPS en rojo; rotacion sube por encima del umbral de atencion."""
    enps = serie(kpis, "enps", "Operaciones")
    for mes in pd.date_range("2026-01-01", "2026-05-01", freq="MS"):
        assert enps.loc[mes, "estado"] == "rojo"

    rot = serie(kpis, "rotacion_total", "Operaciones")
    onda = rot.loc["2026-03-01":"2026-05-01"]
    assert (onda["estado"] != "verde").any()
    assert onda["valor"].max() > rot.loc[:"2025-12-01", "valor"].mean()