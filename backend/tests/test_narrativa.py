"""Pruebas del motor de narrativa (paso 5).

NO necesitan Ollama ni conexion a internet: el modelo se sustituye por un
proveedor falso y el cliente de Ollama se prueba contra un servidor simulado.
Lo que se verifica es que el SISTEMA se comporte bien aunque el modelo se
equivoque: rechaza cifras inventadas, causalidad y citas falsas, y cae a la
plantilla cuando hace falta.

Requiere PostgreSQL con datos cargados (python -m scripts.seed).
Ejecutar desde la carpeta backend:  python -m pytest -q
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.guardrails import extraer_numeros, validar_narrativa
from app.kpis import calcular_kpis
from app.llm import OllamaProveedor, ProveedorNoDisponible, obtener_proveedor
from app.main import app, kpis_df
from app.narrativa import (
    ESQUEMA_NARRATIVA,
    cifras_de,
    confianza_de,
    conteo_estados,
    construir_hechos,
    construir_mensajes,
    generar_narrativa,
    narrativa_plantilla,
)


# ------------------------------------------------------------------ apoyo
@pytest.fixture(scope="module")
def df():
    return calcular_kpis()


@pytest.fixture(scope="module")
def id_area(df):
    por_nombre = dict(zip(df["area"], df["area_id"]))
    return por_nombre.__getitem__


@pytest.fixture(autouse=True)
def sin_ia_real():
    """Ninguna prueba debe llamar a un Ollama real, aunque este instalado."""
    app.dependency_overrides[obtener_proveedor] = lambda: None
    yield
    app.dependency_overrides.clear()


class ProveedorFalso:
    nombre = "falso"
    modelo = "modelo-falso"

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def generar(self, mensajes, esquema):
        self.llamadas.append(mensajes)
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


def respuesta_buena(hechos):
    """Lo que devolveria un modelo bien portado: cifras copiadas y hechos citados."""
    return json.dumps(
        {
            "resumen": "Este mes hay indicadores que requieren atención de la dirección.",
            "hallazgos": [
                {"titulo": h["nombre"], "texto": f"{h['nombre']} fue {h['valor_texto']}.", "hechos": [h["id"]]}
                for h in hechos[:3]
            ],
            "recomendaciones": [
                {"accion": "Dar seguimiento al indicador con el área.", "hechos": [hechos[0]["id"]]}
            ],
        },
        ensure_ascii=False,
    )


def con_cambio(lista_de_hechos, **cambios):
    """Respuesta buena con una modificacion en el primer hallazgo."""
    r = json.loads(respuesta_buena(lista_de_hechos))
    r["hallazgos"][0].update(cambios)
    return json.dumps(r, ensure_ascii=False)


@pytest.fixture(scope="module")
def caso(df, id_area):
    """Operaciones en abril de 2026 (mes de la crisis sembrada)."""
    periodo = pd.Timestamp("2026-04-01")
    return periodo, id_area("Operaciones"), construir_hechos(df, periodo, id_area("Operaciones"))


# ------------------------------------------------------------- guardarrailes
def test_extraer_numeros():
    assert extraer_numeros("fue 4.1 %") == [4.1]
    assert extraer_numeros("fue 4,1 puntos") == [4.1]
    assert extraer_numeros("costó 13,126 MXN") == [13126.0]
    assert extraer_numeros("H01 y H12 en abril de 2026, periodo 2026-04") == []


def buenos(hechos):
    return json.loads(respuesta_buena(hechos))


def test_narrativa_buena_no_tiene_errores(caso):
    _, _, hechos = caso
    assert validar_narrativa(buenos(hechos), hechos, cifras_de(*conteo_estados(hechos).values())) == []


def test_rechaza_cifra_inventada(caso):
    _, _, hechos = caso
    r = json.loads(con_cambio(hechos, texto="La rotación subió 37.5 % este mes."))
    errores = validar_narrativa(r, hechos, set())
    assert any("cifras que no estan" in e and "37.5" in e for e in errores)


def test_acepta_cifra_con_coma_decimal(caso):
    _, _, hechos = caso
    h = hechos[0]
    coma = h["valor_texto"].split()[0].replace(".", ",")
    r = json.loads(con_cambio(hechos, texto=f"El indicador cerró en {coma}."))
    assert validar_narrativa(r, hechos, set()) == []


def test_rechaza_cifra_de_otro_hecho_no_citado(caso):
    """El texto usa una cifra real, pero de un hecho que este hallazgo no cita."""
    _, _, hechos = caso
    otra = next(h for h in hechos[1:] if h["valor_texto"].split()[0] not in hechos[0]["valor_texto"])
    r = json.loads(con_cambio(hechos, texto=f"Cerró en {otra['valor_texto']}."))
    assert validar_narrativa(r, hechos, set())  # hay errores


@pytest.mark.parametrize(
    "frase",
    [
        "La baja de clima causó la rotación.",
        "La rotación subió debido a la carga de trabajo.",
        "Esto se debe a la falta de liderazgo.",
        "El resultado se dio gracias a la capacitación.",
        "Provocó una caída en la productividad.",
    ],
)
def test_rechaza_causalidad(caso, frase):
    _, _, hechos = caso
    r = json.loads(con_cambio(hechos, texto=frase))
    assert any("causalidad" in e for e in validar_narrativa(r, hechos, set()))


def test_permite_coincidencia_y_la_palabra_causas_como_sustantivo(caso):
    _, _, hechos = caso
    ok = "El clima y la rotación coinciden en el mismo periodo. Conviene investigar las causas."
    r = json.loads(con_cambio(hechos, texto=ok))
    assert validar_narrativa(r, hechos, set()) == []


def test_rechaza_hecho_inexistente_y_sin_citas(caso):
    _, _, hechos = caso
    r = json.loads(con_cambio(hechos, hechos=["H99"]))
    assert any("no existen" in e for e in validar_narrativa(r, hechos, set()))
    r = json.loads(con_cambio(hechos, hechos=[]))
    assert any("no cita ningun hecho" in e for e in validar_narrativa(r, hechos, set()))


def test_rechaza_estructura_incompleta(caso):
    _, _, hechos = caso
    assert validar_narrativa("texto suelto", hechos, set())
    assert validar_narrativa({"resumen": "x"}, hechos, set())
    r = buenos(hechos)
    r["hallazgos"] = r["hallazgos"][:1]  # el PRD pide entre 3 y 5
    assert any("entre 3 y 5" in e for e in validar_narrativa(r, hechos, set()))


# ---------------------------------------------------------------- confianza
def test_confianza_por_reglas():
    assert confianza_de(n=300, meses_historia=24, hay_variacion_mensual=True)[0] == "alta"
    assert confianza_de(n=20, meses_historia=24, hay_variacion_mensual=True)[0] == "media"
    assert confianza_de(n=5, meses_historia=24, hay_variacion_mensual=True)[0] == "baja"
    assert confianza_de(n=300, meses_historia=2, hay_variacion_mensual=True)[0] == "baja"
    assert confianza_de(n=300, meses_historia=4, hay_variacion_mensual=True)[0] == "media"
    assert confianza_de(n=300, meses_historia=24, hay_variacion_mensual=False)[0] == "media"


# ------------------------------------------------------------------- hechos
def test_hechos_ordenados_por_severidad_con_ids_consecutivos(caso):
    _, _, hechos = caso
    assert [h["id"] for h in hechos] == [f"H{i:02d}" for i in range(1, len(hechos) + 1)]
    severidad = {"rojo": 0, "amarillo": 1, "verde": 2}
    orden = [severidad[h["estado"]] for h in hechos]
    assert orden == sorted(orden)
    assert hechos[0]["estado"] == "rojo"


def test_los_valores_suprimidos_no_llegan_al_modelo(df, id_area):
    """Legal (4 personas): clima y desempeno estan ocultos; el prompt no debe ni mencionarlos."""
    periodo, legal = df["periodo"].max(), id_area("Legal")
    hechos = construir_hechos(df, periodo, legal)
    assert {h["indicador"] for h in hechos}.isdisjoint({"enps", "cumplimiento_metas"})
    prompt = "\n".join(m["content"] for m in construir_mensajes(hechos, periodo, "Legal"))
    assert "eNPS" not in prompt and "Cumplimiento de metas" not in prompt


def test_muestras_diminutas_tienen_confianza_baja(df, id_area):
    hechos = construir_hechos(df, df["periodo"].max(), id_area("Legal"))
    assert {h["confianza"] for h in hechos} == {"baja"}


def test_el_prompt_no_lleva_datos_personales_ni_floats_crudos(caso):
    periodo, _, hechos = caso
    prompt = "\n".join(m["content"] for m in construir_mensajes(hechos, periodo, "Operaciones"))
    assert "E0" not in prompt  # ningun codigo de empleado
    assert "abril de 2026" in prompt
    assert "no calcules" in prompt.lower()


def test_la_plantilla_pasa_los_guardarrailes_en_todas_las_areas_y_meses(df):
    """Propiedad: el respaldo determinista siempre es una narrativa valida."""
    combinaciones = 0
    for area_id in df["area_id"].unique():
        area = df.loc[df["area_id"] == area_id, "area"].iloc[0]
        for periodo in pd.to_datetime(df["periodo"].unique()):
            hechos = construir_hechos(df, periodo, area_id)
            if not hechos:
                continue
            cuerpo = narrativa_plantilla(hechos, periodo, area)
            errores = validar_narrativa(cuerpo, hechos, cifras_de(*conteo_estados(hechos).values()))
            assert errores == [], f"{area} {periodo:%Y-%m}: {errores}"
            combinaciones += 1
    assert combinaciones == 7 * 24


# ------------------------------------------------------------- orquestacion
def test_sin_proveedor_usa_plantilla_y_exige_revision(df, caso):
    periodo, area_id, _ = caso
    n = generar_narrativa(periodo, area_id, proveedor=None, df=df)
    assert n["origen"] == "plantilla" and n["proveedor"] is None
    assert n["requiere_revision"] is True
    for item in n["hallazgos"] + n["recomendaciones"]:
        assert item["confianza"] in {"alta", "media", "baja"}
        assert item["fuentes"] and item["hechos"]


def test_respuesta_valida_del_modelo_se_acepta(df, caso):
    periodo, area_id, hechos = caso
    prov = ProveedorFalso(respuesta_buena(hechos))
    n = generar_narrativa(periodo, area_id, proveedor=prov, df=df)
    assert n["origen"] == "llm" and n["modelo"] == "modelo-falso"
    assert n["advertencias"] == []
    assert len(prov.llamadas) == 1
    # la confianza de cada hallazgo la pone el codigo, no el modelo
    assert all(h["confianza"] in {"alta", "media", "baja"} for h in n["hallazgos"])


def test_reintenta_con_los_errores_y_acepta_la_correccion(df, caso):
    periodo, area_id, hechos = caso
    mala = con_cambio(hechos, texto="La rotación subió 99.9 % este mes.")
    prov = ProveedorFalso(mala, respuesta_buena(hechos))
    n = generar_narrativa(periodo, area_id, proveedor=prov, df=df)
    assert n["origen"] == "llm"
    assert len(prov.llamadas) == 2
    assert len(n["advertencias"]) == 1 and "99.9" in n["advertencias"][0]
    # el segundo intento incluye la respuesta mala y los errores detectados
    ultimo = prov.llamadas[1][-1]["content"]
    assert "problemas" in ultimo and "99.9" in ultimo


def test_si_el_modelo_insiste_en_inventar_cifras_cae_a_la_plantilla(df, caso):
    periodo, area_id, hechos = caso
    mala = con_cambio(hechos, texto="La rotación subió 99.9 % este mes.")
    n = generar_narrativa(periodo, area_id, proveedor=ProveedorFalso(mala, mala), df=df)
    assert n["origen"] == "plantilla"
    assert "99.9" not in json.dumps(n["hallazgos"], ensure_ascii=False)
    assert any("plantilla" in a for a in n["advertencias"])


def test_si_el_modelo_no_devuelve_json_cae_a_la_plantilla(df, caso):
    periodo, area_id, _ = caso
    n = generar_narrativa(periodo, area_id, proveedor=ProveedorFalso("no soy json", "tampoco"), df=df)
    assert n["origen"] == "plantilla"
    assert any("JSON" in a for a in n["advertencias"])


def test_si_el_modelo_no_esta_disponible_cae_a_la_plantilla(df, caso):
    periodo, area_id, _ = caso
    prov = ProveedorFalso(ProveedorNoDisponible("Ollama apagado"))
    n = generar_narrativa(periodo, area_id, proveedor=prov, df=df)
    assert n["origen"] == "plantilla"
    assert len(prov.llamadas) == 1  # no reintenta si el modelo ni siquiera responde
    assert any("Ollama apagado" in a for a in n["advertencias"])


def test_periodo_o_area_inexistentes(df):
    with pytest.raises(ValueError):
        generar_narrativa("2030-01-01", 0, df=df)
    with pytest.raises(ValueError):
        generar_narrativa(None, 99, df=df)


# ---------------------------------------------------------- cliente Ollama
class _OllamaSimulado(BaseHTTPRequestHandler):
    def do_POST(self):
        cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.ultima = {"ruta": self.path, "cuerpo": cuerpo}
        codigo, respuesta = self.server.respuesta
        datos = json.dumps(respuesta).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def log_message(self, *args):
        pass


@pytest.fixture()
def servidor_ollama():
    servidor = HTTPServer(("127.0.0.1", 0), _OllamaSimulado)
    servidor.respuesta = (200, {"message": {"role": "assistant", "content": '{"ok": true}'}})
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield servidor
    servidor.shutdown()


def test_cliente_ollama_arma_la_peticion_y_lee_la_respuesta(servidor_ollama):
    url = f"http://127.0.0.1:{servidor_ollama.server_port}"
    prov = OllamaProveedor(modelo="llama3.1:8b", url=url, timeout=5)
    mensajes = [{"role": "user", "content": "hola"}]
    assert prov.generar(mensajes, ESQUEMA_NARRATIVA) == '{"ok": true}'

    recibido = servidor_ollama.ultima
    assert recibido["ruta"] == "/api/chat"
    assert recibido["cuerpo"]["model"] == "llama3.1:8b"
    assert recibido["cuerpo"]["stream"] is False
    assert recibido["cuerpo"]["format"] == ESQUEMA_NARRATIVA
    assert recibido["cuerpo"]["messages"] == mensajes


def test_cliente_ollama_modelo_no_descargado_da_pista(servidor_ollama):
    servidor_ollama.respuesta = (404, {"error": "model 'x' not found"})
    prov = OllamaProveedor(modelo="x", url=f"http://127.0.0.1:{servidor_ollama.server_port}", timeout=5)
    with pytest.raises(ProveedorNoDisponible, match="ollama pull x"):
        prov.generar([{"role": "user", "content": "hola"}], ESQUEMA_NARRATIVA)


def test_cliente_ollama_apagado(monkeypatch):
    prov = OllamaProveedor(modelo="x", url="http://127.0.0.1:9", timeout=2)  # puerto sin servicio
    with pytest.raises(ProveedorNoDisponible, match="Ollama"):
        prov.generar([{"role": "user", "content": "hola"}], ESQUEMA_NARRATIVA)


def test_proveedor_configurable_desde_el_entorno(monkeypatch):
    monkeypatch.setenv("LLM_PROVEEDOR", "ninguno")
    assert obtener_proveedor() is None
    monkeypatch.setenv("LLM_PROVEEDOR", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "phi3:mini")
    assert obtener_proveedor().modelo == "phi3:mini"


# ------------------------------------------------------------------- API
@pytest.fixture()
def client():
    return TestClient(app)


def test_api_narrativa_sin_ia(client):
    r = client.post("/narrativas", json={"usar_ia": False})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["origen"] == "plantilla"
    assert cuerpo["periodo"] == "2026-08" and cuerpo["area"] == "Corporativo"
    assert cuerpo["requiere_revision"] is True
    assert cuerpo["hechos"] and cuerpo["hallazgos"]


def test_api_narrativa_con_modelo_simulado(client, id_area):
    df = kpis_df()
    hechos = construir_hechos(df, pd.Timestamp("2026-02-01"), id_area("Operaciones"))
    app.dependency_overrides[obtener_proveedor] = lambda: ProveedorFalso(respuesta_buena(hechos))
    r = client.post("/narrativas", json={"periodo": "2026-02", "area_id": id_area("Operaciones")})
    assert r.status_code == 200
    assert r.json()["origen"] == "llm"
    assert r.json()["modelo"] == "modelo-falso"


def test_api_narrativa_usar_ia_false_ignora_el_modelo(client):
    llamado = ProveedorFalso()  # si se le llamara, fallaria (sin respuestas)
    app.dependency_overrides[obtener_proveedor] = lambda: llamado
    assert client.post("/narrativas", json={"usar_ia": False}).json()["origen"] == "plantilla"
    assert llamado.llamadas == []


@pytest.mark.parametrize(
    "cuerpo, codigo",
    [
        ({"periodo": "2030-01"}, 404),
        ({"area_id": 99}, 404),
        ({"periodo": "2026-13"}, 422),
    ],
)
def test_api_narrativa_errores(client, cuerpo, codigo):
    assert client.post("/narrativas", json=cuerpo).status_code == codigo
