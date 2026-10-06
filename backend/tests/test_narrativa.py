"""Pruebas del motor de narrativa (paso 5).

NO necesitan Ollama, Groq ni conexion a internet: el modelo se sustituye por
un proveedor falso y los clientes HTTP se prueban contra servidores simulados.
Lo que se verifica es que el SISTEMA se comporte bien aunque el modelo se
equivoque: rechaza cifras inventadas, causalidad y citas falsas, y si el
modelo no lo logra falla de forma explicita (nunca rellena con otro texto).

Requiere PostgreSQL con datos cargados (python -m scripts.seed).
Ejecutar desde la carpeta backend:  python -m pytest -q
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from sqlalchemy import text

from app import trabajos
from app.database import engine
from app.guardrails import cifras_permitidas, extraer_numeros, validar_narrativa
from app.kpis import calcular_kpis
from app.llm import (
    ConfiguracionIA,
    GroqProveedor,
    OllamaProveedor,
    ProveedorNoDisponible,
    esquema_estricto,
    obtener_proveedor,
)
from app.main import app, kpis_df, proveedor_configurado
from app.narrativa import (
    ESQUEMA_NARRATIVA,
    INTENTOS,
    NarrativaNoGenerada,
    cifras_de,
    confianza_de,
    conteo_estados,
    construir_hechos,
    construir_mensajes,
    detectar_coincidencias,
    es_mes_estable,
    esquema_narrativa,
    evolucion_de,
    generar_narrativa,
    hechos_para_modelo,
    motivo_de_vigilancia,
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
    """Ninguna prueba debe llamar a un Ollama o Groq real, aunque este configurado.
    Por defecto la API recibe un proveedor sin respuestas: si se le llamara, fallaria."""
    app.dependency_overrides[proveedor_configurado] = lambda: ProveedorFalso()
    yield
    app.dependency_overrides.clear()


class _Inmediato:
    """Ejecutor que corre la tarea en el momento (en vez de en otro hilo)."""

    def submit(self, fn, *args):
        fn(*args)


class _Diferido:
    """Ejecutor que guarda las tareas para correrlas cuando la prueba quiera."""

    def __init__(self):
        self.pendientes = []

    def submit(self, fn, *args):
        self.pendientes.append((fn, args))

    def correr(self):
        while self.pendientes:
            fn, args = self.pendientes.pop(0)
            fn(*args)


@pytest.fixture(autouse=True)
def ejecutor_inmediato(monkeypatch):
    monkeypatch.setattr(trabajos, "ejecutor", _Inmediato())


class ProveedorFalso:
    nombre = "falso"
    modelo = "modelo-falso"

    def __init__(self, *respuestas, local=True):
        self.local = local
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.esquemas = []

    def generar(self, mensajes, esquema):
        self.llamadas.append(mensajes)
        self.esquemas.append(esquema)
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


def respuesta_buena(hechos):
    """Lo que devolveria un modelo bien portado: resumen con cifras, un hallazgo
    por cada rojo (los amarillos y los "por vigilar" agrupados aparte) con sus
    valores copiados, y una recomendacion por cada rojo. Cita solo los hechos
    que se le entregan."""
    visibles = hechos_para_modelo(hechos)  # alertas y "por vigilar"
    c = conteo_estados(hechos)
    # hasta 5 hallazgos individuales; el resto (si lo hay) se agrupa en uno solo
    individuales, agrupados = (visibles, []) if len(visibles) <= 5 else (visibles[:4], visibles[4:])
    hallazgos = [
        {"titulo": h["nombre"], "texto": f"{h['nombre']} fue {h['valor_texto']}.", "hechos": [h["id"]]}
        for h in individuales
    ]
    if agrupados:
        detalle = "; ".join(f"{h['nombre']} {h['valor_texto']}" for h in agrupados)
        hallazgos.append(
            {"titulo": "Otros indicadores", "texto": f"También: {detalle}.",
             "hechos": [h["id"] for h in agrupados]}
        )
    rojos = [h for h in visibles if h["estado"] == "rojo"] or visibles[:1]
    return json.dumps(
        {
            "resumen": f"Hay {c['rojo']} indicadores en rojo y {c['amarillo']} en amarillo este mes.",
            "hallazgos": hallazgos,
            "recomendaciones": [
                {"accion": "Dar seguimiento al indicador con el área.", "hechos": [h["id"]]} for h in rojos[:3]
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


@pytest.fixture(scope="module")
def visibles(caso):
    """Los hechos que ve el modelo (solo alertas)."""
    return hechos_para_modelo(caso[2])


# ------------------------------------------------------------- guardarrailes
def test_extraer_numeros():
    assert extraer_numeros("fue 4.1 %") == [4.1]
    assert extraer_numeros("fue 4,1 puntos") == [4.1]
    assert extraer_numeros("costó 13,126 MXN") == [13126.0]
    assert extraer_numeros("H01 y H12 en abril de 2026, periodo 2026-04") == []


def buenos(hechos):
    return json.loads(respuesta_buena(hechos))


def test_narrativa_buena_no_tiene_errores(caso, visibles):
    _, _, hechos = caso
    assert validar_narrativa(buenos(hechos), visibles, cifras_de(*conteo_estados(hechos).values())) == []


def test_rechaza_cifra_inventada(caso, visibles):
    _, _, hechos = caso
    r = json.loads(con_cambio(hechos, texto="La rotación subió 37.5 % este mes."))
    errores = validar_narrativa(r, visibles, set())
    assert any("cifras que no estan" in e and "37.5" in e for e in errores)


def test_acepta_cifra_con_coma_decimal(caso, visibles):
    _, _, hechos = caso
    coma = visibles[0]["valor_texto"].split()[0].replace(".", ",")
    r = json.loads(con_cambio(hechos, texto=f"El indicador cerró en {coma}."))
    assert validar_narrativa(r, visibles, cifras_de(*conteo_estados(hechos).values())) == []


def test_rechaza_cifra_de_otro_hecho_no_citado(caso, visibles):
    """El texto usa una cifra real, pero de un hecho que este hallazgo no cita."""
    _, _, hechos = caso
    otra = next(h for h in visibles[1:] if h["valor_texto"].split()[0] not in visibles[0]["valor_texto"])
    r = json.loads(con_cambio(hechos, texto=f"Cerró en {otra['valor_texto']}."))
    assert validar_narrativa(r, visibles, set())  # hay errores


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
def test_rechaza_causalidad(caso, visibles, frase):
    _, _, hechos = caso
    r = json.loads(con_cambio(hechos, texto=frase))
    assert any("causalidad" in e for e in validar_narrativa(r, visibles, set()))


def test_permite_coincidencia_y_la_palabra_causas_como_sustantivo(caso, visibles):
    _, _, hechos = caso
    ok = "El clima y la rotación coinciden en el mismo periodo. Conviene investigar las causas."
    r = json.loads(con_cambio(hechos, texto=f"{visibles[0]['valor_texto']}: {ok}"))
    assert validar_narrativa(r, visibles, cifras_de(*conteo_estados(hechos).values())) == []


def test_rechaza_hecho_inexistente_y_sin_citas(caso, visibles):
    _, _, hechos = caso
    r = json.loads(con_cambio(hechos, hechos=["H99"]))
    assert any("no se te entregaron" in e for e in validar_narrativa(r, visibles, set()))
    r = json.loads(con_cambio(hechos, hechos=[]))
    assert any("no cita ningun hecho" in e for e in validar_narrativa(r, visibles, set()))


def test_rechaza_estructura_incompleta(caso, visibles):
    _, _, hechos = caso
    assert validar_narrativa("texto suelto", visibles, set())
    assert validar_narrativa({"resumen": "x"}, visibles, set())
    r = buenos(hechos)
    r["hallazgos"] = r["hallazgos"][:1]  # el PRD pide entre 3 y 5
    assert any("entre 3 y 5" in e for e in validar_narrativa(r, visibles, set()))


# --- reglas nuevas, surgidas de la prueba real con Llama 3.1 8B (prompt v1) ---
def test_rechaza_citar_hechos_en_verde_que_no_se_le_entregaron(caso, visibles):
    _, _, hechos = caso
    verde = next(h for h in hechos if h["estado"] == "verde")
    r = json.loads(con_cambio(hechos, hechos=[verde["id"]]))
    assert any("no se te entregaron" in e for e in validar_narrativa(r, visibles, set()))


def test_exige_cubrir_todos_los_hechos_en_rojo(caso, visibles):
    _, _, hechos = caso
    r = buenos(hechos)
    rojo = next(h for h in visibles if h["estado"] == "rojo")
    for h in r["hallazgos"]:
        h["hechos"] = [x for x in h["hechos"] if x != rojo["id"]] or [visibles[-1]["id"]]
    errores = validar_narrativa(r, visibles, cifras_de(*conteo_estados(hechos).values()))
    assert any(rojo["id"] in e and "rojo" in e for e in errores)


@pytest.mark.parametrize(
    "frase",
    [
        "El eNPS supera el umbral crítico.",
        "La rotación quedó por encima del umbral de atención.",
        "Se ubica por debajo del umbral crítico.",
    ],
)
def test_rechaza_comparar_contra_umbrales(caso, visibles, frase):
    _, _, hechos = caso
    r = json.loads(con_cambio(hechos, texto=frase))
    assert any("umbral" in e for e in validar_narrativa(r, visibles, set()))


def test_permite_hablar_de_umbrales_con_la_frase_neutra(caso, visibles):
    _, _, hechos = caso
    r = json.loads(con_cambio(hechos, texto=f"Cerró en {visibles[0]['valor_texto']} y ya cruzó el umbral crítico."))
    assert validar_narrativa(r, visibles, cifras_de(*conteo_estados(hechos).values())) == []


def test_rechaza_que_el_modelo_hable_de_confianza(caso, visibles):
    _, _, hechos = caso
    r = json.loads(con_cambio(hechos, texto="La confianza en este dato es baja."))
    assert any("confianza" in e for e in validar_narrativa(r, visibles, set()))


def test_rechaza_textos_demasiado_largos(caso, visibles):
    _, _, hechos = caso
    largo = "Primera idea. Segunda idea. Tercera idea. Cuarta idea."
    r = json.loads(con_cambio(hechos, texto=largo))
    assert any("demasiado largo" in e for e in validar_narrativa(r, visibles, set()))
    r = buenos(hechos)
    r["resumen"] = largo
    assert any("demasiado largo" in e for e in validar_narrativa(r, visibles, set()))


def test_cifras_decimales_no_cuentan_como_oraciones_distintas(caso, visibles):
    _, _, hechos = caso
    r = json.loads(con_cambio(hechos, texto=f"Cerró en {visibles[0]['valor_texto']}. Empeoró."))
    assert not any("largo" in e for e in validar_narrativa(r, visibles, set()))


def test_rechaza_hallazgos_y_resumen_sin_cifras(caso, visibles):
    _, _, hechos = caso
    r = json.loads(con_cambio(hechos, texto="El indicador está en una situación delicada."))
    assert any("no incluye el valor" in e for e in validar_narrativa(r, visibles, set()))
    r = buenos(hechos)
    r["resumen"] = "El área enfrenta desafíos en varios indicadores clave."
    assert any("resumen: no incluye ninguna cifra" in e for e in validar_narrativa(r, visibles, set()))


def test_exige_cubrir_tambien_las_alertas_amarillas_pero_permite_agruparlas(caso, visibles):
    _, _, hechos = caso
    cifras = cifras_de(*conteo_estados(hechos).values())
    r = buenos(hechos)                      # la respuesta buena agrupa los amarillos
    assert validar_narrativa(r, visibles, cifras) == []
    amarillo = next(h for h in visibles if h["estado"] == "amarillo")
    for h in r["hallazgos"]:
        h["hechos"] = [x for x in h["hechos"] if x != amarillo["id"]] or [visibles[0]["id"]]
    assert any(amarillo["id"] in e and "amarillo" in e for e in validar_narrativa(r, visibles, cifras))


def test_exige_una_recomendacion_por_cada_hecho_en_rojo(caso, visibles):
    _, _, hechos = caso
    r = buenos(hechos)
    rojo = next(h for h in visibles if h["estado"] == "rojo")
    r["recomendaciones"] = [x for x in r["recomendaciones"] if x["hechos"] != [rojo["id"]]] or [
        {"accion": "Dar seguimiento.", "hechos": [visibles[-1]["id"]]}
    ]
    errores = validar_narrativa(r, visibles, cifras_de(*conteo_estados(hechos).values()))
    assert any("Ninguna recomendacion cubre" in e and rojo["id"] in e for e in errores)


def test_se_deben_como_obligacion_no_es_causalidad_pero_se_debe_a_si(caso, visibles):
    _, _, hechos = caso
    cifras = cifras_de(*conteo_estados(hechos).values())
    valor = visibles[0]["valor_texto"]
    ok = json.loads(con_cambio(hechos, texto=f"Cerró en {valor}. Se deben revisar las metas."))
    assert validar_narrativa(ok, visibles, cifras) == []
    mal = json.loads(con_cambio(hechos, texto=f"Cerró en {valor}. Esto se debe a la carga."))
    assert any("causalidad" in e for e in validar_narrativa(mal, visibles, cifras))


def test_regresion_segunda_salida_real_de_llama31_prompt_v2(caso, visibles):
    """Version aceptada tras un reintento: cumplia las reglas v2 pero era vacia
    (sin cifras, amarillos ignorados, sin recomendacion para el eNPS)."""
    periodo, _, hechos = caso
    if [h["indicador"] for h in hechos[:2]] != ["enps", "rotacion_total"]:
        pytest.skip("Los datos sembrados difieren de los usados para capturar esta salida")
    real = {
        "resumen": "El área Operaciones enfrenta desafíos en varios indicadores clave. El eNPS ya cruzó el "
        "umbral crítico. Se observan coincidencias entre algunos de estos indicadores.",
        "hallazgos": [
            {"titulo": "eNPS en alerta", "texto": "El eNPS ya cruzó el umbral crítico.", "hechos": ["H01"]},
            {"titulo": "Tasa de rotación mensual en alerta",
             "texto": "La Tasa de rotación mensual ya cruzó el umbral crítico.", "hechos": ["H02"]},
            {"titulo": "Coincidencias entre indicadores",
             "texto": "Se observan coincidencias entre el eNPS y la Tasa de rotación mensual.",
             "hechos": ["H01", "H02"]},
        ],
        "recomendaciones": [
            {"accion": "Revisar con la gerencia del área los patrones de las bajas del periodo", "hechos": ["H02"]},
            {"accion": "Revisar con los líderes si las metas asignadas son alcanzables", "hechos": ["H03"]},
            {"accion": "Analizar la planeación de entregables y la carga de trabajo del área", "hechos": ["H04"]},
        ],
    }
    texto = " | ".join(validar_narrativa(real, visibles, cifras_de(*conteo_estados(hechos).values())))
    assert "resumen: no incluye ninguna cifra" in texto
    assert "no incluye el valor de" in texto   # hallazgos vacios (sin cifra de lo que citan)
    assert "Ningun hallazgo cubre el hecho H05" in texto                # amarillos ignorados
    assert "Ninguna recomendacion cubre el hecho H01" in texto          # eNPS sin recomendacion


def test_regresion_salida_real_de_llama31_8b_con_prompt_v1(caso, visibles):
    """La respuesta que dio Llama 3.1 8B con el prompt v1 pasaba las reglas
    antiguas (sin cifras inventadas) pero tenia errores de criterio. Con las
    reglas actuales debe ser rechazada."""
    periodo, _, hechos = caso
    if [h["indicador"] for h in hechos[:2]] != ["enps", "rotacion_total"]:
        pytest.skip("Los datos sembrados difieren de los usados para capturar esta salida")
    real = {
        "resumen": (
            "El área de Operaciones enfrenta desafíos en varios indicadores clave, destacando la "
            "situación crítica del eNPS y la tasa de rotación mensual. A pesar de algunos avances en "
            "indicadores como la cobertura de capacitación y la tasa de finalización de cursos, la "
            "confianza en algunos de los hechos es baja. Es importante abordar estos problemas para "
            "mejorar la eficiencia y satisfacción de los empleados."
        ),
        "hallazgos": [
            {
                "titulo": "Situación crítica del eNPS",
                "texto": "El eNPS ha caído a -23.2 puntos, lo que supera el umbral crítico de 0 puntos. "
                "Aunque ha mejorado en comparación con el mes anterior (+22.6 puntos), sigue siendo un "
                "problema significativo.",
                "hechos": ["H01"],
            },
            {
                "titulo": "Tasa de rotación mensual en rojo",
                "texto": "La tasa de rotación mensual es del 4.1 %, lo que supera el umbral de atención de "
                "2.0 %. Aunque ha aumentado en comparación con el mismo mes del año anterior (+4.1 pts), "
                "sigue siendo un problema.",
                "hechos": ["H02"],
            },
            {
                "titulo": "Cobertura de capacitación y tasa de finalización de cursos en verde",
                "texto": "La cobertura de capacitación es del 96.9 % y la tasa de finalización de cursos es "
                "del 81.4 %, lo que supera los umbrales de atención. Aunque la confianza en algunos de "
                "estos hechos es baja, son indicadores positivos.",
                "hechos": ["H07", "H09"],
            },
        ],
        "recomendaciones": [
            {
                "accion": "Revisar y mejorar la estrategia de capacitación y desarrollo de empleados",
                "hechos": ["H01", "H07", "H09"],
            },
            {"accion": "Implementar medidas para reducir la tasa de rotación mensual", "hechos": ["H02"]},
            {"accion": "Revisar y ajustar la estrategia de contratación y selección de personal", "hechos": ["H08"]},
        ],
    }
    errores = validar_narrativa(real, visibles, cifras_de(*conteo_estados(hechos).values()))
    texto = " | ".join(errores)
    assert "umbral" in texto                      # comparaciones contra umbrales (direccion invertida en el eNPS)
    assert "confianza" in texto                   # comentario inventado sobre la confianza
    assert "no se te entregaron" in texto         # hallazgo y recomendaciones apoyados en hechos en verde
    assert len(errores) >= 5


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


def test_evolucion_se_calcula_segun_el_sentido_del_indicador():
    assert evolucion_de(22.6, "menor_es_peor") == "mejoró"    # el eNPS subio: mejor
    assert evolucion_de(0.8, "mayor_es_peor") == "empeoró"    # la rotacion subio: peor
    assert evolucion_de(-3.6, "menor_es_peor") == "empeoró"   # la productividad bajo: peor
    assert evolucion_de(-2.0, "mayor_es_peor") == "mejoró"    # el tiempo de contratacion bajo: mejor
    assert evolucion_de(0.04, "mayor_es_peor") == "sin cambio"
    assert evolucion_de(None, "mayor_es_peor") is None


def test_el_prompt_no_entrega_umbrales_ni_valores_de_indicadores_en_verde(caso):
    periodo, _, hechos = caso
    prompt = "\n".join(m["content"] for m in construir_mensajes(hechos, periodo, "Operaciones"))
    verde = next(h for h in hechos if h["estado"] == "verde")
    assert verde["valor_texto"] not in prompt          # ni la cifra del indicador en verde...
    assert verde["nombre"] in prompt                   # ...solo su nombre, como "sin alerta"
    assert "3.5" not in prompt                         # umbral critico de la rotacion
    assert "ya cruzó el umbral crítico" in prompt      # en su lugar, la frase neutra
    assert "(mejoró)" in prompt and "(empeoró)" in prompt


def test_el_sistema_detecta_coincidencias_entre_indicadores_en_alerta(caso):
    periodo, _, hechos = caso
    pares = {(a["indicador"], b["indicador"]) for a, b in detectar_coincidencias(hechos)}
    assert ("enps", "rotacion_total") in pares
    prompt = "\n".join(m["content"] for m in construir_mensajes(hechos, periodo, "Operaciones"))
    assert "no causas demostradas" in prompt


def test_los_valores_suprimidos_no_llegan_al_modelo(df, id_area):
    """Jurídico (4 personas): clima y desempeno estan ocultos; el prompt no debe ni mencionarlos."""
    periodo, legal = df["periodo"].max(), id_area("Jurídico")
    hechos = construir_hechos(df, periodo, legal)
    assert {h["indicador"] for h in hechos}.isdisjoint({"enps", "cumplimiento_metas"})
    prompt = "\n".join(m["content"] for m in construir_mensajes(hechos, periodo, "Jurídico"))
    assert "eNPS" not in prompt and "Cumplimiento de metas" not in prompt


def test_muestras_diminutas_tienen_confianza_baja(df, id_area):
    hechos = construir_hechos(df, df["periodo"].max(), id_area("Jurídico"))
    assert {h["confianza"] for h in hechos} == {"baja"}


def test_el_prompt_no_lleva_datos_personales_ni_floats_crudos(caso):
    periodo, _, hechos = caso
    prompt = "\n".join(m["content"] for m in construir_mensajes(hechos, periodo, "Operaciones"))
    assert "E0" not in prompt  # ningun codigo de empleado
    assert "abril de 2026" in prompt
    assert "ni calcules cifras" in prompt.lower()


@pytest.fixture(scope="module")
def caso_estable(df, id_area):
    """Ventas en octubre de 2024: todo en verde y nada por vigilar."""
    periodo = pd.Timestamp("2024-10-01")
    return periodo, id_area("Ventas"), construir_hechos(df, periodo, id_area("Ventas"))


def test_en_un_mes_estable_el_modelo_recibe_todos_los_indicadores(caso_estable):
    periodo, _, hechos = caso_estable
    assert es_mes_estable(hechos)
    assert hechos_para_modelo(hechos) == hechos
    prompt = "\n".join(m["content"] for m in construir_mensajes(hechos, periodo, "Ventas"))
    assert "mes estable" in prompt
    assert all(h["valor_texto"] in prompt for h in hechos)


def test_un_mes_con_alertas_no_es_estable(caso):
    assert not es_mes_estable(caso[2])


def test_el_mes_estable_tambien_lo_redacta_el_modelo(df, caso_estable):
    periodo, area_id, hechos = caso_estable
    prov = ProveedorFalso(respuesta_buena(hechos))
    n = generar_narrativa(periodo, area_id, proveedor=prov, df=df)
    assert len(prov.llamadas) == 1
    assert n["mes_estable"] is True and n["intentos"] == 1
    assert n["conteo_estados"]["rojo"] == 0 and n["hallazgos"]


def test_con_proveedor_en_la_nube_no_se_envia_el_nombre_del_area(df, caso):
    periodo, area_id, hechos = caso
    nube = ProveedorFalso(respuesta_buena(hechos), local=False)
    n = generar_narrativa(periodo, area_id, proveedor=nube, df=df)
    prompt = "\n".join(m["content"] for m in nube.llamadas[0])
    assert "Operaciones" not in prompt and "un área de la empresa" in prompt
    assert n["area"] == "Operaciones"  # el reporte si dice el area; solo el modelo no la ve

    local = ProveedorFalso(respuesta_buena(hechos))
    generar_narrativa(periodo, area_id, proveedor=local, df=df)
    assert "el área Operaciones" in "\n".join(m["content"] for m in local.llamadas[0])


# ------------------------------------------------------------- orquestacion
def test_sin_proveedor_no_hay_narrativa(df, caso):
    """Ya no existe la plantilla: sin modelo no se genera nada."""
    periodo, area_id, _ = caso
    with pytest.raises(ValueError, match="proveedor"):
        generar_narrativa(periodo, area_id, proveedor=None, df=df)


def test_respuesta_valida_del_modelo_se_acepta(df, caso):
    periodo, area_id, hechos = caso
    prov = ProveedorFalso(respuesta_buena(hechos))
    n = generar_narrativa(periodo, area_id, proveedor=prov, df=df)
    assert n["proveedor"] == "falso" and n["modelo"] == "modelo-falso"
    assert n["intentos"] == 1 and n["advertencias"] == []
    assert n["requiere_revision"] is True
    assert len(prov.llamadas) == 1
    # la confianza de cada hallazgo la pone el codigo, no el modelo
    for item in n["hallazgos"] + n["recomendaciones"]:
        assert item["confianza"] in {"alta", "media", "baja"}
        assert item["fuentes"] and item["hechos"]


def test_reintenta_con_los_errores_y_acepta_la_correccion(df, caso):
    periodo, area_id, hechos = caso
    mala = con_cambio(hechos, texto="La rotación subió 99.9 % este mes.")
    prov = ProveedorFalso(mala, respuesta_buena(hechos))
    n = generar_narrativa(periodo, area_id, proveedor=prov, df=df)
    assert n["intentos"] == 2
    assert len(prov.llamadas) == 2
    assert len(n["advertencias"]) == 1 and "99.9" in n["advertencias"][0]
    # el segundo intento incluye la respuesta mala y los errores detectados
    ultimo = prov.llamadas[1][-1]["content"]
    assert "problemas" in ultimo and "99.9" in ultimo


@pytest.mark.skipif(INTENTOS < 3, reason="requiere al menos 3 intentos")
def test_el_reintento_no_acumula_la_conversacion(df, caso):
    """Cada reintento lleva el prompt original + SOLO la ultima respuesta mala.
    Acumular todos los intentos rebasaba el contexto del modelo (4096 tokens)."""
    periodo, area_id, hechos = caso
    mala1 = con_cambio(hechos, texto="La rotación subió 99.9 % este mes.")
    mala2 = con_cambio(hechos, texto="La rotación subió 88.8 % este mes.")
    prov = ProveedorFalso(mala1, mala2, respuesta_buena(hechos))
    generar_narrativa(periodo, area_id, proveedor=prov, df=df)
    primera, tercera = prov.llamadas[0], prov.llamadas[2]
    assert len(tercera) == len(primera) + 2
    assert "88.8 %" in tercera[-2]["content"]  # solo la ultima respuesta mala...
    assert not any("subió 99.9 %" in m["content"] for m in tercera)  # ...la primera ya no viaja
    # pero el error del primer intento se le recuerda, en una linea, para que no lo repita
    assert "En intentos anteriores" in tercera[-1]["content"] and "99.9" in tercera[-1]["content"]


def test_el_error_de_largo_explica_como_corregirlo(caso, visibles):
    hechos = caso[2]
    r = buenos(hechos)
    r["hallazgos"][0]["texto"] += " Uno. Dos. Tres. Cuatro."
    errores = validar_narrativa(r, visibles, set())
    assert any("demasiado largo" in e and "hallazgos separados" in e for e in errores)


def test_no_pide_mas_hallazgos_que_hechos_citables(df, id_area):
    """Regresion (evaluacion real, Jurídico ago-2026): con 2 hechos se pedian
    "de 3 a 5" hallazgos y el tercero nunca podia pasar los guardarrailes.
    Hoy Jurídico ago-2026 tiene un solo hecho evaluable (la capacitacion quedo
    con muestra insuficiente): se pide exactamente 1."""
    periodo, legal = pd.Timestamp("2026-08-01"), id_area("Jurídico")
    hechos = construir_hechos(df, periodo, legal)
    visibles = hechos_para_modelo(hechos)
    assert len(visibles) == 1
    prompt = construir_mensajes(hechos, periodo, "Jurídico")[-1]["content"]
    assert "hallazgos\" (exactamente 1;" in prompt and "de 3 a 5" not in prompt
    for n, esperado in [(1, (1, 1)), (2, (2, 2)), (4, (3, 4)), (7, (3, 5))]:
        esquema = esquema_narrativa([f"H{i:02d}" for i in range(1, n + 1)])["properties"]["hallazgos"]
        assert (esquema["minItems"], esquema["maxItems"]) == esperado


def _hecho_pct(id_, nombre, valor, var_mes, var_anio, n):
    """Hecho minimo en % para probar los guardarrailes sin depender de los datos."""
    return {
        "id": id_, "nombre": nombre, "unidad": "%", "estado": "rojo", "en_vigilancia": False, "n": n,
        "valor_texto": f"{valor:.1f} %", "var_mes_ant_texto": f"{var_mes:+.1f} pts",
        "var_anio_ant_texto": f"{var_anio:+.1f} pts", "personas_texto": None,
    }


def test_regresion_salida_real_de_qwen3_en_legal_sin_valores():
    """Salida real de Qwen3 (Jurídico ago-2026, antes de la regla de muestra
    minima): escribe los cambios pero no los valores. El hallazgo 1 pasaba por
    casualidad: su cambio anual (-25.0 pts) coincide con su valor (25.0 %).
    Ambos deben rechazarse, y el error debe decirle al modelo el valor exacto."""
    visibles = [
        _hecho_pct("H01", "Cobertura de capacitación", 25.0, -75.0, -25.0, 4),
        _hecho_pct("H02", "Tasa de finalización de cursos", 0.0, -100.0, -50.0, 1),
    ]
    hechos = visibles
    salida = {
        "resumen": "En agosto hay 2 indicadores en rojo y 0 en amarillo.",
        "hallazgos": [
            {"titulo": "Cobertura de capacitación", "hechos": ["H01"],
             "texto": "La Cobertura de capacitación empeoró en -75.0 pts (empeoró) respecto al mes anterior y "
                      "en -25.0 pts (empeoró) respecto al mismo mes del año anterior, ya cruzó el umbral crítico."},
            {"titulo": "Tasa de finalización de cursos", "hechos": ["H02"],
             "texto": "La Tasa de finalización de cursos empeoró en -100.0 pts (empeoró) respecto al mes anterior y "
                      "en -50.0 pts (empeoró) respecto al mismo mes del año anterior, ya cruzó el umbral crítico."},
        ],
        "recomendaciones": [{"accion": "Reforzar la convocatoria.", "hechos": ["H01"]},
                            {"accion": "Revisar los horarios de los cursos.", "hechos": ["H02"]}],
    }
    errores = validar_narrativa(salida, visibles, cifras_de(*conteo_estados(hechos).values()))
    assert any("hallazgo 1" in e and "que es 25.0 %" in e for e in errores)
    assert any("hallazgo 2" in e and "que es 0.0 %" in e for e in errores)

    salida["hallazgos"][0]["texto"] = "La cobertura quedó en 25.0 % (-75.0 pts frente al mes anterior)."
    salida["hallazgos"][1]["texto"] = "La tasa de finalización quedó en 0 % (-100.0 pts)."
    assert validar_narrativa(salida, visibles, cifras_de(*conteo_estados(hechos).values())) == []


def test_muestra_insuficiente_no_llega_al_modelo_como_alerta(df, id_area):
    """Jurídico ago-2026: la capacitacion (4 empleados, 1 inscrito) se ve en el
    dashboard, pero no es un hecho: el modelo solo la nombra, sin cifras."""
    periodo, legal = pd.Timestamp("2026-08-01"), id_area("Jurídico")
    hechos = construir_hechos(df, periodo, legal)
    assert {h["indicador"] for h in hechos}.isdisjoint({"cobertura_capacitacion", "tasa_finalizacion"})
    prov = ProveedorFalso(respuesta_buena(hechos))
    n = generar_narrativa(periodo, legal, proveedor=prov, df=df)
    assert n["indicadores_sin_evaluar"] == ["Cobertura de capacitación", "Tasa de finalización de cursos"]
    prompt = prov.llamadas[0][-1]["content"]
    assert "sin evaluar por muestra insuficiente" in prompt and "Tasa de finalización de cursos" in prompt
    assert "0.0 %" not in prompt and "25.0 %" not in prompt


def test_capacitacion_lleva_el_conteo_de_personas(df, id_area):
    """En areas grandes, "18 de 80 inscritos no completaron" es mas claro que el % solo."""
    periodo = pd.Timestamp("2026-04-01")
    hechos = construir_hechos(df, periodo, id_area("Operaciones"))
    fin = next(h for h in hechos if h["indicador"] == "tasa_finalizacion")
    completaron = round(fin["valor"] * fin["n"] / 100)
    assert fin["personas_texto"] == (
        f"{completaron} de {fin['n']} inscritos completaron el curso ({fin['n'] - completaron} no)"
    )
    assert all(h["personas_texto"] is None for h in hechos if "capacitacion" not in h["indicador"]
               and h["indicador"] != "tasa_finalizacion")
    # el modelo puede citar esos conteos sin que cuenten como cifras inventadas
    assert {completaron, fin["n"], fin["n"] - completaron} <= cifras_permitidas(fin)


def test_con_muchos_hechos_pide_de_3_a_5_hallazgos(caso):
    periodo, _, hechos = caso
    assert len(hechos_para_modelo(hechos)) > 5
    assert "hallazgos\" (de 3 a 5;" in construir_mensajes(hechos, periodo, "Operaciones")[-1]["content"]


def test_el_mes_estable_pide_el_conteo_con_numeros(caso_estable):
    periodo, _, hechos = caso_estable
    prompt = construir_mensajes(hechos, periodo, "Ventas")[-1]["content"]
    assert f"0 indicadores en rojo y 0 en amarillo de {len(hechos)}" in prompt


def test_si_el_modelo_insiste_en_inventar_cifras_falla_sin_rellenar(df, caso):
    periodo, area_id, hechos = caso
    mala = con_cambio(hechos, texto="La rotación subió 99.9 % este mes.")
    with pytest.raises(NarrativaNoGenerada) as exc:
        generar_narrativa(periodo, area_id, proveedor=ProveedorFalso(*[mala] * INTENTOS), df=df)
    assert exc.value.reintentable is True
    assert len(exc.value.detalle) == INTENTOS
    assert "99.9" in exc.value.detalle[0]


def test_si_el_modelo_no_devuelve_json_falla(df, caso):
    periodo, area_id, _ = caso
    with pytest.raises(NarrativaNoGenerada) as exc:
        generar_narrativa(periodo, area_id, proveedor=ProveedorFalso(*["no soy json"] * INTENTOS), df=df)
    assert any("JSON" in d for d in exc.value.detalle)


def test_si_el_modelo_no_esta_disponible_falla_sin_reintentar(df, caso):
    periodo, area_id, _ = caso
    prov = ProveedorFalso(ProveedorNoDisponible("Ollama apagado"))
    with pytest.raises(NarrativaNoGenerada, match="Ollama apagado") as exc:
        generar_narrativa(periodo, area_id, proveedor=prov, df=df)
    assert exc.value.reintentable is False
    assert len(prov.llamadas) == 1  # no reintenta si el modelo ni siquiera responde


def test_el_esquema_restringe_el_campo_hechos_a_los_ids_entregados(df, caso):
    """Con salida estructurada, el modelo no puede poner frases ni 'H01 y H02' en `hechos`."""
    periodo, area_id, hechos = caso
    prov = ProveedorFalso(respuesta_buena(hechos))
    generar_narrativa(periodo, area_id, proveedor=prov, df=df)
    esquema = prov.esquemas[0]
    ids = {h["id"] for h in hechos_para_modelo(hechos)}
    for lista in ("hallazgos", "recomendaciones"):
        campo = esquema["properties"][lista]["items"]["properties"]["hechos"]
        assert set(campo["items"]["enum"]) == ids
        assert campo["minItems"] == 1
    # el esquema base no se modifica
    assert "enum" not in ESQUEMA_NARRATIVA["properties"]["hallazgos"]["items"]["properties"]["hechos"]["items"]
    assert esquema_narrativa(["H01"])["properties"]["hallazgos"]["items"]["properties"]["hechos"]["items"]["enum"] == ["H01"]


# ------------------------------------------------------- "por vigilar" (v4)
def test_motivo_de_vigilancia_por_cercania_al_umbral():
    # menor_es_peor, umbral_atencion=68: 68.9 esta a 1.3% de distancia (< 10%)
    m = motivo_de_vigilancia("indice_productividad", "verde", "menor_es_peor", 68.9, 68.0, -1.0, "empeoró", "alta")
    assert m is not None and "cerca del umbral" in m


def test_motivo_de_vigilancia_por_deterioro_relevante():
    # mayor_es_peor, lejos del umbral pero cayo mas del 10% frente al mes anterior
    m = motivo_de_vigilancia("rotacion_total", "verde", "mayor_es_peor", 1.0, 3.5, 0.2, "empeoró", "alta")
    assert m is not None and "deterioro" in m


def test_motivo_de_vigilancia_ninguno_si_no_aplica():
    base = dict(indicador="enps", estado="verde", sentido="menor_es_peor",
                valor=90.0, atencion=10.0, var_mes=5.0, evolucion="empeoró", confianza="alta")
    assert motivo_de_vigilancia(**base) is None  # lejos del umbral y cambio pequeño
    assert motivo_de_vigilancia(**{**base, "evolucion": "mejoró"}) is None  # no empeoro
    assert motivo_de_vigilancia(**{**base, "valor": 10.5, "confianza": "baja"}) is None  # confianza baja
    assert motivo_de_vigilancia(**{**base, "estado": "rojo", "valor": -5}) is None  # ya es alerta, no "por vigilar"


def test_construir_hechos_marca_en_vigilancia_con_motivo(df, id_area):
    """Operaciones feb-2026: eNPS en rojo, y otros 3 indicadores verdes con deterioro real."""
    hechos = construir_hechos(df, pd.Timestamp("2026-02-01"), id_area("Operaciones"))
    por_id = {h["id"]: h for h in hechos}
    vigilancia = [h for h in hechos if h["en_vigilancia"]]
    assert vigilancia, "se esperaba al menos un indicador por vigilar en este mes"
    for h in vigilancia:
        assert h["estado"] == "verde"
        assert h["motivo_vigilancia"]
        assert "conviene vigilarlo" in h["situacion"]
        assert h["accion_base"] is not None  # por vigilar SI tiene accion sugerida, a diferencia de un verde normal
    normales = [h for h in hechos if h["estado"] == "verde" and not h["en_vigilancia"]]
    assert any(h["accion_base"] is None for h in normales) or not normales


def test_hechos_para_modelo_incluye_alertas_y_vigilancia(df, id_area):
    hechos = construir_hechos(df, pd.Timestamp("2026-02-01"), id_area("Operaciones"))
    visibles = hechos_para_modelo(hechos)
    assert all(h["estado"] != "verde" or h["en_vigilancia"] for h in visibles)
    assert any(h["estado"] == "rojo" for h in visibles)
    assert any(h["en_vigilancia"] for h in visibles)
    # ningun verde "normal" (sin vigilancia) se cuela
    ocultos = [h for h in hechos if h["id"] not in {v["id"] for v in visibles}]
    assert all(h["estado"] == "verde" and not h["en_vigilancia"] for h in ocultos)


def test_conteo_estados_incluye_por_vigilar(df, id_area):
    hechos = construir_hechos(df, pd.Timestamp("2026-02-01"), id_area("Operaciones"))
    c = conteo_estados(hechos)
    assert c["por_vigilar"] == sum(h["en_vigilancia"] for h in hechos)
    assert c["por_vigilar"] > 0


def test_el_prompt_distingue_por_vigilar_de_una_alerta(df, id_area):
    periodo, aid = pd.Timestamp("2026-02-01"), id_area("Operaciones")
    hechos = construir_hechos(df, periodo, aid)
    prompt = "\n".join(m["content"] for m in construir_mensajes(hechos, periodo, "Operaciones"))
    assert "conviene vigilarlo" in prompt
    assert "por vigilar" in prompt.lower()


def test_guardrails_exige_cubrir_tambien_los_por_vigilar(df, id_area):
    periodo, aid = pd.Timestamp("2026-02-01"), id_area("Operaciones")
    hechos = construir_hechos(df, periodo, aid)
    visibles = hechos_para_modelo(hechos)
    vigilado = next(h for h in visibles if h["en_vigilancia"])
    r = buenos(hechos) if False else json.loads(respuesta_buena(hechos))
    for hl in r["hallazgos"]:
        hl["hechos"] = [x for x in hl["hechos"] if x != vigilado["id"]] or [visibles[0]["id"]]
    errores = validar_narrativa(r, visibles, cifras_de(*conteo_estados(hechos).values()))
    assert any(vigilado["id"] in e and "vigilar" in e for e in errores)


def test_schemas_exponen_los_campos_de_vigilancia():
    from app.schemas import ConteoEstados, HechoOut
    assert "en_vigilancia" in HechoOut.model_fields
    assert "motivo_vigilancia" in HechoOut.model_fields
    assert "por_vigilar" in ConteoEstados.model_fields


def test_api_narrativa_expone_por_vigilar(client, id_area):
    hechos = construir_hechos(kpis_df(), pd.Timestamp("2026-02-01"), id_area("Operaciones"))
    app.dependency_overrides[proveedor_configurado] = lambda: ProveedorFalso(respuesta_buena(hechos))
    r = client.post("/narrativas", json={"periodo": "2026-02", "area_id": id_area("Operaciones")})
    assert r.status_code == 202
    cuerpo = r.json()["narrativa"]
    assert cuerpo["conteo_estados"]["por_vigilar"] > 0
    assert any(h["en_vigilancia"] for h in cuerpo["hechos"])


def test_periodo_o_area_inexistentes(df):
    with pytest.raises(ValueError):
        generar_narrativa("2030-01-01", 0, proveedor=ProveedorFalso(), df=df)
    with pytest.raises(ValueError):
        generar_narrativa(None, 99, proveedor=ProveedorFalso(), df=df)


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
    assert recibido["cuerpo"]["think"] is False  # por defecto no pensamos (ver mas abajo)
    # "/no_think" es una convencion de Qwen: a un Llama no se le agrega, porque
    # no la entiende y podria tratarla como texto a responder (visto en una
    # evaluacion real: mas fallos y mas lento con Llama al agregarsela)
    assert recibido["cuerpo"]["messages"][-1]["content"] == "hola"
    assert mensajes[-1]["content"] == "hola"  # la lista original del llamador no se modifica


def test_cliente_ollama_desactiva_pensar_por_defecto_y_solo_toca_el_ultimo_mensaje(servidor_ollama):
    """Qwen3 y otros modelos razonadores piensan antes de responder por defecto,
    lo que puede sumar minutos sin ayudar en esta tarea. Debe desactivarse solo,
    sin necesidad de configurar nada, y sin ensuciar los mensajes anteriores
    (importante en el ciclo de reintento, que reenvia toda la conversacion)."""
    url = f"http://127.0.0.1:{servidor_ollama.server_port}"
    prov = OllamaProveedor(modelo="qwen3:8b", url=url, timeout=5)
    mensajes = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hechos"},
        {"role": "assistant", "content": "respuesta mala"},
        {"role": "user", "content": "corrige esto"},
    ]
    prov.generar(mensajes, ESQUEMA_NARRATIVA)
    enviados = servidor_ollama.ultima["cuerpo"]["messages"]
    assert servidor_ollama.ultima["cuerpo"]["think"] is False
    assert [m["content"] for m in enviados[:-1]] == ["sys", "hechos", "respuesta mala"]
    assert enviados[-1]["content"] == "corrige esto\n/no_think"


def test_cliente_ollama_permite_activar_pensar_explicitamente(servidor_ollama):
    url = f"http://127.0.0.1:{servidor_ollama.server_port}"
    prov = OllamaProveedor(modelo="qwen3:8b", url=url, timeout=5, pensar=True)
    prov.generar([{"role": "user", "content": "hola"}], ESQUEMA_NARRATIVA)
    cuerpo = servidor_ollama.ultima["cuerpo"]
    assert cuerpo["think"] is True
    assert cuerpo["messages"][-1]["content"] == "hola"  # no se le agrega /no_think


def test_ollama_think_configurable_desde_el_entorno(monkeypatch):
    monkeypatch.delenv("OLLAMA_THINK", raising=False)
    assert OllamaProveedor(modelo="x").pensar is False  # por defecto, no piensa
    monkeypatch.setenv("OLLAMA_THINK", "true")
    assert OllamaProveedor(modelo="x").pensar is True


def test_no_think_solo_se_agrega_a_modelos_qwen(servidor_ollama):
    """El texto '/no_think' es una convencion de Qwen. A otras familias
    (Llama, Phi, Gemma...) no se les agrega: no la entienden y una evaluacion
    real mostro mas fallos y mas lentitud en Llama al agregarsela igual."""
    url = f"http://127.0.0.1:{servidor_ollama.server_port}"
    for modelo, espera_no_think in [
        ("qwen3:8b", True), ("qwen2.5:14b", True), ("QWEN3:14B", True),
        ("llama3.1:8b", False), ("phi4:14b", False), ("gemma3:12b", False),
    ]:
        prov = OllamaProveedor(modelo=modelo, url=url, timeout=5)
        prov.generar([{"role": "user", "content": "hola"}], ESQUEMA_NARRATIVA)
        contenido = servidor_ollama.ultima["cuerpo"]["messages"][-1]["content"]
        assert contenido.endswith("/no_think") == espera_no_think, modelo
        assert servidor_ollama.ultima["cuerpo"]["think"] is False  # esto si se manda siempre


def test_cliente_ollama_modelo_no_descargado_da_pista(servidor_ollama):
    servidor_ollama.respuesta = (404, {"error": "model 'x' not found"})
    prov = OllamaProveedor(modelo="x", url=f"http://127.0.0.1:{servidor_ollama.server_port}", timeout=5)
    with pytest.raises(ProveedorNoDisponible, match="ollama pull x"):
        prov.generar([{"role": "user", "content": "hola"}], ESQUEMA_NARRATIVA)


def test_cliente_ollama_apagado(monkeypatch):
    prov = OllamaProveedor(modelo="x", url="http://127.0.0.1:9", timeout=2)  # puerto sin servicio
    with pytest.raises(ProveedorNoDisponible, match="Ollama"):
        prov.generar([{"role": "user", "content": "hola"}], ESQUEMA_NARRATIVA)


def test_ollama_trae_contexto_y_timeout_para_cpu(monkeypatch):
    for var in ("OLLAMA_NUM_CTX", "OLLAMA_TIMEOUT"):
        monkeypatch.delenv(var, raising=False)
    prov = OllamaProveedor(modelo="x")
    assert prov.num_ctx >= 8192   # 4096 se rebasaba en los reintentos
    assert prov.timeout >= 900    # en CPU un reporte puede tardar minutos
    assert prov.local is True


def test_proveedor_configurable_desde_el_entorno(monkeypatch):
    monkeypatch.setenv("LLM_PROVEEDOR", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "phi3:mini")
    assert obtener_proveedor().modelo == "phi3:mini"


def test_ya_no_existe_la_opcion_sin_ia(monkeypatch):
    monkeypatch.setenv("LLM_PROVEEDOR", "ninguno")
    with pytest.raises(ConfiguracionIA, match="ollama, groq"):
        obtener_proveedor()


# ------------------------------------------------------------ cliente Groq
@pytest.fixture()
def datos_sinteticos(monkeypatch):
    monkeypatch.setenv("MODO_DATOS", "sinteticos")
    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")


def test_groq_se_niega_con_datos_reales(monkeypatch):
    """El candado: con datos reales (o sin declarar) nada sale a la nube."""
    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
    monkeypatch.delenv("MODO_DATOS", raising=False)  # por defecto: reales
    with pytest.raises(ConfiguracionIA, match="sinteticos"):
        GroqProveedor()
    monkeypatch.setenv("MODO_DATOS", "reales")
    monkeypatch.setenv("LLM_PROVEEDOR", "groq")
    with pytest.raises(ConfiguracionIA, match="sinteticos"):
        obtener_proveedor()


def test_modo_datos_invalido_no_se_acepta(monkeypatch):
    monkeypatch.setenv("MODO_DATOS", "prueba")
    with pytest.raises(ConfiguracionIA, match="MODO_DATOS"):
        GroqProveedor(api_key="x")


def test_groq_sin_api_key(monkeypatch, datos_sinteticos):
    monkeypatch.delenv("GROQ_API_KEY")
    with pytest.raises(ConfiguracionIA, match="GROQ_API_KEY"):
        GroqProveedor()


class _GroqSimulado(BaseHTTPRequestHandler):
    def do_POST(self):
        cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.peticiones.append({"cuerpo": cuerpo, "auth": self.headers.get("Authorization")})
        codigo, respuesta, encabezados = self.server.respuestas.pop(0)
        datos = json.dumps(respuesta).encode()
        self.send_response(codigo)
        for k, v in encabezados.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def log_message(self, *args):
        pass


@pytest.fixture()
def servidor_groq():
    servidor = HTTPServer(("127.0.0.1", 0), _GroqSimulado)
    servidor.peticiones, servidor.respuestas = [], []
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield servidor
    servidor.shutdown()


def _ok_groq(contenido='{"ok": true}'):
    return (200, {"choices": [{"message": {"role": "assistant", "content": contenido}}]}, {})


def test_cliente_groq_arma_la_peticion_y_lee_la_respuesta(servidor_groq, datos_sinteticos):
    servidor_groq.respuestas.append(_ok_groq())
    url = f"http://127.0.0.1:{servidor_groq.server_port}/v1/chat/completions"
    prov = GroqProveedor(modelo="openai/gpt-oss-120b", url=url, timeout=5)
    assert prov.local is False
    assert prov.generar([{"role": "user", "content": "hola"}], ESQUEMA_NARRATIVA) == '{"ok": true}'

    peticion = servidor_groq.peticiones[0]
    assert peticion["auth"] == "Bearer clave-de-prueba"
    formato = peticion["cuerpo"]["response_format"]
    assert formato["type"] == "json_schema" and formato["json_schema"]["strict"] is True
    assert formato["json_schema"]["schema"]["additionalProperties"] is False
    assert peticion["cuerpo"]["reasoning_effort"] == "low"  # razonar poco: ahorra tokens del limite gratuito


def test_esquema_estricto_cierra_todos_los_objetos():
    e = esquema_estricto(esquema_narrativa(["H01"]))
    hallazgo = e["properties"]["hallazgos"]["items"]
    assert e["additionalProperties"] is False and hallazgo["additionalProperties"] is False
    assert set(hallazgo["required"]) == set(hallazgo["properties"])
    assert "additionalProperties" not in ESQUEMA_NARRATIVA  # el original no se toca


def test_cliente_groq_espera_y_reintenta_si_llega_al_limite_por_minuto(servidor_groq, datos_sinteticos):
    servidor_groq.respuestas += [(429, {"error": "rate limit"}, {"retry-after": "7"}), _ok_groq()]
    esperas = []
    url = f"http://127.0.0.1:{servidor_groq.server_port}/v1/chat/completions"
    prov = GroqProveedor(url=url, timeout=5, dormir=esperas.append)
    assert prov.generar([{"role": "user", "content": "hola"}], ESQUEMA_NARRATIVA) == '{"ok": true}'
    assert esperas == [7.0]
    assert len(servidor_groq.peticiones) == 2


def test_cliente_groq_clave_invalida_da_pista(servidor_groq, datos_sinteticos):
    servidor_groq.respuestas.append((401, {"error": "invalid api key"}, {}))
    url = f"http://127.0.0.1:{servidor_groq.server_port}/v1/chat/completions"
    with pytest.raises(ProveedorNoDisponible, match="GROQ_API_KEY"):
        GroqProveedor(url=url, timeout=5).generar([{"role": "user", "content": "hola"}], ESQUEMA_NARRATIVA)


# ------------------------------------------------------------------- API
@pytest.fixture()
def client():
    """Cliente de la API. Borra al terminar las narrativas que la prueba creo."""
    trabajos.asegurar_tabla()
    with engine.connect() as conn:
        ultimo = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM narrativas")).scalar()
    yield TestClient(app)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM narrativas WHERE id > :u"), {"u": ultimo})


def test_api_narrativa_se_genera_en_segundo_plano(client, monkeypatch, id_area):
    """POST responde de inmediato (202, en_proceso); el resultado se consulta por id."""
    diferido = _Diferido()
    monkeypatch.setattr(trabajos, "ejecutor", diferido)
    hechos = construir_hechos(kpis_df(), pd.Timestamp("2026-02-01"), id_area("Operaciones"))
    app.dependency_overrides[proveedor_configurado] = lambda: ProveedorFalso(respuesta_buena(hechos))

    r = client.post("/narrativas", json={"periodo": "2026-02", "area_id": id_area("Operaciones")})
    assert r.status_code == 202
    trabajo = r.json()
    assert trabajo["estado"] == "en_proceso" and trabajo["narrativa"] is None
    assert client.get(f"/narrativas/{trabajo['id']}").json()["estado"] == "en_proceso"

    diferido.correr()  # el hilo de trabajo termina
    listo = client.get(f"/narrativas/{trabajo['id']}").json()
    assert listo["estado"] == "lista" and listo["terminada_en"]
    assert listo["proveedor"] == "falso" and listo["modelo"] == "modelo-falso"  # bitacora (RF-11)
    n = listo["narrativa"]
    assert n["periodo"] == "2026-02" and n["area"] == "Operaciones"
    assert n["requiere_revision"] is True and n["hallazgos"]


def test_api_narrativa_por_defecto_es_corporativo_del_ultimo_mes(client):
    hechos = construir_hechos(kpis_df(), kpis_df()["periodo"].max(), 0)
    app.dependency_overrides[proveedor_configurado] = lambda: ProveedorFalso(respuesta_buena(hechos))
    trabajo = client.post("/narrativas", json={}).json()
    assert trabajo["estado"] == "lista"
    assert trabajo["narrativa"]["periodo"] == "2026-08" and trabajo["narrativa"]["area"] == "Corporativo"


def test_api_si_el_modelo_no_lo_logra_queda_en_error_con_el_motivo(client):
    """Sin plantilla: el reporte no se rellena; queda en error y se pide de nuevo desde cero."""
    prov = ProveedorFalso(*["no soy json"] * (INTENTOS * trabajos.RONDAS))
    app.dependency_overrides[proveedor_configurado] = lambda: prov
    trabajo = client.post("/narrativas", json={}).json()
    assert trabajo["estado"] == "error" and trabajo["narrativa"] is None
    assert "no logró una narrativa válida" in trabajo["error"]
    assert trabajo["rondas"] == trabajos.RONDAS
    assert len(prov.llamadas) == INTENTOS * trabajos.RONDAS
    assert any("JSON" in d for d in trabajo["detalle_error"])


def test_api_si_el_modelo_no_esta_disponible_no_insiste(client):
    prov = ProveedorFalso(ProveedorNoDisponible("Ollama apagado"))
    app.dependency_overrides[proveedor_configurado] = lambda: prov
    trabajo = client.post("/narrativas", json={}).json()
    assert trabajo["estado"] == "error" and "Ollama apagado" in trabajo["error"]
    assert trabajo["rondas"] == 1 and len(prov.llamadas) == 1


def test_api_configuracion_insegura_responde_503(client, monkeypatch):
    app.dependency_overrides.pop(proveedor_configurado)
    monkeypatch.setenv("LLM_PROVEEDOR", "groq")
    monkeypatch.setenv("MODO_DATOS", "reales")
    r = client.post("/narrativas", json={})
    assert r.status_code == 503 and "sinteticos" in r.json()["detail"]


def test_api_historial_y_narrativa_inexistente(client, id_area):
    hechos = construir_hechos(kpis_df(), pd.Timestamp("2026-04-01"), id_area("Operaciones"))
    app.dependency_overrides[proveedor_configurado] = lambda: ProveedorFalso(respuesta_buena(hechos))
    creado = client.post("/narrativas", json={"periodo": "2026-04", "area_id": id_area("Operaciones")}).json()
    historial = client.get("/narrativas", params={"area_id": id_area("Operaciones"), "periodo": "2026-04"}).json()
    assert historial[0]["id"] == creado["id"]
    assert historial[0]["narrativa"] is None  # el historial no trae el cuerpo
    assert client.get("/narrativas/999999999").status_code == 404


def test_al_reiniciar_las_narrativas_en_proceso_quedan_en_error(client):
    with engine.begin() as conn:
        id_ = conn.execute(
            text("INSERT INTO narrativas (area_id, periodo) VALUES (0, '2026-08-01') RETURNING id")
        ).scalar_one()
    assert trabajos.marcar_interrumpidas() >= 1
    trabajo = client.get(f"/narrativas/{id_}").json()
    assert trabajo["estado"] == "error" and "reinició" in trabajo["error"]


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