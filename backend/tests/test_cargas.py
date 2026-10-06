"""Pruebas de la carga de datos desde los sistemas fuente (hito 11).

Aplicar archivos cambia los datos de la base local: al terminar el modulo se
vuelven a generar los datos sinteticos (scripts/seed.py) para que las demas
pruebas encuentren lo de siempre.
"""
import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import cargas
from app.database import engine
from app.main import _cache, app
from app.seguridad import Usuario, usuario_actual


@pytest.fixture(scope="module", autouse=True)
def datos_originales():
    cargas.asegurar_tabla()
    with engine.connect() as conn:
        ultima = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM cargas")).scalar()
    yield
    from scripts import seed  # genera los datos al importarse (deterministas)

    seed.cargar()
    cargas.asegurar_tabla()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM cargas WHERE id > :u"), {"u": ultima})
    _cache["df"] = None


@pytest.fixture()
def client():
    return TestClient(app)


def subir(client, fuente, contenido: bytes, nombre="archivo.csv"):
    return client.post(f"/cargas/{fuente}", files={"archivo": (nombre, contenido)})


def ejemplo(client, fuente, formato="xlsx"):
    r = client.get(f"/cargas/ejemplos/{fuente}", params={"formato": formato})
    assert r.status_code == 200, r.text
    return r.content, r.headers["content-disposition"].split('filename="')[1].rstrip('"')


def csv(filas: list[dict]) -> bytes:
    return pd.DataFrame(filas).to_csv(index=False).encode("utf-8")


# ------------------------------------------------------------- permisos
@pytest.mark.parametrize("rol", ["direccion", "gerente", "admin_ti"])
def test_solo_rrhh_carga_datos(client, rol):
    app.dependency_overrides[usuario_actual] = lambda: Usuario(-3, "pruebas_x", "X", rol, 1 if rol == "gerente" else None)
    assert client.get("/cargas/fuentes").status_code == 403
    assert subir(client, "productividad", b"area,periodo\n").status_code == 403
    assert client.get("/cargas").status_code == 403


def test_catalogo_y_plantillas(client):
    datos = client.get("/cargas/fuentes").json()
    assert [f["clave"] for f in datos["fuentes"]] == ["hris", "ats", "desempeno", "capacitacion", "clima", "productividad"]
    assert datos["ejemplos"] == {"mes": "2026-09", "nombre_mes": "septiembre 2026"}
    plantilla = client.get("/cargas/plantillas/desempeno", params={"formato": "csv"})
    assert plantilla.content.decode("utf-8-sig").strip() == "codigo_empleado,periodo,metas_asignadas,metas_logradas,calificacion"
    assert client.get("/cargas/plantillas/no_existe").status_code == 404


# ------------------------------------------------------------ validacion
def test_rechaza_archivos_que_no_son_csv_ni_excel_o_muy_grandes(client):
    r = subir(client, "clima", b"hola", "datos.txt")
    assert r.status_code == 422 and ".csv o .xlsx" in r.json()["detail"]
    r = subir(client, "clima", b"a" * (cargas.BYTES_MAXIMOS + 1))
    assert r.status_code == 422 and "MB" in r.json()["detail"]


def test_falta_una_columna(client):
    r = subir(client, "productividad", csv([{"area": "Ventas", "periodo": "2026-09"}]))
    assert r.status_code == 201
    carga = r.json()
    assert carga["estado"] == "con_errores"
    assert {e["columna"] for e in carga["errores"]} >= {"horas_efectivas", "horas_disponibles"}


def test_cada_error_dice_fila_columna_y_motivo_y_no_se_puede_aplicar(client):
    filas = [
        {"area": "Ventas", "periodo": "2026-09", "horas_efectivas": 900, "horas_disponibles": 1000,
         "entregables_planificados": 10, "entregables_completados": 8},  # correcta
        {"area": "Marte", "periodo": "2026-09", "horas_efectivas": 1, "horas_disponibles": 2,
         "entregables_planificados": 1, "entregables_completados": 1},
        {"area": "Finanzas", "periodo": "2031-01", "horas_efectivas": "mucho", "horas_disponibles": 2,
         "entregables_planificados": 1, "entregables_completados": 1},
        {"area": "Almacén", "periodo": "2026-09", "horas_efectivas": 50, "horas_disponibles": 40,
         "entregables_planificados": 1, "entregables_completados": 3},
        {"area": "ventas", "periodo": "2026-09", "horas_efectivas": 1, "horas_disponibles": 2,
         "entregables_planificados": 1, "entregables_completados": 1},  # repetida (sin importar mayusculas)
    ]
    carga = subir(client, "productividad", csv(filas)).json()
    assert carga["estado"] == "con_errores" and carga["filas"] == 5
    errores = {}
    for e in carga["errores"]:
        errores.setdefault((e["fila"], e["columna"]), []).append(e["mensaje"])
    assert "'Marte'" in errores[(3, "area")][0] and "no existe" in errores[(3, "area")][0]
    assert "mes futuro" in errores[(4, "periodo")][0]
    assert "no es un número" in errores[(4, "horas_efectivas")][0]
    assert errores[(5, None)] == ["Hay más horas efectivas que disponibles", "Hay más entregables completados que planificados"]
    assert "repetido" in errores[(6, None)][0]
    assert not any(fila == 2 for fila, _ in errores)

    r = client.post(f"/cargas/{carga['id']}/aplicar")
    assert r.status_code == 422 and "corrige el archivo" in r.json()["detail"]
    assert client.post(f"/cargas/{carga['id']}/descartar").json()["estado"] == "descartada"


def test_desempeno_de_un_empleado_que_no_existe(client):
    carga = subir(client, "desempeno", csv([{"codigo_empleado": "E9999", "periodo": "2026-09", "metas_asignadas": 5,
                                            "metas_logradas": 4, "calificacion": 4}])).json()
    assert "carga primero la plantilla de personal" in carga["errores"][0]["mensaje"]


def test_los_datos_personales_se_descartan_y_nunca_se_muestran(client):
    contenido, nombre = ejemplo(client, "hris")
    assert "nombre_completo" in pd.read_excel(io.BytesIO(contenido)).columns  # como lo exporta un HRIS real
    carga = subir(client, "hris", contenido, nombre).json()
    assert carga["estado"] == "validada", carga["errores"][:3]
    assert {"columna": "nombre_completo", "motivo": "dato personal: no se guarda"} in carga["descartadas"]
    assert {"columna": "puesto", "motivo": "no la usa ningún indicador"} in carga["descartadas"]
    muestra = carga["resultado"]["muestra"]
    assert muestra["columnas"] == ["codigo", "area", "fecha_ingreso", "fecha_baja", "tipo_baja"]  # en orden
    assert len(muestra["filas"]) == 8 and all(len(f) == 5 for f in muestra["filas"])
    assert len(carga["sha256"]) == 64
    with engine.connect() as conn:
        guardado = conn.execute(text("SELECT datos::text FROM cargas WHERE id = :i"), {"i": carga["id"]}).scalar()
    assert "nombre_completo" not in guardado
    client.post(f"/cargas/{carga['id']}/descartar")


# ------------------------------------------------------ el mes completo
def test_cargar_el_mes_siguiente_completo_lo_lleva_al_tablero(client):
    """Las seis fuentes de septiembre, en orden, como lo haria RRHH."""
    for fuente in ("hris", "ats", "desempeno", "capacitacion", "clima", "productividad"):
        contenido, nombre = ejemplo(client, fuente)
        assert nombre == f"{fuente}-2026-09.xlsx"
        carga = subir(client, fuente, contenido, nombre).json()
        assert carga["estado"] == "validada", (fuente, carga["errores"][:3])
        r = client.post(f"/cargas/{carga['id']}/aplicar")
        assert r.status_code == 200, r.text
        aplicada = r.json()
        assert aplicada["estado"] == "aplicada" and aplicada["aplicada_por"] == "pruebas_rrhh"
        conciliacion = aplicada["resultado"]["conciliacion"]
        assert conciliacion and all(c["cuadra"] for c in conciliacion), (fuente, conciliacion)
        if fuente == "hris":
            assert aplicada["resultado"]["nuevas"] >= 1  # altas del mes
            assert aplicada["resultado"]["actualizadas"] > 300  # la plantilla que ya estaba

    assert client.get("/periodos").json()[-1] == "2026-09"
    kpis = client.get("/kpis", params={"periodo": "2026-09", "area_id": 0}).json()
    assert {k["indicador"] for k in kpis} >= {"rotacion_total", "enps", "indice_productividad", "cumplimiento_metas"}
    # septiembre ya esta completo y octubre sigue en curso: no hay mas meses que simular
    r = client.get("/cargas/ejemplos/hris")
    assert r.status_code == 422 and "Ya están cargados" in r.json()["detail"]

    historial = client.get("/cargas").json()
    assert [c["fuente"] for c in historial[:6]] == ["productividad", "clima", "capacitacion", "desempeno", "ats", "hris"]
    assert "datos" not in historial[0]


def test_volver_a_cargar_el_mismo_archivo_actualiza_sin_duplicar(client):
    filas = [{"area": "Ventas", "periodo": "2026-08", "horas_efectivas": 10000, "horas_disponibles": 15000,
              "entregables_planificados": 200, "entregables_completados": 180}]
    for _ in range(2):
        carga = subir(client, "productividad", csv(filas)).json()
        assert carga["resultado"]["previo"]["existentes"] == 1
        aplicada = client.post(f"/cargas/{carga['id']}/aplicar").json()
        assert aplicada["resultado"]["nuevas"] == 0 and aplicada["resultado"]["actualizadas"] == 1
    assert client.post(f"/cargas/{carga['id']}/aplicar").status_code == 422  # ya aplicada
