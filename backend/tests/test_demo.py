"""Pruebas del modo demostracion (cuentas demo_ y codigo de MFA visible).

Las cuentas demo_ se crean y se borran en cada prueba (en la base local de
pruebas; para recuperarlas: python -m scripts.demo). El MFA obligatorio se
enciende aqui: el modo demo existe para recorrerlo sin telefono.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import demo, seguridad
from app.database import engine
from app.main import app
from app.seguridad import ErrorDeUsuario, crear_usuario, usuario_actual

CONTRASENA = demo.contrasena()


def _borrar_cuentas():
    with engine.begin() as conn:
        conn.execute(text(r"DELETE FROM usuarios WHERE usuario LIKE 'demo\_%' OR usuario = 'zz_dem_real'"))
        conn.execute(text(r"DELETE FROM usuarios_cambios WHERE usuario LIKE 'demo\_%' OR usuario = 'zz_dem_real'"))


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    app.dependency_overrides.pop(usuario_actual, None)
    monkeypatch.setenv("JWT_SECRETO", "s" * 48)
    monkeypatch.setenv("MFA_OBLIGATORIO", "direccion,admin_ti,rrhh")
    monkeypatch.setenv("MODO_DEMO", "si")
    monkeypatch.setenv("MODO_DATOS", "sinteticos")
    seguridad.asegurar_tabla()
    _borrar_cuentas()
    yield
    _borrar_cuentas()


@pytest.fixture()
def client():
    return TestClient(app)


def entrar(client, usuario, clave=CONTRASENA):
    return client.post("/auth/login", data={"username": usuario, "password": clave})


def test_apagado_por_defecto_no_muestra_nada(client, monkeypatch):
    monkeypatch.setenv("MODO_DEMO", "no")
    assert client.get("/demo").json() == {"activo": False, "contrasena": None, "cuentas": []}
    with pytest.raises(ErrorDeUsuario, match="MODO_DEMO"):
        demo.preparar_cuentas("pruebas")


def test_con_datos_reales_se_niega(client, monkeypatch):
    monkeypatch.setenv("MODO_DATOS", "reales")
    assert client.get("/demo").json()["activo"] is False
    with pytest.raises(ErrorDeUsuario, match="nunca con datos reales"):
        demo.preparar_cuentas("pruebas")


def test_crea_una_cuenta_por_rol_y_la_pantalla_las_lista(client):
    hecho = demo.preparar_cuentas("consola:pruebas")
    assert hecho == [f"{c[0]}: creada" for c in demo.CUENTAS]
    datos = client.get("/demo").json()
    assert datos["activo"] is True and datos["contrasena"] == CONTRASENA
    assert {c["rol"] for c in datos["cuentas"]} == {"direccion", "rrhh", "gerente", "admin_ti"}
    assert seguridad.cambios(5, "demo_ti")[0]["hecho_por"] == "consola:pruebas"


def test_recorre_el_mfa_completo_con_el_codigo_visible(client):
    demo.preparar_cuentas("pruebas")
    r = entrar(client, "demo_rrhh")
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/auth/yo", headers=h).json()["pendiente"] == "configurar_mfa"  # se exige igual

    # sin QR generado todavia no hay codigo que mostrar
    assert client.get("/demo/codigo-configuracion", headers=h).status_code == 404
    client.post("/auth/mfa/configurar", headers=h)
    codigo = client.get("/demo/codigo-configuracion", headers=h).json()
    assert len(codigo["codigo"]) == 6 and 1 <= codigo["segundos"] <= 30
    assert client.post("/auth/mfa/activar", headers=h, json={"codigo": codigo["codigo"]}).status_code == 200

    # al entrar se pide el codigo; la pantalla muestra uno que el servidor acepta
    paso = entrar(client, "demo_rrhh").json()
    assert paso["mfa_requerido"] is True
    visible = client.post("/demo/codigo", json={"mfa_token": paso["mfa_token"]}).json()["codigo"]
    assert visible != codigo["codigo"]  # el de la activacion ya se uso
    r = client.post("/auth/mfa", json={"mfa_token": paso["mfa_token"], "codigo": visible})
    assert r.status_code == 200
    assert client.get("/kpis", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200


def test_nunca_muestra_el_codigo_de_una_cuenta_real(client):
    crear_usuario("zz_dem_real", "Cuenta real", "rrhh", "Clave-de-prueba-123")
    h = {"Authorization": f"Bearer {entrar(client, 'zz_dem_real', 'Clave-de-prueba-123').json()['access_token']}"}
    client.post("/auth/mfa/configurar", headers=h)
    r = client.get("/demo/codigo-configuracion", headers=h)
    assert r.status_code == 404 and "Solo las cuentas de demostración" in r.json()["detail"]


def test_con_el_modo_apagado_no_hay_codigo(client, monkeypatch):
    demo.preparar_cuentas("pruebas")
    h = {"Authorization": f"Bearer {entrar(client, 'demo_ti').json()['access_token']}"}
    client.post("/auth/mfa/configurar", headers=h)
    monkeypatch.setenv("MODO_DEMO", "no")
    assert client.get("/demo/codigo-configuracion", headers=h).status_code == 404


def test_volver_a_prepararlas_las_deja_como_nuevas(client):
    demo.preparar_cuentas("pruebas")
    h = {"Authorization": f"Bearer {entrar(client, 'demo_ti').json()['access_token']}"}
    client.post("/auth/mfa/configurar", headers=h)
    client.post("/auth/mfa/activar", headers=h, json={"codigo": client.get("/demo/codigo-configuracion", headers=h).json()["codigo"]})
    for _ in range(seguridad.INTENTOS_MAXIMOS):
        entrar(client, "demo_rrhh", "no-es-la-clave")
    assert entrar(client, "demo_rrhh").status_code == 429

    assert demo.preparar_cuentas("pruebas") == [f"{c[0]}: restablecida" for c in demo.CUENTAS]
    assert entrar(client, "demo_rrhh").status_code == 200        # desbloqueada
    assert entrar(client, "demo_ti").json()["mfa_requerido"] is False  # MFA por configurar otra vez
