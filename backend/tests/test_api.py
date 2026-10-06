"""Pruebas de la API (paso 4).

Requiere: PostgreSQL arriba con datos cargados (python -m scripts.seed)
y `pip install httpx2` (lo usa el TestClient de FastAPI).
Ejecutar desde la carpeta backend:  python -m pytest -q
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import engine
from app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def id_area():
    """Busca el id de un area por su nombre (no asume el orden de los ids).

    Lee la BD directamente: este fixture se crea antes que la sesion de
    prueba (conftest), y /areas ya exige iniciar sesion."""
    with engine.connect() as conn:
        por_nombre = dict(conn.execute(text("SELECT nombre, id FROM areas")).all())
    return por_nombre.__getitem__


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


def test_areas_incluye_corporativo_y_las_6_areas(client):
    areas = client.get("/areas").json()
    assert areas[0] == {"id": 0, "nombre": "Corporativo"}
    assert {a["nombre"] for a in areas} >= {"Ventas", "Operaciones", "Transporte", "Finanzas", "Almacén", "Jurídico"}
    assert len(areas) == 7


def test_periodos(client):
    p = client.get("/periodos").json()
    assert len(p) == 24
    assert p == sorted(p)
    assert p[0] == "2024-09" and p[-1] == "2026-08"


def test_umbrales(client):
    u = client.get("/umbrales").json()
    assert len(u) == 10
    enps = next(x for x in u if x["indicador"] == "enps")
    assert enps["sentido"] == "menor_es_peor"
    assert enps["umbral_atencion"] == 10 and enps["umbral_critico"] == 0


def test_kpis_por_defecto_es_corporativo_del_ultimo_mes(client):
    filas = client.get("/kpis").json()
    assert len(filas) == 10
    assert {f["area"] for f in filas} == {"Corporativo"}
    assert {f["periodo"] for f in filas} == {"2026-08-01"}


def test_kpis_de_operaciones_en_la_crisis(client, id_area):
    r = client.get("/kpis", params={"periodo": "2026-02", "area_id": id_area("Operaciones"), "indicador": "enps"})
    assert r.status_code == 200
    [fila] = r.json()
    assert fila["valor"] < 0
    assert fila["estado"] == "rojo"
    assert fila["suprimido"] is False


def test_area_pequena_devuelve_null_no_un_numero(client, id_area):
    r = client.get("/kpis", params={"area_id": id_area("Jurídico"), "indicador": "enps"})
    [fila] = r.json()
    assert fila["valor"] is None
    assert fila["suprimido"] is True
    assert fila["estado"] == "suprimido"


def test_json_valido_sin_nan(client, id_area):
    """Si hubiera NaN, la serializacion fallaria; aqui se pide todo Jurídico."""
    r = client.get("/kpis", params={"area_id": id_area("Jurídico")})
    assert r.status_code == 200
    assert all(f["valor"] is None or isinstance(f["valor"], float) for f in r.json())


def test_serie_completa_y_ordenada(client, id_area):
    s = client.get("/kpis/serie/enps", params={"area_id": id_area("Operaciones")}).json()
    assert len(s) == 24
    periodos = [p["periodo"] for p in s]
    assert periodos == sorted(periodos)


def test_serie_con_rango(client):
    s = client.get("/kpis/serie/rotacion_total", params={"desde": "2026-03", "hasta": "2026-05"}).json()
    assert [p["periodo"] for p in s] == ["2026-03-01", "2026-04-01", "2026-05-01"]


@pytest.mark.parametrize(
    "ruta, params, codigo",
    [
        ("/kpis", {"periodo": "2030-01"}, 404),      # mes sin datos
        ("/kpis", {"periodo": "2026-13"}, 422),      # formato invalido
        ("/kpis", {"periodo": "agosto"}, 422),
        ("/kpis", {"area_id": 99}, 404),             # area inexistente
        ("/kpis", {"indicador": "inventado"}, 404),  # indicador inexistente
        ("/kpis/serie/inventado", {}, 404),
        ("/kpis/serie/enps", {"area_id": 99}, 404),
        ("/kpis/serie/enps", {"desde": "2026-1"}, 422),
    ],
)
def test_errores_claros(client, ruta, params, codigo):
    assert client.get(ruta, params=params).status_code == codigo
