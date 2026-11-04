"""Pruebas de los arreglos de la auditoria de seguridad (noviembre de 2026).

Cada bloque reproduce un hallazgo: con el codigo de antes la prueba fallaba.

  1. TI no puede crear ni apropiarse de una cuenta que firma reportes.
  2. Direccion y los gerentes no leen reportes sin firmar.
  3. Subir un archivo no deja a la API sin responder; limites de filas y zip.
  4. El bloqueo por intentos es por cuenta y origen (no se puede bloquear a
     otra persona desde fuera).
  5. Cerrar sesion invalida el token.
  7. La API se conecta a PostgreSQL sin privilegios de superusuario.

El 6 (Content-Security-Policy) y el limite por IP del 4 viven en nginx
(frontend/nginx/); se revisan con el tablero en Docker.

Usuarios reales con su contrasena (prefijo zz_end_), como test_cuentas.py.
"""
import asyncio
import inspect
import io
import json
import os
import time
from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app import cargas, seguridad
from app.database import DB_URL, engine
from app.main import app
from app.rutas import cargas as rutas_cargas
from app.seguridad import INTENTOS_MAXIMOS, ORIGENES_PARA_BLOQUEO_TOTAL, crear_usuario, usuario_actual

CLAVE = "Clave-de-prueba-123"
PREFIJO = "zz_end_"


@pytest.fixture(autouse=True)
def sin_atajo_de_sesion(monkeypatch):
    app.dependency_overrides.pop(usuario_actual, None)
    monkeypatch.setenv("JWT_SECRETO", "s" * 48)


@pytest.fixture(autouse=True)
def cuentas():
    """TI, la Responsable que firma, dos Analistas, Direccion y un gerente de Ventas."""
    seguridad.asegurar_tabla()

    def borrar():
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM narrativas WHERE solicitada_por LIKE :p"), {"p": PREFIJO + "%"})
            conn.execute(text("DELETE FROM suplencias WHERE suplente LIKE :p OR titular LIKE :p"), {"p": PREFIJO + "%"})
            conn.execute(text("DELETE FROM usuarios WHERE usuario LIKE :p"), {"p": PREFIJO + "%"})
            conn.execute(text("DELETE FROM usuarios_cambios WHERE usuario LIKE :p"), {"p": PREFIJO + "%"})

    borrar()
    with engine.connect() as conn:
        ventas = conn.execute(text("SELECT id FROM areas WHERE nombre = 'Ventas'")).scalar_one()
    ids = {
        "ti": crear_usuario(PREFIJO + "ti", "Soporte TI", "admin_ti", CLAVE),
        "resp": crear_usuario(PREFIJO + "resp", "Eva Responsable", "rrhh", CLAVE, firma_reportes=True),
        "ana": crear_usuario(PREFIJO + "ana", "Ana Analista", "rrhh", CLAVE),
        "ana2": crear_usuario(PREFIJO + "ana2", "Otra Analista", "rrhh", CLAVE),
        "dir": crear_usuario(PREFIJO + "dir", "Direccion", "direccion", CLAVE),
        "ger": crear_usuario(PREFIJO + "ger", "Gerente Ventas", "gerente", CLAVE, ventas),
    }
    yield {"ids": ids, "ventas": ventas}
    borrar()


@pytest.fixture()
def client():
    return TestClient(app)


def entrar(client, nombre, clave=CLAVE):
    return client.post("/auth/login", data={"username": PREFIJO + nombre, "password": clave})


def como(client, nombre, clave=CLAVE):
    r = entrar(client, nombre, clave)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def avisos_de_cuenta(nombre):
    with engine.connect() as conn:
        return list(conn.execute(
            text("SELECT a.titulo FROM avisos a JOIN usuarios u ON u.id = a.usuario_id "
                 "WHERE u.usuario = :u AND a.tipo = 'cuenta' ORDER BY a.id"),
            {"u": PREFIJO + nombre},
        ).scalars())


def con_mfa_activa(nombre):
    """La prueba solo revisa la regla: la persona ya entro y activo su MFA."""
    with engine.begin() as conn:
        conn.execute(text("UPDATE usuarios SET mfa_activo = true WHERE usuario = :u"), {"u": PREFIJO + nombre})


# ============================================== 1. TI no firma reportes
def test_ti_no_puede_crear_una_cuenta_que_firme(client):
    r = client.post("/usuarios", headers=como(client, "ti"), json={
        "usuario": PREFIJO + "falsa", "nombre": "Firma Falsa", "rol": "rrhh", "firma_reportes": True,
    })
    assert r.status_code == 403 and "Responsable de RRHH" in r.json()["detail"]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1 FROM usuarios WHERE usuario = :u"), {"u": PREFIJO + "falsa"}).first() is None


def test_ti_no_puede_dar_el_permiso_de_firma_a_una_cuenta(client, cuentas):
    r = client.patch(f"/usuarios/{cuentas['ids']['ana']}", headers=como(client, "ti"), json={"firma_reportes": True})
    assert r.status_code == 403
    assert seguridad.obtener_cuenta(cuentas["ids"]["ana"])["firma_reportes"] is False


def test_lo_que_ti_hace_con_una_cuenta_de_rrhh_le_llega_a_rrhh(client):
    r = client.post("/usuarios", headers=como(client, "ti"), json={
        "usuario": PREFIJO + "nueva", "nombre": "Nueva RRHH", "rol": "rrhh",
    })
    assert r.status_code == 201
    titulo = f"{PREFIJO}ti (TI) creó la cuenta de RRHH de Nueva RRHH ({PREFIJO}nueva)"
    assert titulo in avisos_de_cuenta("resp") and titulo in avisos_de_cuenta("ana")
    # una cuenta que no es de RRHH no genera aviso
    client.post("/usuarios", headers=como(client, "ti"), json={"usuario": PREFIJO + "otro", "nombre": "G", "rol": "direccion"})
    assert not any("otro" in t for t in avisos_de_cuenta("resp"))


@pytest.mark.parametrize("accion", ["contrasena", "mfa/reiniciar"])
def test_si_ti_restablece_el_acceso_de_quien_firma_pierde_la_firma(client, cuentas, accion):
    """El camino de la auditoria: TI restablece la contrasena (o el MFA) de la
    Responsable, entra con la temporal y firma. Ahora la cuenta ya no firma."""
    resp = cuentas["ids"]["resp"]
    with engine.begin() as conn:  # la Responsable tenia una suplente designada
        conn.execute(text("UPDATE usuarios SET mfa_activo = true WHERE id = :i"), {"i": resp})
        conn.execute(
            text("INSERT INTO suplencias (suplente, titular, desde, hasta) VALUES (:s, :t, :d, :h)"),
            {"s": PREFIJO + "ana", "t": PREFIJO + "resp", "d": date.today(), "h": date.today() + timedelta(days=5)},
        )
    ti = como(client, "ti")
    # la suplente tambien: TI restablece a la Analista que firma en su lugar
    for cuenta in ("resp", "ana"):
        r = client.post(f"/usuarios/{cuentas['ids'][cuenta]}/{accion}", headers=ti)
        assert r.status_code == 200, r.text
    assert seguridad.obtener_cuenta(resp)["firma_reportes"] is False
    with engine.connect() as conn:
        abierta = conn.execute(text("SELECT 1 FROM suplencias WHERE suplente = :s AND cancelada_en IS NULL"),
                               {"s": PREFIJO + "ana"}).first()
    assert abierta is None
    acciones = [c["accion"] for c in seguridad.cambios(10, PREFIJO + "resp")]
    assert "suspender_firma" in acciones
    assert any("Ya no puede firmar reportes" in t for t in avisos_de_cuenta("ana2"))


def test_solo_una_responsable_da_el_permiso_de_firma(client, cuentas):
    ana = cuentas["ids"]["ana"]
    ruta = f"/firmas/responsables/{ana}"
    assert client.put(ruta, headers=como(client, "ti"), json={"firma": True}).status_code == 403
    assert client.put(ruta, headers=como(client, "ana2"), json={"firma": True}).status_code == 403  # Analista
    # sin haber activado su propia verificacion en dos pasos, no (TI podria conocer su acceso)
    r = client.put(ruta, headers=como(client, "resp"), json={"firma": True})
    assert r.status_code == 422 and "verificación en dos pasos" in r.json()["detail"]
    con_mfa_activa("ana")
    r = client.put(ruta, headers=como(client, "resp"), json={"firma": True})
    assert r.status_code == 200 and r.json()["firma_reportes"] is True
    assert seguridad.cambios(1, PREFIJO + "ana")[0]["accion"] == "dar_firma"
    assert any("le dio el permiso de firmar reportes a Ana Analista" in t for t in avisos_de_cuenta("ana2"))
    # nadie cambia su propio permiso
    r = client.put(f"/firmas/responsables/{cuentas['ids']['resp']}", headers=como(client, "resp"), json={"firma": False})
    assert r.status_code == 422
    r = client.put(f"/firmas/responsables/{cuentas['ids']['dir']}", headers=como(client, "resp"), json={"firma": True})
    assert r.status_code == 422 and "RRHH" in r.json()["detail"]


# =============================== 2. sin firma, Direccion no lee el reporte
def _narrativa(revision, area_id=0, comentario=None):
    resultado = {"resumen": "TEXTO DE LA IA"}
    with engine.begin() as conn:
        return conn.execute(
            text("INSERT INTO narrativas (area_id, periodo, estado, solicitada_por, terminada_en, resultado, revision, "
                 "comentario_revision) VALUES (:a, '2026-08-01', 'lista', :s, now(), CAST(:r AS jsonb), :rev, :c) "
                 "RETURNING id"),
            {"a": area_id, "s": PREFIJO + "ana", "r": json.dumps(resultado), "rev": revision, "c": comentario},
        ).scalar_one()


@pytest.mark.parametrize("persona,area", [("dir", 0), ("ger", "ventas")])
def test_sin_firma_direccion_y_gerentes_no_leen_el_texto(cuentas, persona, area, monkeypatch):
    """La narrativa de prueba es minima (no pasaria el esquema de respuesta):
    se revisa lo que la API decide mandar, capturandolo en _para."""
    from app.rutas import narrativas

    client = TestClient(app, raise_server_exceptions=False)
    area_id = cuentas["ventas"] if area == "ventas" else 0
    pendiente = _narrativa("pendiente", area_id)
    rechazada = _narrativa("rechazada", area_id, "Faltan cifras de rotación")
    aprobada = _narrativa("aprobada", area_id)
    vistos = {}
    monkeypatch.setattr(narrativas, "_para", lambda u, t, _o=narrativas._para: vistos.setdefault(t["id"], _o(u, t)))
    encabezado = como(client, persona)
    for id_ in (pendiente, rechazada, aprobada):
        client.get(f"/narrativas/{id_}", headers=encabezado)
    assert vistos[pendiente]["narrativa"] is None and vistos[pendiente]["revision"] == "pendiente"
    assert vistos[rechazada]["narrativa"] is None and vistos[rechazada]["comentario_revision"] is None
    assert vistos[aprobada]["narrativa"] == {"resumen": "TEXTO DE LA IA"}
    # RRHH si lo lee para firmarlo
    vistos.clear()
    client.get(f"/narrativas/{pendiente}", headers=como(client, "resp"))
    assert vistos[pendiente]["narrativa"] == {"resumen": "TEXTO DE LA IA"}


def test_en_el_historial_tampoco_va_el_motivo_de_un_rechazo(client):
    _narrativa("rechazada", 0, "Faltan cifras de rotación")
    lista = client.get("/narrativas", headers=como(client, "dir")).json()
    mias = [t for t in lista if t["solicitada_por"] == PREFIJO + "ana"]
    assert mias and all(t["comentario_revision"] is None and t["narrativa"] is None for t in mias)


# ===================================== 3. cargas: la API sigue respondiendo
def test_subir_un_archivo_no_es_una_funcion_async():
    """Una funcion async que valida sin soltar el proceso congela toda la API."""
    assert not inspect.iscoroutinefunction(rutas_cargas.subir_archivo)


def test_mientras_se_valida_un_archivo_la_api_responde(cuentas, monkeypatch):
    import httpx2 as httpx

    app.dependency_overrides[rutas_cargas.solo_analista] = lambda: seguridad._leer_usuario(cuentas["ids"]["ana"])

    def validacion_lenta(*args):
        time.sleep(1.5)
        raise cargas.ErrorDeCarga("prueba")

    monkeypatch.setattr(cargas, "validar", validacion_lenta)

    async def medir():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            inicio = time.perf_counter()

            async def salud():
                await asyncio.sleep(0.2)
                await c.get("/health")
                return time.perf_counter() - inicio

            subida = c.post("/cargas/productividad", files={"archivo": ("p.csv", b"a,b\n1,2\n")})
            _, tiempo_salud = await asyncio.gather(subida, salud())
            return tiempo_salud

    try:
        assert asyncio.run(medir()) < 1.0  # antes: 1.5 s (esperaba a que terminara la validacion)
    finally:
        app.dependency_overrides.pop(rutas_cargas.solo_analista, None)


def test_rechaza_un_archivo_con_demasiadas_filas(monkeypatch):
    monkeypatch.setattr(cargas, "FILAS_MAXIMAS", 10)
    csv = ("area,periodo\n" + "Ventas,2026-08\n" * 11).encode()
    with pytest.raises(cargas.ErrorDeCarga, match="más de 10 filas"):
        cargas.leer_archivo("p.csv", csv)
    assert len(cargas.leer_archivo("p.csv", ("area,periodo\n" + "Ventas,2026-08\n" * 10).encode())) == 10


def test_rechaza_un_excel_que_descomprimido_pesa_demasiado(monkeypatch):
    salida = io.BytesIO()
    pd.DataFrame({"area": ["Ventas"] * 2000, "periodo": ["2026-08"] * 2000}).to_excel(salida, index=False)
    monkeypatch.setattr(cargas, "BYTES_DESCOMPRIMIDOS_MAXIMOS", 10_000)
    with pytest.raises(cargas.ErrorDeCarga, match="descomprimido pesa más"):
        cargas.leer_archivo("p.xlsx", salida.getvalue())
    with pytest.raises(cargas.ErrorDeCarga, match="no es un Excel"):
        cargas.leer_archivo("p.xlsx", b"esto no es un zip")


def test_un_excel_grande_se_lee_solo_hasta_el_limite_de_filas(monkeypatch):
    """No se lee el archivo entero para saber que se pasa del limite."""
    salida = io.BytesIO()
    pd.DataFrame({"area": ["Ventas"] * 3000, "periodo": ["2026-08"] * 3000}).to_excel(salida, index=False)
    monkeypatch.setattr(cargas, "FILAS_MAXIMAS", 100)
    leidas = {}
    original = pd.read_excel
    monkeypatch.setattr(cargas.pd, "read_excel", lambda *a, **k: leidas.setdefault("df", original(*a, **k)))
    with pytest.raises(cargas.ErrorDeCarga, match="más de 100 filas"):
        cargas.leer_archivo("p.xlsx", salida.getvalue())
    assert len(leidas["df"]) == 101


# ============================== 4. bloqueo por cuenta y por origen (IP)
def test_quien_se_equivoca_solo_bloquea_su_equipo(cuentas):
    atacante = TestClient(app, client=("10.0.0.66", 5000))
    duena = TestClient(app, client=("10.0.0.7", 5000))
    for _ in range(INTENTOS_MAXIMOS):
        assert entrar(atacante, "resp", "no-es-la-clave").status_code == 401
    r = entrar(atacante, "resp")  # bloqueado, ni con la contrasena correcta
    assert r.status_code == 429 and "en este equipo" in r.json()["detail"]
    assert entrar(duena, "resp").status_code == 200  # antes: 429, la Responsable quedaba fuera
    assert seguridad.obtener_cuenta(cuentas["ids"]["resp"])["bloqueado"] is True  # TI lo ve en el panel


def test_desde_varios_equipos_se_bloquea_la_cuenta_completa(cuentas):
    for i in range(ORIGENES_PARA_BLOQUEO_TOTAL):
        equipo = TestClient(app, client=(f"10.0.1.{i}", 5000))
        for _ in range(INTENTOS_MAXIMOS):
            entrar(equipo, "resp", "no-es-la-clave")
    r = entrar(TestClient(app, client=("10.0.2.1", 5000)), "resp")
    assert r.status_code == 429 and "varios equipos" in r.json()["detail"]
    # TI la desbloquea al restablecer la contrasena
    temporal = TestClient(app).post(
        f"/usuarios/{cuentas['ids']['resp']}/contrasena", headers=como(TestClient(app), "ti")
    ).json()["contrasena_temporal"]
    assert entrar(TestClient(app, client=("10.0.2.1", 5000)), "resp", temporal).status_code == 200


def test_entrar_bien_reinicia_el_contador_de_ese_equipo():
    equipo = TestClient(app, client=("10.0.3.1", 5000))
    for _ in range(INTENTOS_MAXIMOS - 1):
        entrar(equipo, "ana", "no-es-la-clave")
    assert entrar(equipo, "ana").status_code == 200
    for _ in range(INTENTOS_MAXIMOS - 1):
        assert entrar(equipo, "ana", "no-es-la-clave").status_code == 401
    assert entrar(equipo, "ana").status_code == 200


# =========================================== 5. cerrar sesion de verdad
def test_cerrar_sesion_invalida_el_token(client):
    encabezado = como(client, "ger")
    assert client.get("/auth/yo", headers=encabezado).status_code == 200
    assert client.post("/auth/salir", headers=encabezado).status_code == 204
    r = client.get("/auth/yo", headers=encabezado)  # antes: seguia sirviendo hasta caducar
    assert r.status_code == 401
    assert client.post("/auth/salir", headers=encabezado).status_code == 401


# ======================= 7. la API no se conecta como superusuario
@pytest.fixture()
def rol_de_prueba(monkeypatch):
    """Un rol propio de la prueba (nunca el talentia_api de la API en Docker):
    al terminar, las tablas vuelven a su dueno y el rol se borra."""
    nombre = "zz_api_pruebas"
    monkeypatch.setenv("DB_API_USUARIO", nombre)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with engine.connect() as conn:
        dueno = conn.execute(text("SELECT current_user")).scalar()
    yield nombre
    with engine.begin() as conn:
        if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": nombre}).first():
            conn.exec_driver_sql(f'REASSIGN OWNED BY {nombre} TO "{dueno}"')
            conn.exec_driver_sql(f"DROP OWNED BY {nombre}")
            conn.exec_driver_sql(f"DROP ROLE {nombre}")


def test_la_api_usa_una_cuenta_sin_privilegios(rol_de_prueba):
    from scripts.arranque import preparar_cuenta_de_la_api

    variables = preparar_cuenta_de_la_api()
    assert variables["DB_API_USUARIO"] == rol_de_prueba and len(variables["DB_API_CONTRASENA"]) >= 32
    api = create_engine(DB_URL.set(username=variables["DB_API_USUARIO"], password=variables["DB_API_CONTRASENA"]),
                        connect_args={"connect_timeout": 5})
    try:
        with api.connect() as conn:
            assert conn.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar() is False
            assert conn.execute(text("SELECT COUNT(*) FROM usuarios")).scalar() > 0  # trabaja normal
            assert conn.execute(  # es duena de las tablas: las crea y modifica al arrancar
                text("SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public' AND tableowner <> current_user")
            ).scalar() == 0
            with pytest.raises(Exception, match="permission denied|must be superuser|privilege"):
                conn.exec_driver_sql("COPY (SELECT 1) TO PROGRAM 'id'")  # con superusuario: comandos en el servidor
        with api.connect() as conn:
            with pytest.raises(Exception, match="permission denied|privilege"):
                conn.exec_driver_sql("CREATE ROLE zz_otro_rol SUPERUSER")
    finally:
        api.dispose()


def test_las_variables_de_la_cuenta_de_la_api_cambian_la_conexion(monkeypatch):
    from app.database import _url_desde_entorno

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_API_USUARIO", "talentia_api")
    monkeypatch.setenv("DB_API_CONTRASENA", "x" * 40)
    url = _url_desde_entorno()
    assert url.username == "talentia_api" and url.password == "x" * 40
    monkeypatch.delenv("DB_API_CONTRASENA")
    assert _url_desde_entorno().username == os.getenv("POSTGRES_USER")
