"""Pruebas del modo demostracion (cuentas del personal de Nordika y codigo de
MFA visible en el telefono simulado).

Las cuentas se crean y se borran en cada prueba (en la base local de pruebas;
para recuperarlas: python -m scripts.demo). El MFA obligatorio se
enciende aqui: el modo demo existe para recorrerlo sin telefono.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import demo, seguridad
from app.database import engine
from app.main import app
from app.seguridad import ErrorDeUsuario, crear_usuario, usuario_actual

CONTRASENA = "Prueba-de-demo-1"


def _borrar_cuentas():
    filtro = r"usuario LIKE 'demo\_%' OR usuario = 'zz_dem_real' OR usuario = ANY(:u)"
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM usuarios WHERE {filtro}"), {"u": list(demo.USUARIOS)})
        conn.execute(text(f"DELETE FROM usuarios_cambios WHERE {filtro}"), {"u": list(demo.USUARIOS)})


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    app.dependency_overrides.pop(usuario_actual, None)
    monkeypatch.setenv("JWT_SECRETO", "s" * 48)
    monkeypatch.setenv("MFA_OBLIGATORIO", "direccion,admin_ti,rrhh")
    monkeypatch.setenv("MODO_DEMO", "si")
    monkeypatch.setenv("MODO_DATOS", "sinteticos")
    monkeypatch.setenv("DEMO_CONTRASENA", CONTRASENA)
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
    assert client.get("/demo").json() == {"activo": False}
    with pytest.raises(ErrorDeUsuario, match="MODO_DEMO"):
        demo.preparar_cuentas("pruebas")


def test_con_datos_reales_se_niega(client, monkeypatch):
    monkeypatch.setenv("MODO_DATOS", "reales")
    assert client.get("/demo").json()["activo"] is False
    with pytest.raises(ErrorDeUsuario, match="nunca con datos reales"):
        demo.preparar_cuentas("pruebas")


@pytest.mark.parametrize("clave", [None, "", "corta"])
def test_sin_contrasena_propia_no_hay_cuentas(client, monkeypatch, clave):
    """La contrasena no viene en el codigo: quien instala la elige."""
    if clave is None:
        monkeypatch.delenv("DEMO_CONTRASENA")
    else:
        monkeypatch.setenv("DEMO_CONTRASENA", clave)
    assert client.get("/demo").json() == {"activo": False}
    with pytest.raises(ErrorDeUsuario, match="Falta DEMO_CONTRASENA"):
        demo.preparar_cuentas("pruebas")


def test_crea_una_cuenta_por_rol(client):
    hecho = demo.preparar_cuentas("consola:pruebas")
    assert hecho == [f"{c[0]}: creada" for c in demo.CUENTAS]
    assert {c[2] for c in demo.CUENTAS} == {"direccion", "rrhh", "gerente", "admin_ti"}
    assert entrar(client, "carlos.pena").status_code == 200
    assert seguridad.cambios(5, "carlos.pena")[0]["hecho_por"] == "consola:pruebas"


def test_la_pantalla_de_inicio_no_revela_cuentas_ni_contrasena(client):
    """Se ve como en produccion: la contrasena solo esta en el .env de quien instala."""
    demo.preparar_cuentas("pruebas")
    datos = client.get("/demo").json()
    assert datos == {"activo": True}
    assert CONTRASENA not in str(datos)


def test_recorre_el_mfa_completo_con_el_codigo_visible(client):
    demo.preparar_cuentas("pruebas")
    r = entrar(client, "ana.rios")
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/auth/yo", headers=h).json()["pendiente"] == "configurar_mfa"  # se exige igual

    # sin QR generado todavia no hay codigo que mostrar
    assert client.get("/demo/codigo-configuracion", headers=h).status_code == 404
    client.post("/auth/mfa/configurar", headers=h)
    codigo = client.get("/demo/codigo-configuracion", headers=h).json()
    assert len(codigo["codigo"]) == 6 and 1 <= codigo["segundos"] <= 30
    assert client.post("/auth/mfa/activar", headers=h, json={"codigo": codigo["codigo"]}).status_code == 200

    # al entrar se pide el codigo; la pantalla muestra uno que el servidor acepta
    paso = entrar(client, "ana.rios").json()
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
    h = {"Authorization": f"Bearer {entrar(client, 'carlos.pena').json()['access_token']}"}
    client.post("/auth/mfa/configurar", headers=h)
    monkeypatch.setenv("MODO_DEMO", "no")
    assert client.get("/demo/codigo-configuracion", headers=h).status_code == 404


def test_volver_a_prepararlas_las_deja_como_nuevas(client):
    demo.preparar_cuentas("pruebas")
    h = {"Authorization": f"Bearer {entrar(client, 'carlos.pena').json()['access_token']}"}
    client.post("/auth/mfa/configurar", headers=h)
    client.post("/auth/mfa/activar", headers=h, json={"codigo": client.get("/demo/codigo-configuracion", headers=h).json()["codigo"]})
    for _ in range(seguridad.INTENTOS_MAXIMOS):
        entrar(client, "ana.rios", "no-es-la-clave")
    assert entrar(client, "ana.rios").status_code == 429

    assert demo.preparar_cuentas("pruebas") == [f"{c[0]}: restablecida" for c in demo.CUENTAS]
    assert entrar(client, "ana.rios").status_code == 200        # desbloqueada
    assert entrar(client, "carlos.pena").json()["mfa_requerido"] is False  # MFA por configurar otra vez


# ------------------------------------------------- la entrada es la de siempre
def test_no_hay_entrada_sin_contrasena_ni_codigo(client):
    """La demostracion ensena como se entra de verdad: no existe un atajo."""
    demo.preparar_cuentas("pruebas")
    assert client.post("/demo/entrar", json={"usuario": "ana.rios"}).status_code == 404
    h = {"Authorization": f"Bearer {entrar(client, 'ana.rios').json()['access_token']}"}
    assert client.get("/auth/yo", headers=h).json()["pendiente"] == "configurar_mfa"
    assert client.get("/kpis", headers=h).status_code == 403


def test_las_cuentas_van_en_el_orden_del_flujo():
    assert [c[5] for c in demo.CUENTAS[:3]] == ["Analista de RRHH", "Responsable de RRHH", "Dirección General"]


def test_renombra_las_cuentas_demo_anteriores_con_su_historial(client):
    crear_usuario("demo_analista", "Eva Muñoz", "rrhh", CONTRASENA, por="consola:pruebas")
    with engine.begin() as conn:
        conn.execute(text("UPDATE usuarios_cambios SET hecho_por = 'demo_analista' WHERE usuario = 'demo_analista'"))
    hecho = demo.preparar_cuentas("pruebas")
    assert hecho[0] == "demo_analista: ahora es eva.munoz"
    assert "eva.munoz: restablecida" in hecho  # la misma cuenta, no una nueva
    assert [(c["accion"], c["hecho_por"]) for c in seguridad.cambios(50, "eva.munoz")][-2:] == [
        ("modificar", "pruebas"), ("crear", "eva.munoz")
    ]
    assert seguridad.cambios(50, "demo_analista") == []
    assert entrar(client, "demo_analista").status_code == 401


def test_prepararlas_desactiva_las_cuentas_que_ya_no_se_usan(client):
    crear_usuario("demo_rrhh2", "Eva Muñoz", "rrhh", CONTRASENA)
    hecho = demo.preparar_cuentas("pruebas")
    assert "demo_rrhh2: desactivada (ya no se usa)" in hecho
    assert entrar(client, "demo_rrhh2").status_code == 401
