"""Pruebas de los arreglos de la auditoria de seguridad (noviembre de 2026).

Cada bloque reproduce un hallazgo: con el codigo de antes la prueba fallaba.

  1. TI no puede crear ni apropiarse de una cuenta que firma reportes.
  2. Direccion y los gerentes no leen reportes sin firmar.
  3. Subir un archivo no deja a la API sin responder; limites de filas y zip.
  4. El bloqueo por intentos es por cuenta y origen (no se puede bloquear a
     otra persona desde fuera).
  5. Cerrar sesion invalida el token.
  7. La API se conecta a PostgreSQL sin privilegios de superusuario.
  8. Aplicar una carga es una sola sentencia, no una por fila.
  9. Las dependencias de las pruebas no entran a la imagen de la API.
 10. openpyxl lee los Excel con defusedxml.
 12. Las respuestas de la API no se guardan en la cache del navegador.
 13. Un usuario que no existe se bloquea igual que uno real.
 14. Las bitacoras guardan desde que IP se hizo cada cosa.
 16. El modo demostracion rechaza una contrasena que estuvo publicada.
 17. Un reporte en espera dice cuantos van antes que el.

El 6 (Content-Security-Policy), el 11 (documentacion de la API fuera de la
red) y el limite por IP del 4 viven en nginx (frontend/nginx/); se revisan con
el tablero en Docker. El 15 es de las dependencias del frontend (npm audit).

Usuarios reales con su contrasena (prefijo zz_end_), como test_cuentas.py.
"""
import asyncio
import inspect
import io
import json
import os
import threading
import time
from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app import cargas, seguridad, trabajos
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
    # una cuenta de TI no ve datos de colaboradores: no genera aviso
    client.post("/usuarios", headers=como(client, "ti"), json={"usuario": PREFIJO + "otro", "nombre": "G", "rol": "admin_ti"})
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


# ===================== 8. aplicar una carga: una sentencia, no una por fila
def test_aplicar_inserta_todas_las_filas_en_una_sola_sentencia(cuentas):
    from sqlalchemy import event

    sentencias = []
    filas = [{"area": cuentas["ventas"], "periodo": date(2019, 1, 1), "dimension": "enps", "puntaje": i % 11}
             for i in range(500)]
    with engine.connect() as conn:
        transaccion = conn.begin()
        event.listen(conn, "before_cursor_execute", lambda *a: sentencias.append(a[2]))
        try:
            nuevas, conciliacion = cargas._APLICAR["clima"](conn, filas)
        finally:
            transaccion.rollback()  # la prueba no deja datos
    inserciones = [s for s in sentencias if s.startswith("INSERT INTO respuestas_clima")]
    assert len(inserciones) == 1  # antes: 500
    assert nuevas == 500 and conciliacion[0] == {"concepto": "Respuestas", "archivo": 500, "base": 500}


def test_aplicar_por_lote_distingue_nuevas_de_actualizadas(cuentas):
    with engine.connect() as conn:
        transaccion = conn.begin()
        try:
            existente = conn.execute(text("SELECT area_id, periodo FROM productividad LIMIT 1")).one()
            filas = [
                {"area": existente.area_id, "periodo": existente.periodo, "horas_efectivas": 10.5,
                 "horas_disponibles": 20.0, "entregables_planificados": 5, "entregables_completados": 4},
                {"area": existente.area_id, "periodo": date(2019, 1, 1), "horas_efectivas": 1.0,
                 "horas_disponibles": 2.0, "entregables_planificados": 1, "entregables_completados": 1},
            ]
            nuevas, conciliacion = cargas._APLICAR["productividad"](conn, filas)
            guardada = conn.execute(
                text("SELECT horas_efectivas FROM productividad WHERE area_id = :a AND periodo = :p"),
                {"a": existente.area_id, "p": existente.periodo},
            ).scalar()
        finally:
            transaccion.rollback()
    assert nuevas == 1 and float(guardada) == 10.5
    assert all(c["archivo"] == c["base"] for c in conciliacion)


# =========== 9 y 10. dependencias: sin las de pruebas en la imagen; XML seguro
def test_la_imagen_de_la_api_no_instala_las_dependencias_de_las_pruebas():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    produccion = (backend / "requirements.txt").read_text(encoding="utf-8").lower()
    assert not any(p in produccion for p in ("pytest", "pypdf", "httpx"))
    if (backend / "Dockerfile").exists():  # dentro de la imagen no esta: se construye con el
        dockerfile = (backend / "Dockerfile").read_text(encoding="utf-8")
        assert "pip install -r requirements.txt" in dockerfile and "pip install -r requirements-dev.txt" not in dockerfile


def test_openpyxl_lee_los_excel_con_defusedxml():
    import openpyxl.xml

    assert openpyxl.xml.DEFUSEDXML is True


# ========================================= 12. sin cache del navegador
def test_las_respuestas_de_la_api_no_se_guardan_en_cache(client):
    assert client.get("/health").headers["cache-control"] == "no-store"
    r = client.get("/kpis", headers=como(client, "ger"))
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"


# ============== 13. el bloqueo no revela que cuentas existen
def test_un_usuario_que_no_existe_se_bloquea_igual_que_uno_real():
    equipo = TestClient(app, client=("10.0.4.1", 5000))
    respuestas = {}
    for nombre in ("resp", "no_existe"):
        for _ in range(INTENTOS_MAXIMOS):
            assert entrar(equipo, nombre, "no-es-la-clave").status_code == 401
        respuestas[nombre] = entrar(equipo, nombre, "no-es-la-clave")
    assert respuestas["resp"].status_code == respuestas["no_existe"].status_code == 429  # antes: 401 si no existia
    assert respuestas["resp"].json() == respuestas["no_existe"].json()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM bloqueos_acceso WHERE usuario LIKE :p"), {"p": PREFIJO + "%"})


def test_crear_una_cuenta_borra_lo_que_se_intento_antes_con_ese_nombre():
    equipo = TestClient(app, client=("10.0.4.2", 5000))
    for _ in range(INTENTOS_MAXIMOS):
        entrar(equipo, "despues", "no-es-la-clave")
    crear_usuario(PREFIJO + "despues", "Cuenta Nueva", "direccion", CLAVE)
    assert entrar(equipo, "despues").status_code == 200


# ====================================== 14. desde que IP se hizo cada cosa
def test_la_bitacora_de_cuentas_guarda_la_ip(cuentas):
    ti = TestClient(app, client=("10.0.5.7", 5000))
    r = ti.post("/usuarios", headers=como(ti, "ti"), json={"usuario": PREFIJO + "conip", "nombre": "Con IP", "rol": "direccion"})
    assert r.status_code == 201
    cambios = ti.get("/usuarios/cambios", headers=como(ti, "ti"), params={"usuario": PREFIJO + "conip"}).json()
    assert cambios[0]["accion"] == "crear" and cambios[0]["origen"] == "10.0.5.7"
    # lo que se hace desde la consola o el arranque no tiene IP
    assert seguridad.cambios(1, PREFIJO + "ti")[0]["origen"] is None


def test_la_firma_y_la_descarga_de_un_reporte_guardan_la_ip(cuentas, monkeypatch):
    from app import exportar, trabajos

    id_ = _narrativa("pendiente")
    # narrativa minima: no pasa el esquema de respuesta, pero la firma ya quedo guardada
    equipo = TestClient(app, client=("10.0.5.8", 5000), raise_server_exceptions=False)
    equipo.post(f"/narrativas/{id_}/revision", headers=como(equipo, "resp"), json={"decision": "aprobada"})
    monkeypatch.setattr(exportar, "generar", lambda trabajo, formato: b"%PDF-")
    monkeypatch.setattr(exportar, "nombre_archivo", lambda trabajo, formato: "reporte.pdf")
    assert equipo.get(f"/narrativas/{id_}/exportar", headers=como(equipo, "dir")).status_code == 200
    with engine.connect() as conn:
        assert conn.execute(text("SELECT revisada_desde FROM narrativas WHERE id = :i"), {"i": id_}).scalar() == "10.0.5.8"
        assert conn.execute(text("SELECT origen FROM exportaciones WHERE narrativa_id = :i"), {"i": id_}).scalar() == "10.0.5.8"


# ============== 16. una contrasena de demo que estuvo publicada no sirve
def test_el_modo_demo_rechaza_una_contrasena_publicada(monkeypatch):
    import hashlib

    from app import demo

    monkeypatch.setenv("MODO_DEMO", "si")
    monkeypatch.setenv("MODO_DATOS", "sinteticos")
    monkeypatch.setenv("DEMO_CONTRASENA", "Publicada-en-github-1")
    assert demo.motivo_inactivo() is None
    monkeypatch.setattr(demo, "CONTRASENAS_PUBLICADAS",
                        demo.CONTRASENAS_PUBLICADAS | {hashlib.sha256(b"Publicada-en-github-1").hexdigest()})
    assert "estuvo publicada" in demo.motivo_inactivo()
    assert len(demo.CONTRASENAS_PUBLICADAS) >= 1  # la que estuvo en el repositorio hasta octubre


# ============================ 17. un reporte en espera dice su lugar en la cola
def test_un_reporte_en_espera_dice_cuantos_van_antes(cuentas):
    with engine.begin() as conn:
        ids = [conn.execute(
            text("INSERT INTO narrativas (area_id, periodo, estado, solicitada_por) "
                 "VALUES (0, '2026-08-01', 'en_proceso', :s) RETURNING id"),
            {"s": PREFIJO + "ana"},
        ).scalar_one() for _ in range(2)]
    from app import trabajos

    primero, segundo = (trabajos.obtener(i) for i in ids)
    assert segundo["antes_en_cola"] == primero["antes_en_cola"] + 1
    listo = trabajos.obtener(_narrativa("aprobada"))
    assert listo["antes_en_cola"] is None


# ============================================================================
# Segunda auditoria (noviembre de 2026)
# ============================================================================

# ============ 1. la suplente tambien debe tener su propio acceso, no el de TI
def test_no_se_designa_suplente_a_quien_tiene_la_temporal_de_ti(client, cuentas):
    with engine.begin() as conn:  # TI la creo: tiene la contrasena temporal que TI conoce
        conn.execute(text("UPDATE usuarios SET debe_cambiar_contrasena = true WHERE usuario = :u"), {"u": PREFIJO + "ana"})
    responsable = como(client, "resp")
    hasta = str(date.today() + timedelta(days=3))
    assert PREFIJO + "ana" not in [c["usuario"] for c in client.get("/firmas", headers=responsable).json()["candidatas"]]
    r = client.post("/firmas/suplencia", headers=responsable, json={"suplente": PREFIJO + "ana", "hasta": hasta})
    assert r.status_code == 422 and "contraseña temporal" in r.json()["detail"]  # antes: 200
    with engine.begin() as conn:  # ya entro, la cambio y activo su verificacion en dos pasos
        conn.execute(text("UPDATE usuarios SET debe_cambiar_contrasena = false, mfa_activo = true WHERE usuario = :u"),
                     {"u": PREFIJO + "ana"})
    assert PREFIJO + "ana" in [c["usuario"] for c in client.get("/firmas", headers=responsable).json()["candidatas"]]
    r = client.post("/firmas/suplencia", headers=responsable, json={"suplente": PREFIJO + "ana", "hasta": hasta})
    assert r.status_code == 200, r.text


# ======== 2. la API no conserva la contrasena del superusuario en su entorno
def test_el_arranque_quita_la_contrasena_del_superusuario_antes_de_la_api(monkeypatch):
    from scripts import arranque

    monkeypatch.setenv("POSTGRES_PASSWORD", "secreto-del-superusuario")
    monkeypatch.setattr(arranque, "sembrar_si_hace_falta", lambda: None)
    monkeypatch.setattr(arranque, "preparar_demo", lambda: None)
    monkeypatch.setattr(arranque, "preparar_cuenta_de_la_api",
                        lambda: {"DB_API_USUARIO": "talentia_api", "DB_API_CONTRASENA": "x" * 40})
    entorno = {}
    monkeypatch.setattr(arranque.os, "execvp", lambda *a: entorno.update(os.environ))
    arranque.main()
    assert "POSTGRES_PASSWORD" not in entorno  # antes: la API la tenia y podia entrar como superusuario
    assert entorno["DB_API_USUARIO"] == "talentia_api"


# ===== 3. adivinar la contrasena actual con una sesion robada tambien bloquea
def test_la_contrasena_actual_equivocada_cuenta_como_intento_fallido(cuentas):
    equipo = TestClient(app, client=("10.0.6.1", 5000))
    sesion = como(equipo, "ger")
    for i in range(INTENTOS_MAXIMOS):
        r = equipo.post("/auth/contrasena", headers=sesion, json={"actual": f"intento-{i}-xxxx", "nueva": "Otra-clave-nueva-1"})
        assert r.status_code == 422
    r = equipo.post("/auth/contrasena", headers=sesion, json={"actual": CLAVE, "nueva": "Otra-clave-nueva-1"})
    assert r.status_code == 429  # antes: 200 tras intentos sin limite
    assert entrar(equipo, "ger").status_code == 429  # y desde ese equipo tampoco entra
    assert entrar(TestClient(app, client=("10.0.6.2", 5000)), "ger").status_code == 200  # la persona, desde el suyo, si


# == 4. lo que TI hace con Direccion o un gerente tambien se avisa (y a la persona)
def test_si_ti_restablece_a_un_gerente_se_entera_rrhh_y_el_gerente(client, cuentas):
    r = client.post(f"/usuarios/{cuentas['ids']['ger']}/contrasena", headers=como(client, "ti"))
    assert r.status_code == 200
    titulo = f"{PREFIJO}ti (TI) restableció la contraseña de la cuenta de gerencia de Gerente Ventas ({PREFIJO}ger)"
    assert titulo in avisos_de_cuenta("resp")  # antes: solo se avisaba de cuentas de RRHH
    assert titulo in avisos_de_cuenta("ger")
    with engine.connect() as conn:  # al gerente le llega con su area, la unica que puede ver
        area = conn.execute(text("SELECT a.area_id FROM avisos a JOIN usuarios u ON u.id = a.usuario_id "
                                 "WHERE u.usuario = :u AND a.tipo = 'cuenta'"), {"u": PREFIJO + "ger"}).scalar()
    assert area == cuentas["ventas"]


# ================================ 6. el historial no consulta una vez por fila
def test_el_historial_consulta_los_nombres_de_una_vez(client, cuentas):
    from sqlalchemy import event

    for _ in range(15):
        id_ = _narrativa("pendiente")
        with engine.begin() as conn:
            conn.execute(text("UPDATE narrativas SET revision = 'aprobada', revisada_por = :r WHERE id = :i"),
                         {"r": PREFIJO + "resp", "i": id_})
    encabezado = como(client, "resp")  # el inicio de sesion no cuenta
    consultas = []

    def contar(*_):
        consultas.append(1)

    event.listen(engine, "before_cursor_execute", contar)
    try:
        lista = client.get("/narrativas", params={"limite": 100}, headers=encabezado).json()
    finally:
        event.remove(engine, "before_cursor_execute", contar)
    mias = [t for t in lista if t["revisada_por"] == PREFIJO + "resp"]
    assert len(mias) >= 15 and all(t["firma"]["nombre"] == "Eva Responsable" for t in mias)
    assert len(consultas) < 12  # antes: una por fila (mas de 15)


# ====================== 7. el tablero sirve los KPIs ya listos, sin recalcularlos
def test_los_kpis_salen_del_indice_y_coinciden_con_el_calculo(client):
    from app.rutas.comun import a_registros, indice_kpis, kpis_df

    df = kpis_df()
    mes = df["periodo"].max()
    esperado = a_registros(df[(df["periodo"] == mes) & (df["area_id"] == 0)])
    assert client.get("/kpis", params={"area_id": 0}, headers=como(client, "dir")).json() == json.loads(
        json.dumps(esperado, default=str))
    assert indice_kpis() is indice_kpis()  # se arma una vez por calculo


# ================ 11. una carga validada que nadie aplica vence y se borran sus filas
def test_una_carga_validada_que_nadie_aplica_vence(cuentas):
    with engine.begin() as conn:
        id_ = conn.execute(
            text("INSERT INTO cargas (fuente, archivo, sha256, bytes, filas, estado, errores, descartadas, periodos, "
                 "datos, resultado, subida_por, subida_en) VALUES ('productividad', 'viejo.csv', repeat('a', 64), 10, 1, "
                 "'validada', '[]', '[]', '[]', CAST(:d AS jsonb), '{}', :u, now() - make_interval(days => :dias)) "
                 "RETURNING id"),
            {"d": json.dumps([{"area": 1}]), "u": PREFIJO + "ana", "dias": cargas.DIAS_PARA_APLICAR + 1},
        ).scalar_one()
    try:
        with pytest.raises(cargas.ErrorDeCarga, match="venció"):
            cargas.aplicar(id_, PREFIJO + "ana")
        with engine.connect() as conn:
            fila = conn.execute(text("SELECT estado, datos, aplicada_por FROM cargas WHERE id = :i"), {"i": id_}).one()
        assert fila.estado == "descartada" and fila.datos is None and fila.aplicada_por == cargas.CADUCADA
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM cargas WHERE id = :i"), {"i": id_})


def test_vencer_cargas_no_truena_si_la_api_nunca_ha_arrancado():
    """scripts/programar.py recien sembrada la base: la tabla cargas aun no existe.
    revisar() vence las cargas antes de las alertas: un error ahi las detendria."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE cargas RENAME TO cargas_guardada"))
    try:
        assert cargas.caducar() == 0  # antes: UndefinedTable
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS cargas"))
            conn.execute(text("ALTER TABLE cargas_guardada RENAME TO cargas"))


# ============================================================================
# Tercera auditoria (noviembre de 2026)
# ============================================================================

# ============ 2. el DDL de cargas solo corre si falta algo: dos pestanas se interbloqueaban
def test_dos_personas_viendo_las_cargas_no_se_interbloquean():
    errores = []

    def leer():
        try:
            for _ in range(25):
                cargas.listar()
        except Exception as exc:  # antes: DeadlockDetected en 12 de cada 100
            errores.append(exc)

    hilos = [threading.Thread(target=leer) for _ in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert errores == []


def test_el_ddl_de_cargas_no_corre_si_el_esquema_esta_al_dia(monkeypatch):
    llamadas = []
    monkeypatch.setattr(cargas, "ejecutar_sql", llamadas.append)
    cargas.asegurar_tabla()
    assert llamadas == []


def test_si_el_seed_se_lleva_la_columna_folio_se_repone():
    """El seed recrea vacantes, a veces con la API encendida: por eso no basta
    una bandera por proceso."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE vacantes RENAME COLUMN folio TO folio_guardado"))
    try:
        cargas.asegurar_tabla()
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(folio) FROM vacantes")).scalar() == 0
    finally:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE vacantes DROP COLUMN IF EXISTS folio"))
            conn.execute(text("ALTER TABLE vacantes RENAME COLUMN folio_guardado TO folio"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS vacantes_folio ON vacantes (folio)"))


# ==================================== 4. las contrasenas mas obvias se rechazan
@pytest.mark.parametrize("clave", [
    "1234567890", "0987654321", "aaaaaaaaaa", "1212121212", "abcabcabca", "abcdefghij", "qwertyuiop",
    "Password123", "Password123!", "qwerty12345", "Admin12345", "Talentia2026", "Bienvenido1",
])
def test_una_contrasena_obvia_se_rechaza(clave):
    with pytest.raises(seguridad.ErrorDeUsuario, match="común"):
        seguridad.validar_contrasena_nueva(clave, "persona")


@pytest.mark.parametrize("clave", [CLAVE, "k7Mq-3xPa-9tRe", "mi perro se llama Toby", "Otra-clave-nueva-1"])
def test_una_contrasena_razonable_se_acepta(clave):
    seguridad.validar_contrasena_nueva(clave, "persona")


def test_las_temporales_que_genera_ti_siempre_pasan_la_regla():
    for _ in range(200):
        seguridad.validar_contrasena_nueva(seguridad.generar_contrasena_temporal(), "persona")


# ============= 9. la cola de reportes no acepta duplicados ni crece sin limite
class _Proveedor:
    nombre, modelo = "falso", "modelo-falso"


class _SinEjecutar:
    def submit(self, *_):
        pass  # se queda en_proceso, como si el modelo siguiera trabajando


@pytest.fixture()
def cola_vacia(monkeypatch):
    monkeypatch.setattr(trabajos, "ejecutor", _SinEjecutar())
    with engine.begin() as conn:
        antes = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM narrativas")).scalar()
        conn.execute(text("UPDATE narrativas SET estado = 'error' WHERE estado = 'en_proceso'"))
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM narrativas WHERE id > :i"), {"i": antes})


def _pedir(area_id=0, mes="2026-08-01", **extra):
    return trabajos.encolar(pd.Timestamp(mes), area_id, _Proveedor(), None, **extra)


def test_el_mismo_reporte_no_se_encola_dos_veces(cola_vacia):
    primero = _pedir(solicitante=PREFIJO + "ana")
    with pytest.raises(trabajos.SolicitudRechazada, match=str(primero)) as exc:
        _pedir(solicitante=PREFIJO + "ana")
    assert exc.value.estado == 409  # antes: 30 de 30 aceptados
    _pedir(area_id=1, solicitante=PREFIJO + "ana")  # otra area si
    _pedir(mes="2026-07-01", solicitante=PREFIJO + "ana")  # otro mes tambien


def test_la_cola_llena_rechaza_los_pedidos_pero_no_los_programados(cola_vacia, monkeypatch):
    monkeypatch.setattr(trabajos, "COLA_MAXIMA", 2)
    _pedir(area_id=1, solicitante=PREFIJO + "ana")
    _pedir(area_id=2, solicitante=PREFIJO + "ana")
    with pytest.raises(trabajos.SolicitudRechazada) as exc:
        _pedir(area_id=3, solicitante=PREFIJO + "ana")
    assert exc.value.estado == 429
    assert _pedir(area_id=3, programada=True)  # lo del mes no se queda fuera


def test_la_api_responde_409_con_el_motivo(client, cola_vacia, monkeypatch):
    from app.rutas import narrativas

    app.dependency_overrides[narrativas.proveedor_configurado] = lambda: _Proveedor()
    try:
        analista = como(client, "ana")
        mes = client.get("/periodos", headers=analista).json()[-1]
        datos = {"area_id": 0, "periodo": mes}
        assert client.post("/narrativas", headers=analista, json=datos).status_code == 202
        r = client.post("/narrativas", headers=analista, json=datos)
        assert r.status_code == 409 and "ya se está generando" in r.json()["detail"]
    finally:
        app.dependency_overrides.pop(narrativas.proveedor_configurado, None)


# ========= base vacia con datos reales: la API no arrancaba (faltaban las tablas)
def _arranque_con_datos_reales(monkeypatch, vacia):
    from scripts import arranque

    ejecutados = []
    monkeypatch.setattr(arranque, "base_vacia", lambda: vacia)
    monkeypatch.setattr(arranque, "modo_datos", lambda: "reales")
    monkeypatch.setattr(arranque, "ejecutar_sql", ejecutados.append)
    arranque.sembrar_si_hace_falta()
    return ejecutados


def test_con_datos_reales_y_base_vacia_se_crean_las_tablas(monkeypatch):
    assert _arranque_con_datos_reales(monkeypatch, vacia=True) == ["schema.sql"]


def test_con_datos_reales_y_base_con_datos_no_se_toca_nada(monkeypatch):
    """schema.sql borra las tablas de las fuentes: nunca con datos."""
    assert _arranque_con_datos_reales(monkeypatch, vacia=False) == []
