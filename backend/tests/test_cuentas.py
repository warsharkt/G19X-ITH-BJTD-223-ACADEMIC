"""Pruebas de la administracion de cuentas con bitacora y de la verificacion
en dos pasos (pasos 6.1 y 6.2; RF-06, RF-11, RF-12).

Como en test_seguridad.py, sin el atajo de sesion: usuarios reales (prefijo
zz_cta_, se borran al final), su contrasena y su token. El MFA obligatorio
esta apagado en conftest; las pruebas de MFA lo encienden.
"""
import time

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import seguridad
from app.database import engine
from app.main import app
from app.seguridad import INTENTOS_MAXIMOS, crear_usuario, usuario_actual

CLAVE = "Clave-de-prueba-123"
PREFIJO = "zz_cta_"


@pytest.fixture(autouse=True)
def sin_atajo_de_sesion(monkeypatch):
    app.dependency_overrides.pop(usuario_actual, None)
    monkeypatch.setenv("JWT_SECRETO", "s" * 48)


@pytest.fixture()
def con_mfa(monkeypatch):
    monkeypatch.setenv("MFA_OBLIGATORIO", "direccion,admin_ti,rrhh")


@pytest.fixture(autouse=True)
def cuentas():
    """TI, RRHH y un gerente de Ventas, nuevos en cada prueba."""
    seguridad.asegurar_tabla()

    def borrar():
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM usuarios WHERE usuario LIKE :p"), {"p": PREFIJO + "%"})

    borrar()
    with engine.connect() as conn:
        ventas = conn.execute(text("SELECT id FROM areas WHERE nombre = 'Ventas'")).scalar_one()
    ids = {
        "ti": crear_usuario(PREFIJO + "ti", "Soporte TI", "admin_ti", CLAVE),
        "ti2": crear_usuario(PREFIJO + "ti2", "Soporte TI 2", "admin_ti", CLAVE),
        "rrhh": crear_usuario(PREFIJO + "rrhh", "Ana RRHH", "rrhh", CLAVE),
        "ger": crear_usuario(PREFIJO + "ger", "Luis Ventas", "gerente", CLAVE, ventas),
    }
    yield {"ids": ids, "ventas": ventas}
    borrar()


@pytest.fixture()
def client():
    return TestClient(app)


def entrar(client, nombre, clave=CLAVE):
    return client.post("/auth/login", data={"username": PREFIJO + nombre, "password": clave})


def token(client, nombre, clave=CLAVE):
    r = entrar(client, nombre, clave)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def bitacora(usuario):
    return [(c["accion"], c["hecho_por"], c["detalle"]) for c in reversed(seguridad.cambios(100, usuario))]


# ===================================================== cuentas desde el panel
def test_ti_crea_una_cuenta_con_contrasena_temporal(client):
    ti = token(client, "ti")
    r = client.post("/usuarios", headers=ti, json={
        "usuario": PREFIJO + "nueva", "nombre": "Eva Nueva", "rol": "direccion", "correo": "Eva@Empresa.com",
    })
    assert r.status_code == 201
    temporal = r.json()["contrasena_temporal"]
    cuenta = r.json()["cuenta"]
    assert cuenta["debe_cambiar_contrasena"] is True and cuenta["correo"] == "eva@empresa.com"
    assert len(temporal) == 14 and "contrasena" not in str(bitacora(PREFIJO + "nueva"))
    assert bitacora(PREFIJO + "nueva") == [
        ("crear", PREFIJO + "ti", {"nombre": "Eva Nueva", "rol": "direccion", "area_id": None, "correo": "eva@empresa.com"})
    ]

    # con la temporal solo puede cambiarla
    eva = token(client, "nueva", temporal)
    yo = client.get("/auth/yo", headers=eva).json()
    assert yo["pendiente"] == "cambiar_contrasena"
    r = client.get("/kpis", headers=eva)
    assert r.status_code == 403 and "contraseña temporal" in r.json()["detail"]

    mala = client.post("/auth/contrasena", headers=eva, json={"actual": "no-es", "nueva": "Mi-clave-propia-1"})
    assert mala.status_code == 422 and "actual no es correcta" in mala.json()["detail"]
    r = client.post("/auth/contrasena", headers=eva, json={"actual": temporal, "nueva": "Mi-clave-propia-1"})
    assert r.status_code == 200
    nuevo = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/kpis", headers=nuevo).status_code == 200
    assert client.get("/auth/yo", headers=eva).status_code == 401  # la sesion vieja se cierra
    assert entrar(client, "nueva", temporal).status_code == 401
    assert bitacora(PREFIJO + "nueva")[-1][:2] == ("cambiar_contrasena", PREFIJO + "nueva")


@pytest.mark.parametrize("rol", ["rrhh", "ger"])
def test_solo_ti_administra_cuentas(client, cuentas, rol):
    h = token(client, rol)
    assert client.post("/usuarios", headers=h, json={"usuario": PREFIJO + "x", "nombre": "X", "rol": "rrhh"}).status_code == 403
    assert client.patch(f"/usuarios/{cuentas['ids']['ti']}", headers=h, json={"activo": False}).status_code == 403
    assert client.post(f"/usuarios/{cuentas['ids']['ti']}/contrasena", headers=h).status_code == 403
    assert client.post(f"/usuarios/{cuentas['ids']['ti']}/mfa/reiniciar", headers=h).status_code == 403


def test_rrhh_puede_auditar_cuentas_y_el_gerente_no(client):
    rrhh, ger = token(client, "rrhh"), token(client, "ger")
    nombres = {c["usuario"] for c in client.get("/usuarios", headers=rrhh).json()}
    assert {PREFIJO + "ti", PREFIJO + "ger"} <= nombres
    assert client.get("/usuarios/cambios", headers=rrhh, params={"usuario": PREFIJO + "ger"}).json()[0]["accion"] == "crear"
    assert client.get("/usuarios", headers=ger).status_code == 403
    assert client.get("/usuarios/cambios", headers=ger).status_code == 403


def test_cambiar_rol_quita_el_area_y_queda_en_la_bitacora(client, cuentas):
    ti = token(client, "ti")
    r = client.patch(f"/usuarios/{cuentas['ids']['ger']}", headers=ti, json={"rol": "rrhh", "nombre": "Luis RRHH"})
    assert r.status_code == 200
    assert r.json()["rol"] == "rrhh" and r.json()["area_id"] is None
    accion, por, detalle = bitacora(PREFIJO + "ger")[-1]
    assert (accion, por) == ("modificar", PREFIJO + "ti")
    assert detalle == {"rol": ["gerente", "rrhh"], "area_id": [cuentas["ventas"], None], "nombre": ["Luis Ventas", "Luis RRHH"]}

    r = client.patch(f"/usuarios/{cuentas['ids']['ger']}", headers=ti, json={"rol": "gerente"})
    assert r.status_code == 422 and "necesita un area" in r.json()["detail"]
    assert client.patch("/usuarios/999999", headers=ti, json={"nombre": "X"}).status_code == 404


def test_nadie_cambia_su_propio_rol_ni_se_desactiva(client, cuentas):
    ti = token(client, "ti")
    for cambio in ({"rol": "rrhh"}, {"activo": False}):
        r = client.patch(f"/usuarios/{cuentas['ids']['ti']}", headers=ti, json=cambio)
        assert r.status_code == 422 and "tu propio rol" in r.json()["detail"]
    # su nombre si
    assert client.patch(f"/usuarios/{cuentas['ids']['ti']}", headers=ti, json={"nombre": "TI Central"}).status_code == 200


def test_desactivar_corta_la_sesion_y_se_puede_reactivar(client, cuentas):
    ti, ger = token(client, "ti"), token(client, "ger")
    r = client.patch(f"/usuarios/{cuentas['ids']['ger']}", headers=ti, json={"activo": False})
    assert r.status_code == 200 and r.json()["activo"] is False
    assert client.get("/auth/yo", headers=ger).status_code == 401
    assert entrar(client, "ger").status_code == 401
    client.patch(f"/usuarios/{cuentas['ids']['ger']}", headers=ti, json={"activo": True})
    assert entrar(client, "ger").status_code == 200
    assert [a for a, _, _ in bitacora(PREFIJO + "ger")][-2:] == ["desactivar", "reactivar"]


def test_restablecer_contrasena_desbloquea_y_cierra_sesiones(client, cuentas):
    ger = token(client, "ger")
    for _ in range(INTENTOS_MAXIMOS):
        entrar(client, "ger", "no-es-la-clave")
    assert entrar(client, "ger").status_code == 429

    ti = token(client, "ti")
    r = client.post(f"/usuarios/{cuentas['ids']['ger']}/contrasena", headers=ti)
    temporal = r.json()["contrasena_temporal"]
    assert client.get("/auth/yo", headers=ger).status_code == 401  # la sesion anterior ya no sirve
    assert entrar(client, "ger").status_code == 401                # ni la contrasena anterior
    nuevo = token(client, "ger", temporal)
    assert client.get("/auth/yo", headers=nuevo).json()["pendiente"] == "cambiar_contrasena"
    assert bitacora(PREFIJO + "ger")[-1][:2] == ("restablecer_contrasena", PREFIJO + "ti")

    propia = client.post(f"/usuarios/{cuentas['ids']['ti']}/contrasena", headers=ti)
    assert propia.status_code == 422 and "Mi cuenta" in propia.json()["detail"]


def test_la_consola_queda_en_la_bitacora():
    seguridad.cambiar_correo(PREFIJO + "rrhh", "ana@empresa.com", por="consola:warsh")
    assert bitacora(PREFIJO + "rrhh")[-1] == ("modificar", "consola:warsh", {"correo": [None, "ana@empresa.com"]})


# ================================================================ MFA
def configurar(client, h):
    """Activa el MFA de la sesion h. Devuelve (secreto, codigos de respaldo)."""
    r = client.post("/auth/mfa/configurar", headers=h)
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["qr"].startswith("data:image/svg+xml;base64,")
    assert datos["uri"].startswith("otpauth://totp/") and datos["secreto"] in datos["uri"]
    r = client.post("/auth/mfa/activar", headers=h, json={"codigo": pyotp.TOTP(datos["secreto"]).now()})
    assert r.status_code == 200, r.text
    return datos["secreto"], r.json()["codigos"]


def codigo_siguiente(secreto):
    """El codigo de los proximos 30 s (aun valido): el actual ya se uso al activar."""
    return pyotp.TOTP(secreto).at(int(time.time()) + 30)


def test_mfa_obligatorio_para_rrhh_bloquea_hasta_configurarlo(client, con_mfa):
    h = token(client, "rrhh")
    yo = client.get("/auth/yo", headers=h).json()
    assert yo["pendiente"] == "configurar_mfa" and yo["mfa_obligatorio"] is True
    r = client.get("/kpis", headers=h)
    assert r.status_code == 403 and "dos pasos" in r.json()["detail"]

    mal = client.post("/auth/mfa/configurar", headers=h).json()
    r = client.post("/auth/mfa/activar", headers=h, json={"codigo": "000000"})
    assert r.status_code == 422 and "no es correcto" in r.json()["detail"]
    r = client.post("/auth/mfa/activar", headers=h, json={"codigo": pyotp.TOTP(mal["secreto"]).now()})
    codigos = r.json()["codigos"]
    assert len(codigos) == 10 and len(set(codigos)) == 10

    yo = client.get("/auth/yo", headers=h).json()
    assert yo["pendiente"] is None and yo["mfa_activo"] and yo["codigos_respaldo_restantes"] == 10
    assert client.get("/kpis", headers=h).status_code == 200
    assert bitacora(PREFIJO + "rrhh")[-1][:2] == ("activar_mfa", PREFIJO + "rrhh")
    assert client.post("/auth/mfa/configurar", headers=h).status_code == 409  # ya esta activo


def test_el_gerente_no_esta_obligado(client, con_mfa):
    yo = client.get("/auth/yo", headers=token(client, "ger")).json()
    assert yo["pendiente"] is None and yo["mfa_obligatorio"] is False


def test_entrar_con_mfa_pide_el_codigo(client, con_mfa):
    secreto, _ = configurar(client, token(client, "rrhh"))
    r = entrar(client, "rrhh")
    assert r.status_code == 200 and r.json()["mfa_requerido"] is True and r.json()["access_token"] is None
    paso = r.json()["mfa_token"]

    # el token del paso intermedio no sirve como sesion
    assert client.get("/auth/yo", headers={"Authorization": f"Bearer {paso}"}).status_code == 401
    r = client.post("/auth/mfa", json={"mfa_token": paso, "codigo": "123456"})
    assert r.status_code == 401 and "no es correcto" in r.json()["detail"]

    codigo = codigo_siguiente(secreto)
    r = client.post("/auth/mfa", json={"mfa_token": paso, "codigo": codigo})
    assert r.status_code == 200
    sesion = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/kpis", headers=sesion).status_code == 200
    # el mismo codigo no se puede volver a usar, aunque siga vigente
    otro = entrar(client, "rrhh").json()["mfa_token"]
    assert client.post("/auth/mfa", json={"mfa_token": otro, "codigo": codigo}).status_code == 401
    # y el token de sesion no sirve para el paso de MFA
    assert client.post("/auth/mfa", json={"mfa_token": r.json()["access_token"], "codigo": codigo}).status_code == 401


def test_codigo_de_respaldo_sirve_una_vez(client, con_mfa):
    _, codigos = configurar(client, token(client, "rrhh"))
    paso = entrar(client, "rrhh").json()["mfa_token"]
    r = client.post("/auth/mfa", json={"mfa_token": paso, "codigo": codigos[0].upper().replace("-", " ")})
    assert r.status_code == 200  # sin importar mayusculas, espacios o guion
    sesion = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/auth/yo", headers=sesion).json()["codigos_respaldo_restantes"] == 9
    paso = entrar(client, "rrhh").json()["mfa_token"]
    assert client.post("/auth/mfa", json={"mfa_token": paso, "codigo": codigos[0]}).status_code == 401
    assert bitacora(PREFIJO + "rrhh")[-1][0] == "usar_codigo_respaldo"


def test_probar_codigos_bloquea_aunque_se_repita_la_contrasena(client, con_mfa):
    """La contrasena correcta no reinicia el contador mientras falte el codigo."""
    configurar(client, token(client, "rrhh"))
    paso = entrar(client, "rrhh").json()["mfa_token"]
    for _ in range(INTENTOS_MAXIMOS - 1):
        client.post("/auth/mfa", json={"mfa_token": paso, "codigo": "000000"})
    paso = entrar(client, "rrhh").json()["mfa_token"]  # contrasena correcta otra vez
    client.post("/auth/mfa", json={"mfa_token": paso, "codigo": "000000"})
    r = entrar(client, "rrhh")
    assert r.status_code == 429 and "bloqueada" in r.json()["detail"]


def test_ti_reinicia_el_mfa_de_quien_perdio_el_telefono(client, cuentas, con_mfa):
    secreto, _ = configurar(client, token(client, "rrhh"))
    paso = entrar(client, "rrhh").json()["mfa_token"]
    sesion = client.post("/auth/mfa", json={"mfa_token": paso, "codigo": codigo_siguiente(secreto)}).json()["access_token"]

    secreto_ti, _ = configurar(client, token(client, "ti"))  # TI tambien esta obligado
    paso = entrar(client, "ti").json()["mfa_token"]
    ti = {"Authorization": "Bearer " + client.post(
        "/auth/mfa", json={"mfa_token": paso, "codigo": codigo_siguiente(secreto_ti)}
    ).json()["access_token"]}

    r = client.post(f"/usuarios/{cuentas['ids']['rrhh']}/mfa/reiniciar", headers=ti)
    assert r.status_code == 200 and r.json()["mfa_activo"] is False
    assert client.get("/auth/yo", headers={"Authorization": f"Bearer {sesion}"}).status_code == 401
    r = entrar(client, "rrhh")  # ya no pide codigo: debe configurarlo de nuevo
    assert r.json()["mfa_requerido"] is False
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/auth/yo", headers=h).json()["pendiente"] == "configurar_mfa"
    assert bitacora(PREFIJO + "rrhh")[-1][:2] == ("reiniciar_mfa", PREFIJO + "ti")

    propio = client.post(f"/usuarios/{cuentas['ids']['ti']}/mfa/reiniciar", headers=ti)
    assert propio.status_code == 422 and "propia" in propio.json()["detail"]
