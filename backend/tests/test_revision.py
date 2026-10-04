"""Pruebas de la revision humana de narrativas (paso 8, RF-05 y RF-11).

Como en test_seguridad.py, se usan usuarios reales (prefijo zz_rev_, se
borran al final) con su contrasena y su token. Las narrativas se insertan
directo en la tabla: aqui solo importa el flujo de revision, no el modelo.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import seguridad, trabajos
from app.database import engine
from app.main import app
from app.seguridad import crear_usuario, usuario_actual

CLAVE = "Clave-de-prueba-123"
PREFIJO = "zz_rev_"
COMENTARIO = "Faltan las cifras de Ventas en el segundo hallazgo"


@pytest.fixture(autouse=True)
def sin_atajo_de_sesion(monkeypatch):
    app.dependency_overrides.pop(usuario_actual, None)
    monkeypatch.setenv("JWT_SECRETO", "s" * 48)


@pytest.fixture(scope="module")
def usuarios():
    """Dos personas de RRHH (una solicita, otra revisa) y una de cada otro rol."""
    seguridad.asegurar_tabla()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM usuarios WHERE usuario LIKE :p"), {"p": PREFIJO + "%"})
        ventas = conn.execute(text("SELECT id FROM areas WHERE nombre = 'Ventas'")).scalar_one()
    datos = {"rrhh": None, "rrhh2": None, "direccion": None, "gerente": ventas, "admin_ti": None}
    for nombre, area_id in datos.items():
        crear_usuario(PREFIJO + nombre, f"Prueba {nombre}", nombre.rstrip("2"), CLAVE, area_id)
    yield {nombre: PREFIJO + nombre for nombre in datos}
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM usuarios WHERE usuario LIKE :p"), {"p": PREFIJO + "%"})


@pytest.fixture()
def client():
    trabajos.asegurar_tabla()
    with engine.connect() as conn:
        ultimo = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM narrativas")).scalar()
    yield TestClient(app)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM narrativas WHERE id > :u"), {"u": ultimo})


@pytest.fixture()
def como(client, usuarios):
    def _como(nombre):
        r = client.post("/auth/login", data={"username": usuarios[nombre], "password": CLAVE})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return _como


@pytest.fixture()
def narrativa(client, usuarios):
    """Crea una narrativa del consolidado y devuelve su id.

    narrativa(estado="lista", solicitada_por="rrhh")"""
    def _crear(estado="lista", solicitada_por="rrhh"):
        with engine.begin() as conn:
            return conn.execute(
                text(
                    "INSERT INTO narrativas (area_id, periodo, estado, solicitada_por, terminada_en) "
                    "VALUES (0, '2026-08-01', :e, :s, CASE WHEN :e = 'en_proceso' THEN NULL ELSE now() END) "
                    "RETURNING id"
                ),
                {"e": estado, "s": usuarios[solicitada_por]},
            ).scalar_one()
    return _crear


def revisar(client, id_, encabezados, decision="aprobada", comentario=None):
    return client.post(
        f"/narrativas/{id_}/revision", json={"decision": decision, "comentario": comentario}, headers=encabezados
    )


def test_otra_persona_de_rrhh_aprueba_y_queda_en_la_bitacora(client, como, narrativa, usuarios):
    id_ = narrativa()
    nueva = client.get(f"/narrativas/{id_}", headers=como("rrhh")).json()
    assert nueva["revision"] == "pendiente" and nueva["revisada_por"] is None

    r = revisar(client, id_, como("rrhh2"), comentario="  Revisado contra el tablero  ")
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["revision"] == "aprobada"
    assert datos["revisada_por"] == usuarios["rrhh2"]  # bitacora RF-11: quien aprobo
    assert datos["revisada_en"] is not None
    assert datos["comentario_revision"] == "Revisado contra el tablero"
    assert datos["solicitada_por"] == usuarios["rrhh"]
    assert client.get(f"/narrativas/{id_}", headers=como("rrhh")).json()["revision"] == "aprobada"


def test_nadie_aprueba_lo_que_el_mismo_solicito(client, como, narrativa):
    id_ = narrativa(solicitada_por="rrhh")
    r = revisar(client, id_, como("rrhh"))
    assert r.status_code == 403
    assert "tú solicitaste" in r.json()["detail"]
    assert client.get(f"/narrativas/{id_}", headers=como("rrhh")).json()["revision"] == "pendiente"


@pytest.mark.parametrize("rol", ["direccion", "gerente", "admin_ti"])
def test_solo_rrhh_puede_revisar(client, como, narrativa, rol):
    id_ = narrativa(solicitada_por="rrhh")
    assert revisar(client, id_, como(rol)).status_code == 403


def test_al_rechazar_el_motivo_es_obligatorio(client, como, narrativa):
    id_ = narrativa()
    rrhh2 = como("rrhh2")
    for comentario in (None, "", "   ", "corto"):
        r = revisar(client, id_, rrhh2, "rechazada", comentario)
        assert r.status_code == 422, comentario
        assert "motivo" in str(r.json()["detail"])

    r = revisar(client, id_, rrhh2, "rechazada", COMENTARIO)
    assert r.status_code == 200
    assert r.json()["revision"] == "rechazada"
    assert r.json()["comentario_revision"] == COMENTARIO


def test_decision_desconocida_se_rechaza(client, como, narrativa):
    assert revisar(client, narrativa(), como("rrhh2"), decision="publicada").status_code == 422


def test_la_decision_es_definitiva(client, como, narrativa, usuarios):
    id_ = narrativa()
    assert revisar(client, id_, como("rrhh2")).status_code == 200
    r = revisar(client, id_, como("rrhh2"), "rechazada", COMENTARIO)
    assert r.status_code == 409
    assert usuarios["rrhh2"] in r.json()["detail"]


@pytest.mark.parametrize("estado", ["en_proceso", "error"])
def test_solo_se_revisan_narrativas_terminadas(client, como, narrativa, estado):
    r = revisar(client, narrativa(estado=estado), como("rrhh2"))
    assert r.status_code == 409
    assert "lista" in r.json()["detail"]


def test_narrativa_inexistente(client, como):
    assert revisar(client, 999_999_999, como("rrhh2")).status_code == 404


def test_las_narrativas_anteriores_al_paso_8_quedan_pendientes(client, como, narrativa):
    """El DEFAULT de la columna nueva: lo ya generado no aparece como aprobado."""
    id_ = narrativa()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT revision FROM narrativas WHERE id = :i"), {"i": id_}).scalar() == "pendiente"


def test_historial_filtra_por_revision(client, como, narrativa):
    aprobada, pendiente, rechazada, con_error = narrativa(), narrativa(), narrativa(), narrativa(estado="error")
    rrhh2 = como("rrhh2")
    revisar(client, aprobada, rrhh2)
    revisar(client, rechazada, rrhh2, "rechazada", COMENTARIO)

    def ids(revision):
        r = client.get("/narrativas", params={"revision": revision, "limite": 100}, headers=rrhh2)
        assert r.status_code == 200
        return {n["id"] for n in r.json()}

    assert pendiente in ids("pendiente")
    assert aprobada not in ids("pendiente") and rechazada not in ids("pendiente")
    assert con_error not in ids("pendiente")  # con error no hay nada que revisar
    assert aprobada in ids("aprobada") and rechazada in ids("rechazada")
    assert client.get("/narrativas", params={"revision": "otra"}, headers=rrhh2).status_code == 422


def test_dos_revisiones_simultaneas_solo_una_gana(client, como, narrativa, usuarios):
    """El UPDATE lleva las condiciones: la segunda decision no pisa a la primera."""
    id_ = narrativa()
    primero = trabajos.revisar(id_, "aprobada", usuarios["rrhh2"], None)
    assert primero["revision"] == "aprobada"
    with pytest.raises(trabajos.RevisionNoPermitida):
        trabajos.revisar(id_, "rechazada", PREFIJO + "otra_persona", COMENTARIO)
    with engine.connect() as conn:
        fila = conn.execute(
            text("SELECT revision, revisada_por FROM narrativas WHERE id = :i"), {"i": id_}
        ).one()
    assert tuple(fila) == ("aprobada", usuarios["rrhh2"])
