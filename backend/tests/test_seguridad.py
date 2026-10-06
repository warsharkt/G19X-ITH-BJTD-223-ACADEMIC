"""Pruebas de inicio de sesion y control de acceso por rol (paso 6, RF-06).

A diferencia del resto de las pruebas, aqui NO se usa el atajo de sesion de
conftest: se crean usuarios reales (prefijo zz_prueba_, se borran al final),
se inicia sesion con su contrasena y se usa el token como lo haria el
frontend.

Requiere PostgreSQL con datos cargados (python -m scripts.seed).
"""
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import seguridad, trabajos
from app.database import engine
from app.main import app, proveedor_configurado
from app.seguridad import (
    INTENTOS_MAXIMOS,
    ErrorDeUsuario,
    cambiar_contrasena,
    crear_usuario,
    hash_contrasena,
    usuario_actual,
    verificar_contrasena,
)

CLAVE = "Clave-de-prueba-123"
PREFIJO = "zz_prueba_"


@pytest.fixture(autouse=True)
def sin_atajo_de_sesion(monkeypatch):
    """Quita el usuario fijo de conftest y pone un secreto de prueba."""
    app.dependency_overrides.pop(usuario_actual, None)
    monkeypatch.setenv("JWT_SECRETO", "s" * 48)
    monkeypatch.delenv("JWT_MINUTOS", raising=False)


@pytest.fixture(scope="module")
def areas():
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT nombre, id FROM areas")).all())


@pytest.fixture(scope="module")
def usuarios(areas):
    """Un usuario de cada rol; se borran al terminar el modulo."""
    seguridad.asegurar_tabla()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM usuarios WHERE usuario LIKE :p"), {"p": PREFIJO + "%"})
    datos = {
        "direccion": (None,),
        "rrhh": (None,),
        "gerente": (areas["Ventas"],),
        "admin_ti": (None,),
    }
    for rol, (area_id,) in datos.items():
        crear_usuario(PREFIJO + rol, f"Prueba {rol}", rol, CLAVE, area_id)
    yield {rol: PREFIJO + rol for rol in datos}
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


def entrar(client, usuario, clave=CLAVE):
    return client.post("/auth/login", data={"username": usuario, "password": clave})


@pytest.fixture()
def como(client, usuarios):
    """como("gerente") -> encabezados con el token de ese rol."""
    def _como(rol):
        r = entrar(client, usuarios[rol])
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return _como


# ------------------------------------------------------------- contrasenas
def test_la_contrasena_se_guarda_como_hash_con_sal():
    a, b = hash_contrasena(CLAVE), hash_contrasena(CLAVE)
    assert a != b and CLAVE not in a  # sal distinta; la contrasena no aparece
    assert verificar_contrasena(CLAVE, a) and verificar_contrasena(CLAVE, b)
    assert not verificar_contrasena("otra-clave-123", a)
    assert not verificar_contrasena(CLAVE, "basura")


@pytest.mark.parametrize(
    "datos, mensaje",
    [
        (dict(rol="rrhh", contrasena="corta1"), "al menos"),
        (dict(rol="rrhh", contrasena="zz_prueba_x-1234567"), "nombre de usuario"),
        (dict(rol="jefe", contrasena=CLAVE), "no valido"),
        (dict(rol="gerente", contrasena=CLAVE), "necesita un area"),
        (dict(rol="gerente", contrasena=CLAVE, area_id=0), "necesita un area"),
        (dict(rol="rrhh", contrasena=CLAVE, area_id=1), "Solo los gerentes"),
        (dict(rol="gerente", contrasena=CLAVE, area_id=999), "no existe"),
    ],
)
def test_crear_usuario_valida_los_datos(datos, mensaje):
    with pytest.raises(ErrorDeUsuario, match=mensaje):
        crear_usuario(PREFIJO + "x", "X", **datos)


def test_no_se_repiten_usuarios(usuarios):
    with pytest.raises(ErrorDeUsuario, match="ya existe"):
        crear_usuario(usuarios["rrhh"].upper(), "Otra", "rrhh", CLAVE)  # sin importar mayusculas


# ------------------------------------------------------------------ sesion
def test_health_y_login_no_requieren_sesion(client):
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("ruta", ["/areas", "/periodos", "/umbrales", "/kpis", "/narrativas", "/auth/yo"])
def test_sin_sesion_todo_lo_demas_responde_401(client, ruta):
    assert client.get(ruta).status_code == 401


def test_login_y_quien_soy(client, usuarios, areas):
    r = entrar(client, usuarios["gerente"])
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"
    yo = client.get("/auth/yo", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
    assert yo["rol"] == "gerente" and yo["area_id"] == areas["Ventas"]
    assert yo["areas_permitidas"] == [areas["Ventas"]]


def test_usuario_inexistente_y_contrasena_mala_dan_el_mismo_mensaje(client, usuarios):
    malo = entrar(client, usuarios["rrhh"], "no-es-la-clave")
    inexistente = entrar(client, PREFIJO + "nadie", CLAVE)
    assert malo.status_code == inexistente.status_code == 401
    assert malo.json() == inexistente.json()  # no revela que cuentas existen


def test_bloqueo_por_intentos_fallidos(client, usuarios):
    usuario = PREFIJO + "bloqueo"
    crear_usuario(usuario, "Bloqueo", "rrhh", CLAVE)
    for _ in range(INTENTOS_MAXIMOS):
        assert entrar(client, usuario, "no-es-la-clave").status_code == 401
    r = entrar(client, usuario, CLAVE)  # ni con la contrasena correcta
    assert r.status_code == 429 and "bloqueada" in r.json()["detail"]
    cambiar_contrasena(usuario, CLAVE + "-nueva")  # el administrador la restablece
    assert entrar(client, usuario, CLAVE + "-nueva").status_code == 200


def test_un_acierto_reinicia_el_contador_de_fallos(client, usuarios):
    usuario = PREFIJO + "contador"
    crear_usuario(usuario, "Contador", "rrhh", CLAVE)
    for _ in range(INTENTOS_MAXIMOS - 1):
        entrar(client, usuario, "no-es-la-clave")
    assert entrar(client, usuario, CLAVE).status_code == 200
    for _ in range(INTENTOS_MAXIMOS - 1):
        entrar(client, usuario, "no-es-la-clave")
    assert entrar(client, usuario, CLAVE).status_code == 200


def test_token_vencido_alterado_o_de_otro_secreto_no_sirve(client, usuarios, monkeypatch):
    monkeypatch.setenv("JWT_MINUTOS", "-1")
    vencido = entrar(client, usuarios["rrhh"]).json()["access_token"]
    monkeypatch.delenv("JWT_MINUTOS")
    bueno = entrar(client, usuarios["rrhh"]).json()["access_token"]
    ajeno = jwt.encode({"sub": "1", "exp": 9999999999}, "x" * 48, algorithm="HS256")
    for token in (vencido, bueno[:-2] + "xx", ajeno, "basura"):
        r = client.get("/auth/yo", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, token
    assert client.get("/auth/yo", headers={"Authorization": f"Bearer {bueno}"}).status_code == 200


def test_desactivar_un_usuario_corta_su_sesion_de_inmediato(client, usuarios):
    usuario = PREFIJO + "baja"
    crear_usuario(usuario, "Baja", "rrhh", CLAVE)
    encabezado = {"Authorization": f"Bearer {entrar(client, usuario).json()['access_token']}"}
    assert client.get("/auth/yo", headers=encabezado).status_code == 200
    with engine.begin() as conn:
        conn.execute(text("UPDATE usuarios SET activo = false WHERE usuario = :u"), {"u": usuario})
    assert client.get("/auth/yo", headers=encabezado).status_code == 401
    assert entrar(client, usuario).status_code == 401


def test_sin_secreto_configurado_el_login_avisa(client, usuarios, monkeypatch):
    monkeypatch.setenv("JWT_SECRETO", "corto")
    r = entrar(client, usuarios["rrhh"])
    assert r.status_code == 503 and "JWT_SECRETO" in r.json()["detail"]


# ---------------------------------------------------------------- permisos
def test_direccion_solo_ve_el_consolidado(client, como, areas):
    h = como("direccion")
    assert [a["id"] for a in client.get("/areas", headers=h).json()] == [0]
    assert client.get("/kpis", headers=h).status_code == 200  # por defecto, corporativo
    assert client.get("/kpis", params={"area_id": areas["Ventas"]}, headers=h).status_code == 403
    assert client.get("/kpis/serie/enps", params={"area_id": areas["Transporte"]}, headers=h).status_code == 403


def test_gerente_solo_ve_su_area(client, como, areas):
    h = como("gerente")  # gerente de Ventas
    assert [a["id"] for a in client.get("/areas", headers=h).json()] == [areas["Ventas"]]
    filas = client.get("/kpis", headers=h).json()  # por defecto, su area
    assert filas and {f["area"] for f in filas} == {"Ventas"}
    assert client.get("/kpis/serie/enps", headers=h).status_code == 200
    for otra in (0, areas["Transporte"]):
        assert client.get("/kpis", params={"area_id": otra}, headers=h).status_code == 403
        assert client.get("/kpis/serie/enps", params={"area_id": otra}, headers=h).status_code == 403


def test_rrhh_ve_todo(client, como, areas):
    h = como("rrhh")
    assert len(client.get("/areas", headers=h).json()) == len(areas) + 1
    for area_id in [0, *areas.values()]:
        assert client.get("/kpis", params={"area_id": area_id}, headers=h).status_code == 200


def test_admin_ti_ve_catalogos_pero_no_datos_de_colaboradores(client, como):
    h = como("admin_ti")
    for ruta in ("/areas", "/periodos", "/umbrales"):
        assert client.get(ruta, headers=h).status_code == 200
    for ruta in ("/kpis", "/kpis/serie/enps", "/narrativas"):
        r = client.get(ruta, headers=h)
        assert r.status_code == 403 and "colaboradores" in r.json()["detail"]
    assert client.post("/narrativas", json={}, headers=h).status_code == 403


class _ProveedorQuieto:
    nombre, modelo, local = "falso", "modelo-falso", True


class _SinEjecutar:
    def submit(self, *args):
        pass  # la narrativa queda en_proceso: aqui solo importan los permisos


def test_narrativas_respetan_el_area_y_registran_quien_las_pidio(client, como, areas, monkeypatch):
    monkeypatch.setattr(trabajos, "ejecutor", _SinEjecutar())
    app.dependency_overrides[proveedor_configurado] = lambda: _ProveedorQuieto()
    try:
        gerente, rrhh, direccion = como("gerente"), como("rrhh"), como("direccion")

        propia = client.post("/narrativas", json={}, headers=gerente)  # por defecto, su area
        assert propia.status_code == 202
        assert propia.json()["area_id"] == areas["Ventas"]
        assert propia.json()["solicitada_por"] == PREFIJO + "gerente"  # bitacora RF-11
        assert client.post("/narrativas", json={"area_id": areas["Transporte"]}, headers=gerente).status_code == 403

        de_ti = client.post("/narrativas", json={"area_id": areas["Transporte"]}, headers=rrhh).json()
        assert client.get(f"/narrativas/{de_ti['id']}", headers=gerente).status_code == 403
        assert client.get(f"/narrativas/{de_ti['id']}", headers=direccion).status_code == 403
        assert client.get(f"/narrativas/{propia.json()['id']}", headers=gerente).status_code == 200

        historial = client.get("/narrativas", params={"limite": 100}, headers=gerente).json()
        assert historial and {n["area_id"] for n in historial} == {areas["Ventas"]}
        ids_rrhh = {n["id"] for n in client.get("/narrativas", params={"limite": 100}, headers=rrhh).json()}
        assert {de_ti["id"], propia.json()["id"]} <= ids_rrhh
    finally:
        app.dependency_overrides.pop(proveedor_configurado, None)
