"""Pruebas de la programacion mensual (RF-07) y del panel de configuracion:
umbrales editables con bitacora y programacion (RF-12). Paso 10.

La configuracion, las corridas y los umbrales se guardan antes de cada
prueba y se restauran al final: la base local la usa tambien quien desarrolla.
"""
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import avisos, programacion, trabajos
from app.database import engine
from app.kpis import calcular_kpis
from app.llm import ConfiguracionIA
from app.main import app
from app.seguridad import Usuario, crear_usuario, usuario_actual
from conftest import USUARIO_RRHH

OCTUBRE = date(2026, 10, 6)  # el ultimo mes cerrado con datos es agosto de 2026


class _Guardar:
    """Ejecutor que no corre nada: solo anota que se pidio (sin modelo)."""

    def __init__(self):
        self.tareas = []

    def submit(self, fn, *args):
        self.tareas.append(args)


class _ProveedorFalso:
    nombre = "falso"
    modelo = "modelo-falso"
    local = True


@pytest.fixture(autouse=True)
def estado_limpio(monkeypatch):
    """Guarda y restaura programacion, corridas, umbrales y narrativas."""
    programacion.asegurar_tabla()
    with engine.begin() as conn:
        conf = conn.execute(
            text("SELECT activa, dia_del_mes, modificada_por, modificada_en FROM programacion")
        ).mappings().one()
        corridas = conn.execute(text("SELECT * FROM corridas_programadas")).mappings().all()
        umbrales = conn.execute(text("SELECT indicador, umbral_atencion, umbral_critico FROM umbrales")).all()
        ultimo_cambio = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM umbrales_cambios")).scalar()
        ultima_narrativa = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM narrativas")).scalar()
        conn.execute(text("DELETE FROM corridas_programadas"))
    monkeypatch.setattr(trabajos, "ejecutor", _Guardar())
    monkeypatch.setattr(programacion, "obtener_proveedor", lambda: _ProveedorFalso())
    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE programacion SET activa = :activa, dia_del_mes = :dia_del_mes, "
                "modificada_por = :modificada_por, modificada_en = :modificada_en"
            ),
            dict(conf),
        )
        conn.execute(text("DELETE FROM corridas_programadas"))
        for c in corridas:
            conn.execute(
                text("INSERT INTO corridas_programadas VALUES (:periodo, :iniciada_en, :origen, :narrativas)"), dict(c)
            )
        for indicador, atencion, critico in umbrales:
            conn.execute(
                text("UPDATE umbrales SET umbral_atencion = :a, umbral_critico = :c WHERE indicador = :i"),
                {"i": indicador, "a": atencion, "c": critico},
            )
        conn.execute(text("DELETE FROM umbrales_cambios WHERE id > :u"), {"u": ultimo_cambio})
        conn.execute(text("DELETE FROM narrativas WHERE id > :u"), {"u": ultima_narrativa})


def configurar(activa=True, dia=5):
    programacion.guardar(activa, dia, "pruebas")


def nuevas_narrativas():
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT area_id, to_char(periodo, 'YYYY-MM') AS periodo, solicitada_por, programada "
                 "FROM narrativas WHERE programada ORDER BY id")
        ).mappings().all()


# ------------------------------------------------------- mes objetivo
def test_el_objetivo_es_el_ultimo_mes_cerrado_con_datos():
    df = pd.DataFrame({"periodo": pd.to_datetime(["2026-07-01", "2026-08-01", "2026-09-01"])})
    assert programacion.periodo_objetivo(df, date(2026, 10, 6)) == pd.Timestamp("2026-09-01")
    # septiembre esta en curso: aunque ya tenga datos, aun no se reporta
    assert programacion.periodo_objetivo(df, date(2026, 9, 20)) == pd.Timestamp("2026-08-01")
    assert programacion.periodo_objetivo(df, date(2026, 7, 2)) is None


# ----------------------------------------------------------- revisar()
def test_desactivada_no_genera_nada():
    configurar(activa=False)
    r = programacion.revisar(dia=OCTUBRE)
    assert r["narrativas"] == [] and r["mensaje"] == "La programación mensual está desactivada."
    assert programacion.corridas() == []


def test_antes_del_dia_no_genera_nada():
    configurar(dia=10)
    r = programacion.revisar(dia=OCTUBRE)
    assert r["narrativas"] == [] and "a partir del día 10" in r["mensaje"]


def test_genera_el_consolidado_y_cada_area_una_sola_vez():
    configurar(dia=5)
    r = programacion.revisar(origen="script", dia=OCTUBRE)
    df = calcular_kpis()
    areas = sorted(df.loc[df["periodo"] == "2026-08-01", "area_id"].unique())

    assert r["periodo"] == "2026-08" and len(r["narrativas"]) == len(areas)
    filas = nuevas_narrativas()
    assert [f["area_id"] for f in filas] == areas and areas[0] == 0  # el consolidado primero
    assert all(f["periodo"] == "2026-08" and f["solicitada_por"] is None for f in filas)
    assert len(trabajos.ejecutor.tareas) == len(areas)  # cada una va al hilo de trabajo
    [corrida] = programacion.corridas()
    assert corrida["periodo"] == "2026-08" and corrida["origen"] == "script"
    assert corrida["narrativas"] == len(areas)

    # la API revisa cada hora y el script cada dia: no se duplica
    otra = programacion.revisar(dia=date(2026, 10, 7))
    assert otra["narrativas"] == [] and otra["mensaje"] == "Los reportes de agosto 2026 ya se generaron."
    assert len(nuevas_narrativas()) == len(areas)


def test_si_dos_procesos_compiten_solo_uno_gana():
    configurar()
    df = calcular_kpis()
    agosto = pd.Timestamp("2026-08-01")
    primero = programacion._generar(agosto, df, "api")
    segundo = programacion._generar(agosto, df, "script")
    assert primero["narrativas"] and "ya se generaron" in segundo["mensaje"]


def test_sin_ia_configurada_avisa_a_rrhh_una_vez(monkeypatch):
    def sin_ia():
        raise ConfiguracionIA("Groq no se puede usar con datos reales")

    monkeypatch.setattr(programacion, "obtener_proveedor", sin_ia)
    configurar()
    rrhh_id = crear_usuario("zz_prog_rrhh", "Prueba", "rrhh", "Clave-de-prueba-123")
    try:
        r = programacion.revisar(dia=OCTUBRE)
        assert "Groq no se puede usar" in r["mensaje"] and r["narrativas"] == []
        assert programacion.corridas() == []  # se reintenta en la siguiente revision
        programacion.revisar(dia=OCTUBRE)
        rrhh = Usuario(rrhh_id, "zz_prog_rrhh", "Prueba", "rrhh", None)
        errores = [a for a in avisos.listar(rrhh)["avisos"] if a["tipo"] == "error"]
        assert [a["titulo"] for a in errores] == [
            "La programación mensual no pudo generar los reportes de agosto 2026: "
            "Groq no se puede usar con datos reales"
        ]
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM usuarios WHERE id = :i"), {"i": rrhh_id})


def test_las_programadas_las_revisa_cualquier_persona_de_rrhh():
    configurar()
    id_ = programacion.revisar(dia=OCTUBRE)["narrativas"][0]
    with engine.begin() as conn:
        conn.execute(text("UPDATE narrativas SET estado = 'lista' WHERE id = :i"), {"i": id_})
    assert trabajos.revisar(id_, "aprobada", "cualquiera_de_rrhh", None)["revision"] == "aprobada"
    assert trabajos.obtener(id_)["programada"] is True


# ---------------------------------------------------- API: programacion
def como(rol, area_id=None):
    app.dependency_overrides[usuario_actual] = lambda: Usuario(-2, f"pruebas_{rol}", "Prueba", rol, area_id)
    return TestClient(app)


def test_api_programacion_la_ve_cualquiera_y_la_cambia_solo_rrhh():
    for rol in ("direccion", "gerente", "admin_ti"):
        cliente = como(rol, 1 if rol == "gerente" else None)
        assert cliente.get("/programacion").status_code == 200
        r = cliente.put("/programacion", json={"activa": True, "dia_del_mes": 3})
        assert r.status_code == 403 and "Solo Recursos Humanos" in r.json()["detail"]

    app.dependency_overrides[usuario_actual] = lambda: USUARIO_RRHH
    r = TestClient(app).put("/programacion", json={"activa": True, "dia_del_mes": 3})
    assert r.status_code == 200
    datos = r.json()
    assert datos["activa"] is True and datos["dia_del_mes"] == 3
    assert datos["modificada_por"] == USUARIO_RRHH.usuario and datos["modificada_en"]
    assert datos["correo_activo"] is False and datos["corridas"] == []


def test_api_programacion_dia_invalido():
    r = TestClient(app).put("/programacion", json={"activa": True, "dia_del_mes": 31})
    assert r.status_code == 422


# -------------------------------------------------------- API: umbrales
def test_api_rrhh_cambia_un_umbral_y_queda_en_la_bitacora():
    cliente = TestClient(app)
    antes = {u["indicador"]: u for u in cliente.get("/umbrales").json()}["rotacion_total"]

    r = cliente.put("/umbrales/rotacion_total", json={"umbral_atencion": 2.5, "umbral_critico": 4.0})
    assert r.status_code == 200
    assert r.json()["umbral_atencion"] == 2.5 and r.json()["umbral_critico"] == 4.0

    [cambio] = [c for c in cliente.get("/umbrales/cambios").json() if c["usuario"] == USUARIO_RRHH.usuario][:1]
    assert cambio["indicador"] == "rotacion_total" and cambio["nombre"] == "Tasa de rotación mensual"
    assert (cambio["atencion_antes"], cambio["critico_antes"]) == (antes["umbral_atencion"], antes["umbral_critico"])
    assert (cambio["atencion_nuevo"], cambio["critico_nuevo"]) == (2.5, 4.0)

    # el semaforo se recalcula de inmediato (sin esperar el cache de la API)
    kpi = cliente.get("/kpis", params={"area_id": 0, "indicador": "rotacion_total"}).json()[0]
    assert kpi["umbral_critico"] == 4.0


def test_api_sin_cambios_no_ensucia_la_bitacora():
    cliente = TestClient(app)
    actual = {u["indicador"]: u for u in cliente.get("/umbrales").json()}["enps"]
    total = len(cliente.get("/umbrales/cambios?limite=100").json())
    r = cliente.put("/umbrales/enps", json={k: actual[k] for k in ("umbral_atencion", "umbral_critico")})
    assert r.status_code == 200
    assert len(cliente.get("/umbrales/cambios?limite=100").json()) == total


@pytest.mark.parametrize(
    "indicador, atencion, critico, mensaje",
    [
        ("rotacion_total", 4.0, 2.0, "un valor más alto es peor"),
        ("enps", 0, 10, "un valor más bajo es peor"),
        ("cobertura_capacitacion", 60, 150, "entre 0 y 100"),
        ("tiempo_contratacion", -5, 60, "de 0 o más"),
    ],
)
def test_api_umbrales_sin_sentido_se_rechazan(indicador, atencion, critico, mensaje):
    r = TestClient(app).put(f"/umbrales/{indicador}", json={"umbral_atencion": atencion, "umbral_critico": critico})
    assert r.status_code == 422 and mensaje in r.json()["detail"]


def test_api_umbral_inexistente():
    r = TestClient(app).put("/umbrales/no_existe", json={"umbral_atencion": 1, "umbral_critico": 2})
    assert r.status_code == 404


@pytest.mark.parametrize("rol", ["direccion", "gerente", "admin_ti"])
def test_api_solo_rrhh_cambia_umbrales(rol):
    cliente = como(rol, 1 if rol == "gerente" else None)
    r = cliente.put("/umbrales/rotacion_total", json={"umbral_atencion": 2.5, "umbral_critico": 4.0})
    assert r.status_code == 403
    assert cliente.get("/umbrales/cambios").status_code == 200  # la bitacora si la ven
