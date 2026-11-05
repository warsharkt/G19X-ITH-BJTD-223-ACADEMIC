"""Pruebas de la programacion mensual (RF-07) y del panel de configuracion:
umbrales editables con bitacora y programacion (RF-12). Paso 10.

La configuracion, las corridas y los umbrales se guardan antes de cada
prueba y se restauran al final: la base local la usa tambien quien desarrolla.
"""
import threading
import time
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import avisos, programacion, trabajos
from app.database import engine
from app.kpis import calcular_kpis
from app.llm import ConfiguracionIA, ProveedorNoDisponible
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


def test_un_mes_a_medio_cargar_espera_a_sus_fuentes():
    """Solo las vacantes de septiembre: el mes ya tiene un indicador, pero no
    se genera hasta que esten las cuatro fuentes mensuales."""
    configurar()
    with engine.begin() as conn:
        id_ = conn.execute(text(
            "INSERT INTO vacantes (area_id, fecha_apertura, fecha_contratacion, costo_proceso) "
            "VALUES ((SELECT MIN(id) FROM areas), '2026-08-20', '2026-09-15', 10000) RETURNING id"
        )).scalar_one()
    try:
        assert "2026-09-01" in set(calcular_kpis()["periodo"].astype(str))
        r = programacion.revisar(dia=OCTUBRE)
        assert r["narrativas"] == [] and r["mensaje"] == (
            "Los reportes de septiembre 2026 se generan cuando estén todas sus fuentes. Falta: "
            "Metas de desempeño, Capacitación, Encuesta de ambiente laboral, Productividad."
        )
        assert programacion.corridas() == [] and nuevas_narrativas() == []  # se vuelve a revisar luego
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM vacantes WHERE id = :i"), {"i": id_})


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


def test_las_programadas_las_firma_la_responsable():
    configurar()
    id_ = programacion.revisar(dia=OCTUBRE)["narrativas"][0]
    with engine.begin() as conn:
        conn.execute(text("UPDATE narrativas SET estado = 'lista' WHERE id = :i"), {"i": id_})
    responsable = crear_usuario("zz_prog_firma", "Prueba", "rrhh", "Clave-de-prueba-123", firma_reportes=True)
    try:
        assert trabajos.revisar(id_, "aprobada", "zz_prog_firma", None)["revision"] == "aprobada"
        assert trabajos.obtener(id_)["programada"] is True
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM usuarios WHERE id = :i"), {"i": responsable})


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
RESPONSABLE = Usuario(-3, "pruebas_responsable", "Responsable", "rrhh", None, firma_reportes=True)


@pytest.fixture()
def como_responsable():
    """Los umbrales los cambia solo la Responsable de RRHH (la sesion por
    defecto de las pruebas es una Analista)."""
    app.dependency_overrides[usuario_actual] = lambda: RESPONSABLE


def test_api_la_responsable_cambia_un_umbral_y_queda_en_la_bitacora(como_responsable):
    cliente = TestClient(app)
    antes = {u["indicador"]: u for u in cliente.get("/umbrales").json()}["rotacion_total"]

    r = cliente.put("/umbrales/rotacion_total", json={"umbral_atencion": 2.5, "umbral_critico": 4.0})
    assert r.status_code == 200
    assert r.json()["umbral_atencion"] == 2.5 and r.json()["umbral_critico"] == 4.0

    [cambio] = [c for c in cliente.get("/umbrales/cambios").json() if c["usuario"] == RESPONSABLE.usuario][:1]
    assert cambio["indicador"] == "rotacion_total" and cambio["nombre"] == "Tasa de rotación mensual"
    assert (cambio["atencion_antes"], cambio["critico_antes"]) == (antes["umbral_atencion"], antes["umbral_critico"])
    assert (cambio["atencion_nuevo"], cambio["critico_nuevo"]) == (2.5, 4.0)

    # el semaforo se recalcula de inmediato (sin esperar el cache de la API)
    kpi = cliente.get("/kpis", params={"area_id": 0, "indicador": "rotacion_total"}).json()[0]
    assert kpi["umbral_critico"] == 4.0


def test_api_sin_cambios_no_ensucia_la_bitacora(como_responsable):
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
def test_api_umbrales_sin_sentido_se_rechazan(como_responsable, indicador, atencion, critico, mensaje):
    r = TestClient(app).put(f"/umbrales/{indicador}", json={"umbral_atencion": atencion, "umbral_critico": critico})
    assert r.status_code == 422 and mensaje in r.json()["detail"]


def test_api_umbral_inexistente(como_responsable):
    r = TestClient(app).put("/umbrales/no_existe", json={"umbral_atencion": 1, "umbral_critico": 2})
    assert r.status_code == 404


@pytest.mark.parametrize("rol", ["rrhh", "direccion", "gerente", "admin_ti"])
def test_api_solo_la_responsable_cambia_umbrales(rol):
    """Ni la Analista (rrhh sin firma), que prepara los reportes, ni los demas roles."""
    cliente = como(rol, 1 if rol == "gerente" else None)
    r = cliente.put("/umbrales/rotacion_total", json={"umbral_atencion": 2.5, "umbral_critico": 4.0})
    assert r.status_code == 403 and "Responsable" in r.json()["detail"]
    assert cliente.get("/umbrales/cambios").status_code == 200  # la bitacora si la ven


# --------------------------------------- reportes que no terminaron (octava auditoria)
AGOSTO = date(2026, 8, 1)


class _ProveedorColgado(_ProveedorFalso):
    """Un modelo que no responde: cada llamada le costaria OLLAMA_TIMEOUT a la cola."""

    def __init__(self):
        self.llamadas = 0

    def generar(self, mensajes, esquema):
        self.llamadas += 1
        raise ProveedorNoDisponible("se agotó el tiempo de espera")


class _ProveedorInvalido(_ProveedorFalso):
    def generar(self, mensajes, esquema):
        return "esto no es JSON"


def generar_el_mes():
    configurar()
    programacion.revisar(dia=OCTUBRE)
    tareas = list(trabajos.ejecutor.tareas)
    trabajos.ejecutor.tareas.clear()
    return tareas


def correr(tareas, proveedor):
    for id_, periodo, area_id, _, df in tareas:
        trabajos._ejecutar(id_, periodo, area_id, proveedor, df)


def errores_de(usuario):
    return [a["titulo"] for a in avisos.listar(usuario)["avisos"] if a["tipo"] == "error"]


@pytest.fixture
def rrhh():
    id_ = crear_usuario("zz_prog_rrhh", "Prueba", "rrhh", "Clave-de-prueba-123")
    yield Usuario(id_, "zz_prog_rrhh", "Prueba", "rrhh", None)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM usuarios WHERE id = :i"), {"i": id_})


def test_lo_que_interrumpe_un_reinicio_se_vuelve_a_generar_solo():
    tareas = generar_el_mes()
    with engine.begin() as conn:  # el primero alcanzo a terminar: ese no se repite
        conn.execute(text("UPDATE narrativas SET estado = 'lista' WHERE id = :i"), {"i": tareas[0][0]})
    assert trabajos.marcar_interrumpidas() == [AGOSTO]

    r = programacion.revisar(dia=OCTUBRE)
    assert len(r["narrativas"]) == len(tareas) - 1
    assert {t[2] for t in trabajos.ejecutor.tareas} == {t[2] for t in tareas[1:]}
    assert "Se volvieron a solicitar" in r["mensaje"]
    assert programacion.revisar(dia=OCTUBRE)["narrativas"] == []  # ya van en camino
    assert programacion.corridas()[0]["narrativas"] == len(tareas)


def test_si_se_reinicia_otra_vez_se_deja_de_intentar_y_se_avisa_una_vez(rrhh):
    tareas = generar_el_mes()
    for _ in range(programacion.FALLOS_MAXIMOS - 1):
        trabajos.marcar_interrumpidas()
        assert len(programacion.revisar(dia=OCTUBRE)["narrativas"]) == len(tareas)
    trabajos.marcar_interrumpidas()
    assert programacion.revisar(dia=OCTUBRE)["narrativas"] == []
    programacion.revisar(dia=OCTUBRE)
    agotados = [t for t in errores_de(rrhh) if "siguen sin generarse" in t]
    assert len(agotados) == 1 and str(len(tareas)) in agotados[0]


def test_un_reinicio_avisa_a_rrhh_al_arrancar(monkeypatch, rrhh):
    monkeypatch.setenv("PROGRAMACION_EN_API", "no")
    generar_el_mes()
    with TestClient(app):
        pass
    titulos = errores_de(rrhh)
    assert len(titulos) == 1 and "agosto 2026" in titulos[0] and "se reinició" in titulos[0]


def test_lo_pedido_a_mano_no_se_repite_ni_avisa():
    tareas = generar_el_mes()
    with engine.begin() as conn:
        conn.execute(text("UPDATE narrativas SET estado = 'lista' WHERE programada"))
        conn.execute(
            text("INSERT INTO narrativas (area_id, periodo, solicitada_por) VALUES (:a, :p, 'pruebas')"),
            {"a": tareas[0][2], "p": AGOSTO},
        )
    assert trabajos.marcar_interrumpidas() == []
    assert programacion.revisar(dia=OCTUBRE)["narrativas"] == []


def test_una_corrida_terminada_no_pide_areas_que_le_faltaron():
    """Un area que aparece despues no se genera sola: la corrida ya termino."""
    tareas = generar_el_mes()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM narrativas WHERE id = :i"), {"i": tareas[0][0]})
    assert programacion.revisar(dia=OCTUBRE)["narrativas"] == []


def test_si_alguien_ya_lo_pidio_a_mano_no_se_repite():
    tareas = generar_el_mes()
    trabajos.marcar_interrumpidas()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO narrativas (area_id, periodo, solicitada_por) VALUES (:a, :p, 'pruebas')"),
            {"a": tareas[0][2], "p": AGOSTO},
        )
    assert len(programacion.revisar(dia=OCTUBRE)["narrativas"]) == len(tareas) - 1


def test_con_la_programacion_apagada_no_se_repite_nada():
    generar_el_mes()
    trabajos.marcar_interrumpidas()
    configurar(activa=False)
    assert programacion.revisar(dia=OCTUBRE)["narrativas"] == []


def test_un_reporte_que_no_paso_la_validacion_no_se_repite_solo(rrhh):
    tareas = generar_el_mes()
    correr(tareas[:1], _ProveedorInvalido())
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE narrativas SET estado = 'lista' WHERE programada AND estado = 'en_proceso'")
        )
    assert programacion.revisar(dia=OCTUBRE)["narrativas"] == []
    assert any("No se pudo generar el reporte programado" in t for t in errores_de(rrhh))


def test_un_modelo_colgado_solo_cuesta_una_espera_y_un_aviso(rrhh):
    tareas = generar_el_mes()
    colgado = _ProveedorColgado()
    correr(tareas, colgado)
    assert colgado.llamadas == 1  # antes: una por reporte, 15 minutos cada una
    with engine.connect() as conn:
        filas = conn.execute(text("SELECT estado, error FROM narrativas WHERE programada")).all()
    assert len(filas) == len(tareas)
    assert all(e == "error" and "no estuvo disponible" in m for e, m in filas)
    titulos = errores_de(rrhh)
    assert len(titulos) == 1 and "agosto 2026" in titulos[0]


def test_mientras_el_modelo_sigue_caido_no_se_gastan_intentos():
    tareas = generar_el_mes()
    correr(tareas, _ProveedorColgado())
    assert programacion.revisar(dia=OCTUBRE)["narrativas"] == []


def test_cuando_el_modelo_vuelve_se_reintenta_lo_que_fallo():
    tareas = generar_el_mes()
    correr(tareas, _ProveedorColgado())
    assert not trabajos.modelo_disponible()
    trabajos._caida["hasta"] = time.monotonic() - 1  # ya paso la espera
    assert trabajos.modelo_disponible()
    assert len(programacion.revisar(dia=OCTUBRE)["narrativas"]) == len(tareas)


def test_una_corrida_cortada_a_la_mitad_se_completa():
    """La API murio despues de anotar el mes y antes de pedir los reportes."""
    tareas = generar_el_mes()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM narrativas WHERE programada AND id <> :i"), {"i": tareas[0][0]})
        conn.execute(text("UPDATE corridas_programadas SET narrativas = 0"))
    r = programacion.revisar(dia=OCTUBRE)
    assert len(r["narrativas"]) == len(tareas) - 1
    assert programacion.corridas()[0]["narrativas"] == len(tareas)


def test_dos_revisiones_a_la_vez_no_duplican_los_reintentos():
    tareas = generar_el_mes()
    trabajos.marcar_interrumpidas()
    resultados = []
    hilos = [
        threading.Thread(target=lambda: resultados.append(programacion.revisar(dia=OCTUBRE)["narrativas"]))
        for _ in range(4)
    ]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(len(r) for r in resultados) == [0, 0, 0, len(tareas)]
