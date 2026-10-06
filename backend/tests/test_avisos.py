"""Pruebas de los avisos y del correo opcional (paso 10, RF-09).

Usuarios reales (prefijo zz_av_, se borran al final): los avisos son por
persona y van a la tabla `avisos` con llave foranea a `usuarios`. Las
narrativas se insertan directo en la tabla; aqui no importa el modelo.
"""
import smtplib

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import avisos, seguridad, trabajos
from app.database import engine
from app.main import app
from app.seguridad import ErrorDeUsuario, Usuario, crear_usuario, usuario_actual

CLAVE = "Clave-de-prueba-123"
PREFIJO = "zz_av_"
AGOSTO = pd.Timestamp("2026-08-01")


@pytest.fixture(scope="module")
def ventas():
    with engine.connect() as conn:
        return conn.execute(text("SELECT id FROM areas WHERE nombre = 'Ventas'")).scalar_one()


@pytest.fixture(scope="module")
def gente(ventas):
    """Dos de RRHH, Direccion, el gerente de Ventas y TI. Devuelve nombre -> Usuario."""
    seguridad.asegurar_tabla()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM usuarios WHERE usuario LIKE :p"), {"p": PREFIJO + "%"})
    datos = {
        "rrhh": ("rrhh", None, "rrhh@empresa.com"),
        "rrhh2": ("rrhh", None, None),
        "dir": ("direccion", None, "dir@empresa.com"),
        "ger": ("gerente", ventas, "ger@empresa.com"),
        "ti": ("admin_ti", None, "ti@empresa.com"),
    }
    personas = {}
    for nombre, (rol, area_id, correo) in datos.items():
        id_ = crear_usuario(PREFIJO + nombre, f"Prueba {nombre}", rol, CLAVE, area_id, correo)
        personas[nombre] = Usuario(id_, PREFIJO + nombre, f"Prueba {nombre}", rol, area_id)
    yield personas
    with engine.begin() as conn:  # sus avisos se van en cascada
        conn.execute(text("DELETE FROM usuarios WHERE usuario LIKE :p"), {"p": PREFIJO + "%"})


@pytest.fixture()
def narrativa(gente):
    """Inserta una narrativa y devuelve su id; las borra al terminar."""
    trabajos.asegurar_tabla()
    with engine.connect() as conn:
        ultimo = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM narrativas")).scalar()

    def _crear(area_id=0, estado="lista", solicitada_por=None, programada=False):
        with engine.begin() as conn:
            return conn.execute(
                text(
                    "INSERT INTO narrativas (area_id, periodo, estado, solicitada_por, programada, terminada_en) "
                    "VALUES (:a, '2026-08-01', :e, :s, :p, now()) RETURNING id"
                ),
                {"a": area_id, "e": estado, "s": gente[solicitada_por].usuario if solicitada_por else None,
                 "p": programada},
            ).scalar_one()

    yield _crear
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM narrativas WHERE id > :u"), {"u": ultimo})


def titulos(u: Usuario) -> list[str]:
    return [a["titulo"] for a in avisos.listar(u)["avisos"]]


def kpis_falsos(ventas, *rojos_de_ventas):
    """DataFrame minimo con lo que usa avisar_alertas: un rojo en el
    consolidado, los rojos de Ventas que se pidan y un amarillo."""
    filas = [
        (0, "Corporativo", "rotacion_total", "Tasa de rotación mensual", "rojo"),
        (ventas, "Ventas", "enps", "eNPS", "amarillo"),
    ] + [(ventas, "Ventas", ind, nombre, "rojo") for ind, nombre in rojos_de_ventas]
    return pd.DataFrame(
        [{"periodo": AGOSTO, "area_id": a, "area": ar, "indicador": i, "nombre": n, "estado": e}
         for a, ar, i, n, e in filas]
    )


# ------------------------------------------------------------ alertas
def test_alerta_roja_llega_a_quien_le_toca(gente, ventas):
    df = kpis_falsos(ventas, ("rotacion_voluntaria", "Rotación voluntaria mensual"))
    assert avisos.avisar_alertas(df) > 0

    corporativo = "Corporativo, agosto 2026: 1 indicador en rojo (Tasa de rotación mensual)"
    de_ventas = "Ventas, agosto 2026: 1 indicador en rojo (Rotación voluntaria mensual)"
    assert titulos(gente["dir"]) == [corporativo]           # Direccion: solo el consolidado
    assert titulos(gente["ger"]) == [de_ventas]             # gerente: solo su area
    assert set(titulos(gente["rrhh"])) == {corporativo, de_ventas}  # RRHH: todo
    assert titulos(gente["ti"]) == []                       # TI no ve datos
    # el amarillo no avisa
    assert all("eNPS" not in t for t in titulos(gente["rrhh"]))
    aviso = avisos.listar(gente["ger"])["avisos"][0]
    assert aviso["tipo"] == "alerta" and aviso["enlace"] == f"/tablero?area={ventas}&periodo=2026-08"


def test_la_misma_alerta_no_se_repite_pero_un_rojo_nuevo_si(gente, ventas):
    df = kpis_falsos(ventas, ("rotacion_voluntaria", "Rotación voluntaria mensual"))
    avisos.avisar_alertas(df)
    assert avisos.avisar_alertas(df) == 0  # la API revisa cada hora: nada nuevo
    assert len(titulos(gente["ger"])) == 1

    df = kpis_falsos(ventas, ("rotacion_voluntaria", "Rotación voluntaria mensual"), ("enps", "eNPS"))
    df = df[~((df["indicador"] == "enps") & (df["estado"] == "amarillo"))]
    avisos.avisar_alertas(df)
    assert titulos(gente["ger"])[0] == "Ventas, agosto 2026: 2 indicadores en rojo (eNPS, Rotación voluntaria mensual)"
    assert len(titulos(gente["dir"])) == 1  # el consolidado no cambio


def test_al_leer_se_vuelven_a_aplicar_los_permisos(gente, ventas):
    """Si al gerente lo cambian de area, deja de ver los avisos de la anterior."""
    avisos.avisar_alertas(kpis_falsos(ventas, ("rotacion_voluntaria", "Rotación voluntaria mensual")))
    movido = Usuario(gente["ger"].id, gente["ger"].usuario, "Prueba", "gerente", ventas + 1)
    assert avisos.listar(movido) == {"no_leidos": 0, "avisos": []}
    como_ti = Usuario(gente["ger"].id, gente["ger"].usuario, "Prueba", "admin_ti", None)
    assert avisos.listar(como_ti)["avisos"] == []


# --------------------------------------------------------- narrativas
def test_reporte_listo_avisa_a_rrhh_menos_a_quien_lo_pidio(gente, narrativa):
    id_ = narrativa(solicitada_por="rrhh")
    avisos.avisar_narrativa_terminada(id_)
    assert titulos(gente["rrhh2"]) == ["Reporte de Corporativo, agosto 2026 listo para revisión"]
    assert titulos(gente["rrhh"]) == []  # no puede revisar lo que pidio
    assert titulos(gente["dir"]) == []   # aun no esta aprobado
    assert avisos.listar(gente["rrhh2"])["avisos"][0]["enlace"] == f"/narrativas/{id_}"


def test_error_avisa_solo_si_era_programado(gente, narrativa):
    avisos.avisar_narrativa_terminada(narrativa(estado="error", solicitada_por="rrhh2"))
    assert titulos(gente["rrhh"]) == []  # quien lo pidio ya lo ve en pantalla

    avisos.avisar_narrativa_terminada(narrativa(estado="error", programada=True))
    esperado = ["No se pudo generar el reporte programado de Corporativo, agosto 2026"]
    assert titulos(gente["rrhh"]) == titulos(gente["rrhh2"]) == esperado


def test_aprobado_avisa_a_la_audiencia_y_a_quien_lo_pidio(gente, narrativa, ventas):
    id_ = narrativa(area_id=ventas, solicitada_por="ger")
    trabajos.revisar(id_, "aprobada", gente["rrhh2"].usuario, None)
    assert titulos(gente["ger"]) == ["Reporte de Ventas, agosto 2026 aprobado: ya se puede descargar"]
    assert titulos(gente["rrhh2"]) == []  # quien aprobo no se avisa a si mismo
    assert titulos(gente["dir"]) == []    # no es del consolidado

    corporativo = narrativa(programada=True)
    trabajos.revisar(corporativo, "aprobada", gente["rrhh"].usuario, None)
    assert titulos(gente["dir"]) == ["Reporte de Corporativo, agosto 2026 aprobado: ya se puede descargar"]


def test_rechazado_avisa_a_quien_lo_pidio(gente, narrativa):
    id_ = narrativa(solicitada_por="dir")
    trabajos.revisar(id_, "rechazada", gente["rrhh"].usuario, "Falta el hallazgo de rotación")
    assert titulos(gente["dir"]) == ["Reporte de Corporativo, agosto 2026 rechazado: revisa el motivo"]


def test_si_el_aviso_falla_la_revision_sigue(gente, narrativa, monkeypatch):
    def falla(*_args, **_kwargs):
        raise RuntimeError("tabla de avisos no disponible")

    monkeypatch.setattr(avisos, "_crear", falla)
    id_ = narrativa(solicitada_por="rrhh")
    assert trabajos.revisar(id_, "aprobada", gente["rrhh2"].usuario, None)["revision"] == "aprobada"


# ---------------------------------------------------------------- API
@pytest.fixture()
def como(gente):
    def _como(nombre):
        app.dependency_overrides[usuario_actual] = lambda: gente[nombre]
        return TestClient(app)
    return _como


def test_api_lista_y_marca_leidos(gente, ventas, como):
    avisos.avisar_alertas(kpis_falsos(ventas, ("rotacion_voluntaria", "Rotación voluntaria mensual")))
    cliente = como("rrhh")
    r = cliente.get("/avisos").json()
    assert r["no_leidos"] == 2 and len(r["avisos"]) == 2

    primero = r["avisos"][0]["id"]
    assert cliente.post(f"/avisos/{primero}/leido").status_code == 204
    r = cliente.get("/avisos").json()
    assert r["no_leidos"] == 1
    assert [a["id"] for a in cliente.get("/avisos?solo_no_leidos=true").json()["avisos"]] != [primero]

    assert cliente.post("/avisos/leidos").json() == {"marcados": 1}
    assert cliente.get("/avisos").json()["no_leidos"] == 0


def test_api_no_deja_marcar_avisos_ajenos(gente, ventas, como):
    avisos.avisar_alertas(kpis_falsos(ventas, ("rotacion_voluntaria", "Rotación voluntaria mensual")))
    ajeno = avisos.listar(gente["rrhh"])["avisos"][0]["id"]
    assert como("ger").post(f"/avisos/{ajeno}/leido").status_code == 404
    assert avisos.listar(gente["rrhh"])["no_leidos"] == 2


def test_api_ti_no_tiene_avisos(como):
    assert como("ti").get("/avisos").json() == {"no_leidos": 0, "avisos": []}


# -------------------------------------------------------------- correo
class SmtpFalso:
    """Servidor SMTP de mentira: guarda lo que se envia."""
    enviados: list = []
    falla = False

    def __init__(self, host, puerto, timeout=None):
        self.host, self.puerto = host, puerto
        self.tls = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def ehlo(self):
        pass

    def has_extn(self, nombre):
        return nombre == "starttls"

    def starttls(self):
        self.tls = True

    def login(self, usuario, contrasena):
        assert self.tls, "la contraseña no debe viajar sin cifrar"
        self.usuario = usuario

    def send_message(self, mensaje):
        if SmtpFalso.falla:
            raise smtplib.SMTPServerDisconnected("se cayó la conexión")
        SmtpFalso.enviados.append(mensaje)


class _Anotar:
    """En lugar del hilo de correo: anota el envio y la prueba decide cuando enviar."""

    def __init__(self):
        self.pedidos = 0

    def submit(self, _fn):
        self.pedidos += 1


@pytest.fixture()
def smtp(monkeypatch):
    SmtpFalso.enviados, SmtpFalso.falla = [], False
    monkeypatch.setattr(avisos.smtplib, "SMTP", SmtpFalso)
    monkeypatch.setattr(avisos, "ejecutor_correo", _Anotar())
    monkeypatch.setenv("SMTP_HOST", "smtp.prueba")
    monkeypatch.setenv("SMTP_USUARIO", "motor@empresa.com")
    monkeypatch.setenv("SMTP_CONTRASENA", "secreta")
    monkeypatch.setenv("APP_URL", "https://rrhh.empresa.com/")
    return SmtpFalso


def test_correo_sin_datos_uno_por_persona(gente, ventas, smtp):
    avisos.avisar_alertas(kpis_falsos(ventas, ("rotacion_voluntaria", "Rotación voluntaria mensual")))
    assert avisos.ejecutor_correo.pedidos == 1  # el aviso pide el envio en segundo plano
    enviados = avisos.enviar_correos()

    para = {m["To"]: m for m in smtp.enviados if m["To"].endswith("@empresa.com")}
    assert set(para) == {"rrhh@empresa.com", "dir@empresa.com", "ger@empresa.com"}  # rrhh2 sin correo, TI sin avisos
    assert enviados >= 3
    rrhh = para["rrhh@empresa.com"]
    assert rrhh["Subject"] == "Motor de Reportes de RRHH: tienes 2 avisos nuevos"
    cuerpo = rrhh.get_content()
    assert "https://rrhh.empresa.com/avisos" in cuerpo
    for dato in ("Ventas", "Corporativo", "rotación", "Rotación", "agosto", "rojo"):
        assert dato not in cuerpo and dato not in rrhh["Subject"], dato
    assert para["ger@empresa.com"]["Subject"].endswith("tienes 1 aviso nuevo")

    assert avisos.enviar_correos() == 0  # no se repite


def test_correo_no_se_manda_si_ya_lo_leyo(gente, ventas, smtp):
    avisos.avisar_alertas(kpis_falsos(ventas, ("rotacion_voluntaria", "Rotación voluntaria mensual")))
    avisos.marcar_todos(gente["ger"])
    avisos.enviar_correos()
    assert "ger@empresa.com" not in {m["To"] for m in smtp.enviados}


def test_si_el_correo_falla_se_reintenta_despues(gente, ventas, smtp):
    avisos.avisar_alertas(kpis_falsos(ventas, ("rotacion_voluntaria", "Rotación voluntaria mensual")))
    smtp.falla = True
    avisos.enviar_correos()
    assert smtp.enviados == []
    smtp.falla = False
    avisos.enviar_correos()
    assert "ger@empresa.com" in {m["To"] for m in smtp.enviados}


def test_sin_smtp_no_hay_correo(gente, ventas, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "")
    avisos.avisar_alertas(kpis_falsos(ventas, ("rotacion_voluntaria", "Rotación voluntaria mensual")))
    assert avisos.configuracion_smtp() is None
    assert avisos.enviar_correos() == 0


def test_no_manda_la_contrasena_sin_cifrar(monkeypatch):
    class SinTls(SmtpFalso):
        def has_extn(self, nombre):
            return False

    monkeypatch.setattr(avisos.smtplib, "SMTP", SinTls)
    conf = {"host": "smtp.prueba", "puerto": 587, "usuario": "motor", "contrasena": "x", "remitente": "motor"}
    with pytest.raises(smtplib.SMTPException, match="STARTTLS"):
        avisos._enviar(conf, "a@empresa.com", "asunto", "cuerpo")


# ------------------------------------------------------ correo del usuario
def test_correo_del_usuario_se_valida(gente):
    with pytest.raises(ErrorDeUsuario, match="no es un correo"):
        seguridad.cambiar_correo(gente["rrhh2"].usuario, "sin-arroba")
    seguridad.cambiar_correo(gente["rrhh2"].usuario, "  RRHH2@Empresa.com ")
    with engine.connect() as conn:
        correo = conn.execute(text("SELECT correo FROM usuarios WHERE id = :i"), {"i": gente["rrhh2"].id}).scalar()
    assert correo == "rrhh2@empresa.com"
    seguridad.cambiar_correo(gente["rrhh2"].usuario, "")  # vacio lo quita
    with engine.connect() as conn:
        assert conn.execute(text("SELECT correo FROM usuarios WHERE id = :i"), {"i": gente["rrhh2"].id}).scalar() is None
