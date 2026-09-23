"""Motor de narrativa ejecutiva (paso 5).

Flujo (secciones 10.3.5 y 10.5 del PRD):

    KPIs validados -> HECHOS (con id, confianza y fuente)
                   -> prompt -> modelo de lenguaje -> JSON
                   -> GUARDARRAILES (cifras, trazabilidad, causalidad)
                   -> si no pasa: 1 reintento con los errores -> plantilla
                   -> narrativa lista para REVISION HUMANA

Lo que el modelo NUNCA recibe: valores suprimidos por la regla de tamano
minimo de grupo (10.3.4), ni nombres ni datos personales.
El "nivel de confianza" lo calcula el codigo con reglas, no el modelo.
"""
import copy
import json
import os
from datetime import datetime, timezone

import pandas as pd

from app.guardrails import cifras_de, cifras_permitidas, validar_narrativa
from app.kpis import CORPORATIVO, INDICADORES_SOLO_VARIACION_ABSOLUTA, calcular_kpis

VERSION_PROMPT = "v4"
INTENTOS = int(os.getenv("LLM_INTENTOS", "2"))

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

FUENTES = {
    "tiempo_contratacion": "ATS (vacantes)",
    "costo_por_contratacion": "ATS (vacantes)",
    "cumplimiento_metas": "Sistema de desempeño (metas_desempeno)",
    "cobertura_capacitacion": "LMS (inscripciones_capacitacion)",
    "tasa_finalizacion": "LMS (inscripciones_capacitacion)",
    "rotacion_total": "HRIS (empleados)",
    "rotacion_voluntaria": "HRIS (empleados)",
    "rotacion_involuntaria": "HRIS (empleados)",
    "enps": "Encuesta de clima (respuestas_clima)",
    "indice_productividad": "Sistema de proyectos (productividad)",
}

# Acciones de la plantilla determinista. Sugerencias para valoracion de RRHH:
# ninguna afirma una causa ni propone decisiones sobre personas.
RECOMENDACIONES = {
    "rotacion_total": "Revisar con la gerencia del área los patrones de las bajas del periodo, por ejemplo mediante entrevistas de salida.",
    "rotacion_voluntaria": "Explorar con el área las razones que las personas dan al renunciar y dar seguimiento mensual.",
    "rotacion_involuntaria": "Revisar con RRHH los criterios y el proceso que se siguieron en las bajas involuntarias.",
    "enps": "Programar sesiones de escucha con el equipo y dar seguimiento al eNPS el próximo mes.",
    "cumplimiento_metas": "Revisar con los líderes si las metas asignadas son alcanzables y si el equipo cuenta con los recursos necesarios.",
    "cobertura_capacitacion": "Reforzar la convocatoria a los programas de capacitación en el área.",
    "tasa_finalizacion": "Identificar en qué punto los colaboradores dejan los cursos y ajustar horarios o formato.",
    "tiempo_contratacion": "Revisar las etapas del proceso de selección para localizar demoras.",
    "costo_por_contratacion": "Revisar los canales de reclutamiento de mayor costo y su rendimiento.",
    "indice_productividad": "Analizar la planeación de entregables y la carga de trabajo del área.",
}

SEVERIDAD = {"rojo": 0, "amarillo": 1, "verde": 2}
ORDEN_CONFIANZA = ["baja", "media", "alta"]

ESQUEMA_NARRATIVA = {
    "type": "object",
    "properties": {
        "resumen": {"type": "string"},
        "hallazgos": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "texto": {"type": "string"},
                    "hechos": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["titulo", "texto", "hechos"],
            },
        },
        "recomendaciones": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "accion": {"type": "string"},
                    "hechos": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["accion", "hechos"],
            },
        },
    },
    "required": ["resumen", "hallazgos", "recomendaciones"],
}

def esquema_narrativa(ids: list[str]) -> dict:
    """Esquema JSON donde `hechos` solo puede contener los ids entregados.

    Con salida estructurada, el modelo no puede escribir en ese campo nada que
    no sea un id valido (en la prueba real puso frases enteras y "H01 y H02").
    """
    esquema = copy.deepcopy(ESQUEMA_NARRATIVA)
    for lista in ("hallazgos", "recomendaciones"):
        campo = esquema["properties"][lista]["items"]["properties"]["hechos"]
        campo["minItems"] = 1
        campo["items"] = {"type": "string", "enum": list(ids)}
    return esquema


PROMPT_SISTEMA = """Eres un analista de Recursos Humanos. Redactas, en español, el resumen ejecutivo mensual para la alta dirección.

REGLAS OBLIGATORIAS
1. Usa ÚNICAMENTE los HECHOS que se te entregan. No inventes ni calcules cifras: copia las cifras tal como aparecen en "valor" y "cambio".
2. Los hallazgos deben cubrir TODOS los hechos que se te entregan (alertas y "por vigilar"): un hallazgo por cada hecho en rojo, y el resto puede ir individual o agrupado (un hallazgo puede citar varios ids) si son del mismo tipo. Ningún hecho puede quedar sin mencionar. Si hay mas de 5 hechos, agrupa los que sobren en un ultimo hallazgo.
3. Cada hallazgo DEBE incluir el "valor" de CADA hecho que cita y, si existe, su cambio contra el mes anterior. Un hallazgo sin el valor no sirve.
4. Los hechos marcados "conviene vigilarlo" no son alertas: dilo con ese matiz (por ejemplo "sin alerta, pero conviene vigilar..."), nunca como si ya fueran una alerta.
5. Para hablar de umbrales usa solo la frase de "situacion" (por ejemplo "cruzó el umbral crítico"). No compares números con umbrales ni uses "supera" o "por debajo del umbral".
6. El campo "cambio" ya dice entre paréntesis si el indicador mejoró o empeoró. Úsalo; no lo deduzcas del signo del número.
7. En el campo "hechos" escribe SOLO ids de la lista (por ejemplo ["H01", "H02"]), nunca frases.
8. No afirmes causas: están prohibidos "causó", "provocó", "debido a", "se debe a", "gracias a". Si el sistema reporta una coincidencia, di solo que "coinciden" o "se observan juntos", nunca que uno explique al otro.
9. No menciones la confianza de los datos: el sistema la muestra por separado.
10. El resumen debe decir cuántos indicadores están en rojo y en amarillo, y nombrar los más graves con su valor.
11. Cada hecho en rojo debe tener al menos una recomendación. Cada recomendación parte de la "accion_base" del hecho que cita y habla solo de ese indicador. Son sugerencias para valoración de RRHH: nunca propongas despidos, sanciones ni acciones sobre personas concretas.
12. Sé breve. Resumen: máximo 3 oraciones. Cada hallazgo: máximo 2 oraciones. Cada recomendación: 1 oración.
13. Responde SOLO con el JSON."""


# ---------------------------------------------------------------- formato
def _num(x, decimales=1, con_signo=False):
    x = round(float(x), decimales)
    if x == 0:
        return f"{0:.{decimales}f}"  # evita "-0.0"
    return f"{x:+.{decimales}f}" if con_signo else f"{x:.{decimales}f}"


def texto_valor(valor, unidad):
    if unidad == "MXN":
        return f"{_num(valor, 0)} MXN"
    if unidad == "%":
        return f"{_num(valor)} %"
    if unidad == "días":
        return f"{_num(valor)} días"
    return f"{_num(valor)} puntos"


def texto_variacion(delta, unidad):
    if delta is None or pd.isna(delta):
        return None
    if unidad == "MXN":
        return f"{_num(delta, 0, True)} MXN"
    sufijo = {"%": "pts", "días": "días", "puntos": "puntos"}[unidad]
    return f"{_num(delta, 1, True)} {sufijo}"


def nombre_mes(periodo: pd.Timestamp) -> str:
    return f"{MESES_ES[periodo.month - 1]} de {periodo.year}"


# -------------------------------------------------------------- confianza
def _tope(nivel, maximo):
    return ORDEN_CONFIANZA[min(ORDEN_CONFIANZA.index(nivel), ORDEN_CONFIANZA.index(maximo))]


def confianza_de(n: int, meses_historia: int, hay_variacion_mensual: bool):
    """Nivel de confianza por REGLAS (no lo decide el modelo).

    Considera el tamano de la muestra, los meses de historia que respaldan
    la tendencia y si existe el dato del mes anterior para comparar.
    """
    nivel, motivos = "alta", []
    if n < 10:
        nivel = "baja"
        motivos.append(f"muestra muy pequeña (n={n})")
    elif n < 30:
        nivel = _tope(nivel, "media")
        motivos.append(f"muestra pequeña (n={n})")
    if meses_historia < 3:
        nivel = "baja"
        motivos.append("menos de 3 meses de historia")
    elif meses_historia < 6:
        nivel = _tope(nivel, "media")
        motivos.append("menos de 6 meses de historia")
    if not hay_variacion_mensual:
        nivel = _tope(nivel, "media")
        motivos.append("sin dato del mes anterior para comparar")
    return nivel, "; ".join(motivos) or "muestra e historia suficientes"


def _confianza_minima(hechos: list[dict]) -> str:
    return min((h["confianza"] for h in hechos), key=ORDEN_CONFIANZA.index)


# ----------------------------------------------------------------- hechos
SITUACION = {
    "rojo": "ya cruzó el umbral crítico",
    "amarillo": "cruzó el umbral de atención, pero todavía no el crítico",
    "verde": "sin alerta",
}


# Indicadores "por vigilar": en verde, pero con senales de deterioro. Es lo que
# un directivo querria saber antes de que se convierta en alerta.
UMBRAL_CERCANIA = 0.10        # a menos del 10 % del umbral de atencion
DETERIORO_RELEVANTE = 0.10    # empeoro 10 % o mas frente al mes anterior


def motivo_de_vigilancia(indicador, estado, sentido, valor, atencion, var_mes, evolucion, confianza):
    """Motivo por el que un indicador en verde conviene vigilarlo, o None.

    Requiere que haya empeorado frente al mes anterior y que su confianza no
    sea baja (con muestras diminutas el ruido dominaria la lista).
    """
    if estado != "verde" or confianza == "baja" or evolucion != "empeoró":
        return None
    motivos = []
    if atencion:
        margen = (valor - atencion) if sentido == "menor_es_peor" else (atencion - valor)
        if margen / abs(atencion) <= UMBRAL_CERCANIA:
            motivos.append("está cerca del umbral de atención")
    if indicador not in INDICADORES_SOLO_VARIACION_ABSOLUTA and var_mes is not None:
        previo = valor - var_mes
        if previo and abs(var_mes) / abs(previo) >= DETERIORO_RELEVANTE:
            motivos.append("su deterioro frente al mes anterior es relevante")
    return " y ".join(motivos) or None


def evolucion_de(delta, sentido) -> str | None:
    """'mejoró' / 'empeoró' / 'sin cambio', calculado por codigo segun el sentido del indicador.

    Asi el modelo no tiene que razonar si un valor mas alto es bueno o malo.
    """
    if delta is None or pd.isna(delta):
        return None
    if round(float(delta), 1) == 0:
        return "sin cambio"
    sube_es_mejor = sentido == "menor_es_peor"
    return "mejoró" if (delta > 0) == sube_es_mejor else "empeoró"


def construir_hechos(df: pd.DataFrame, periodo: pd.Timestamp, area_id: int) -> list[dict]:
    """Hechos verificables de un area y mes. Excluye los valores suprimidos."""
    filas = df[(df["periodo"] == periodo) & (df["area_id"] == area_id)]
    historia = (
        df[(df["area_id"] == area_id) & (df["periodo"] <= periodo) & df["valor"].notna()]
        .groupby("indicador")
        .size()
    )
    filas = filas[~filas["suprimido"] & filas["valor"].notna()].copy()
    filas["_sev"] = filas["estado"].map(SEVERIDAD)
    filas = filas.sort_values(["_sev", "indicador"])

    hechos = []
    for i, f in enumerate(filas.itertuples(), start=1):
        nivel, motivo = confianza_de(
            n=int(f.n),
            meses_historia=int(historia.get(f.indicador, 0)),
            hay_variacion_mensual=not pd.isna(f.var_mes_ant),
        )
        evol_mes = evolucion_de(f.var_mes_ant, f.sentido)
        motivo_vig = motivo_de_vigilancia(
            f.indicador, f.estado, f.sentido, float(f.valor), float(f.umbral_atencion),
            None if pd.isna(f.var_mes_ant) else float(f.var_mes_ant), evol_mes, nivel,
        )
        hechos.append(
            {
                "id": f"H{i:02d}",
                "indicador": f.indicador,
                "nombre": f.nombre,
                "unidad": f.unidad,
                "area": f.area,
                "periodo": f"{periodo:%Y-%m}",
                "valor": round(float(f.valor), 1),
                "valor_texto": texto_valor(f.valor, f.unidad),
                "var_mes_ant": None if pd.isna(f.var_mes_ant) else round(float(f.var_mes_ant), 1),
                "var_mes_ant_texto": texto_variacion(f.var_mes_ant, f.unidad),
                "var_anio_ant": None if pd.isna(f.var_anio_ant) else round(float(f.var_anio_ant), 1),
                "var_anio_ant_texto": texto_variacion(f.var_anio_ant, f.unidad),
                "estado": f.estado,
                "n": int(f.n),
                "umbral_atencion": float(f.umbral_atencion),
                "umbral_atencion_texto": texto_valor(f.umbral_atencion, f.unidad),
                "umbral_critico": float(f.umbral_critico),
                "umbral_critico_texto": texto_valor(f.umbral_critico, f.unidad),
                "sentido": "valores más altos son peores"
                if f.sentido == "mayor_es_peor"
                else "valores más bajos son peores",
                "evolucion_mes_ant": evol_mes,
                "evolucion_anio_ant": evolucion_de(f.var_anio_ant, f.sentido),
                "en_vigilancia": motivo_vig is not None,
                "motivo_vigilancia": motivo_vig,
                "situacion": f"sin alerta, pero conviene vigilarlo: {motivo_vig}" if motivo_vig else SITUACION[f.estado],
                "accion_base": RECOMENDACIONES.get(f.indicador) if (f.estado != "verde" or motivo_vig) else None,
                "confianza": nivel,
                "motivo_confianza": motivo,
                "fuente": FUENTES.get(f.indicador, "Motor analítico"),
            }
        )
    return hechos


def conteo_estados(hechos: list[dict]) -> dict:
    conteo = {"rojo": 0, "amarillo": 0, "verde": 0}
    for h in hechos:
        conteo[h["estado"]] += 1
    conteo["por_vigilar"] = sum(h["en_vigilancia"] for h in hechos)
    conteo["total"] = len(hechos)
    return conteo


def _alcance(area: str) -> str:
    return "el consolidado corporativo" if area == "Corporativo" else f"el área {area}"


# ----------------------------------------------------------------- prompt
# Pares de indicadores que suelen moverse juntos. El SISTEMA detecta cuando
# ambos estan en alerta y se lo senala al modelo como coincidencia (no causa).
VINCULOS = [
    ("enps", "rotacion_total"),
    ("enps", "cumplimiento_metas"),
    ("cumplimiento_metas", "indice_productividad"),
]


def hechos_para_modelo(hechos: list[dict]) -> list[dict]:
    """Hechos que ve (y puede citar) el modelo: alertas e indicadores por vigilar.

    Los demas indicadores en verde no se le entregan, para que no gaste
    hallazgos en ellos. Puede quedar vacia: sin alertas ni nada por vigilar no
    hay nada que redactar y no se consulta al modelo.
    """
    return [h for h in hechos if h["estado"] != "verde" or h["en_vigilancia"]]


def detectar_coincidencias(hechos: list[dict]) -> list[tuple[dict, dict]]:
    en_alerta = {h["indicador"]: h for h in hechos if h["estado"] != "verde"}
    return [(en_alerta[a], en_alerta[b]) for a, b in VINCULOS if a in en_alerta and b in en_alerta]


def _cambio(texto, evolucion):
    return None if texto is None else f"{texto} ({evolucion})"


def construir_mensajes(hechos: list[dict], periodo: pd.Timestamp, area: str) -> list[dict]:
    """Prompt para el modelo. Recibe todos los hechos y decide que se le muestra."""
    visibles = hechos_para_modelo(hechos)
    ids_visibles = {h["id"] for h in visibles}
    para_modelo = [
        {
            "id": h["id"],
            "indicador": h["nombre"],
            "valor": h["valor_texto"],
            "cambio_vs_mes_anterior": _cambio(h["var_mes_ant_texto"], h["evolucion_mes_ant"]),
            "cambio_vs_mismo_mes_del_año_anterior": _cambio(
                h["var_anio_ant_texto"], h["evolucion_anio_ant"]
            ),
            "estado": h["estado"],
            "situacion": h["situacion"],
            "muestra": h["n"],
            "accion_base": h["accion_base"],
        }
        for h in visibles
    ]
    c = conteo_estados(hechos)
    encabezado = (
        "HECHOS EN ALERTA Y POR VIGILAR (ordenados por severidad)"
        if any(h["estado"] != "verde" for h in hechos)
        else "HECHOS POR VIGILAR (ningún indicador está en alerta este mes)"
    )
    partes = [
        f"Periodo: {nombre_mes(periodo)}",
        f"Alcance: {_alcance(area)}",
        f"Conteo de estados: {c['rojo']} en rojo, {c['amarillo']} en amarillo, "
        f"{c['verde']} en verde, de los cuales {c['por_vigilar']} conviene vigilar (total {c['total']}).",
        f"\n{encabezado}:\n{json.dumps(para_modelo, ensure_ascii=False, indent=1)}",
    ]
    sin_alerta = [h["nombre"] for h in hechos if h["id"] not in ids_visibles]
    if sin_alerta:
        partes.append(
            "\nIndicadores sin alerta (menciónalos solo en el resumen, sin cifras): "
            + ", ".join(sin_alerta) + "."
        )
    coincidencias = detectar_coincidencias(hechos)
    if coincidencias:
        partes.append(
            "\nCoincidencias detectadas por el sistema (son coincidencias, no causas demostradas):"
        )
        partes += [
            f"- {a['id']} ({a['nombre']}) y {b['id']} ({b['nombre']}) están ambos en alerta."
            for a, b in coincidencias
        ]
    partes.append(
        "\nEntrega un JSON con: \"resumen\", \"hallazgos\" (de 3 a 5; cada uno con \"titulo\", "
        "\"texto\" y \"hechos\") y \"recomendaciones\" (de 1 a 3; cada una con \"accion\" y \"hechos\")."
    )
    return [
        {"role": "system", "content": PROMPT_SISTEMA},
        {"role": "user", "content": "\n".join(partes)},
    ]


# -------------------------------------------------------------- plantilla
def narrativa_plantilla(hechos: list[dict], periodo: pd.Timestamp, area: str) -> dict:
    """Narrativa determinista (sin IA). Respaldo cuando el modelo falla y
    linea base para comparar contra la version con IA."""
    mes, alcance, c = nombre_mes(periodo), _alcance(area), conteo_estados(hechos)
    resumen = (
        f"En {mes}, {alcance} tiene {c['rojo']} indicadores en rojo, "
        f"{c['amarillo']} en amarillo y {c['verde']} en verde, de {c['total']} "
        "con datos disponibles"
        + (f"; de los que están en verde, {c['por_vigilar']} conviene vigilar" if c["por_vigilar"] else "")
        + "."
    )

    temas = hechos_para_modelo(hechos)  # alertas y "por vigilar", en orden de severidad
    verdes = [h for h in hechos if h["estado"] == "verde" and not h["en_vigilancia"]]
    # hasta 5 hallazgos individuales; si hay mas temas, los que sobran se agrupan en uno
    individuales, agrupados = (temas, []) if len(temas) <= 5 else (temas[:4], temas[4:])

    def _texto(h):
        texto = f"{h['nombre']} fue {h['valor_texto']} en {mes}"
        if h["var_mes_ant_texto"]:
            texto += f" ({h['var_mes_ant_texto']} frente al mes anterior)"
        if h["en_vigilancia"]:
            texto += f"; sin alerta, pero conviene vigilar: {h['motivo_vigilancia']}."
        else:
            texto += f"; se ubica en {h['estado']} según los umbrales definidos por RRHH."
        return texto

    hallazgos = [
        {"titulo": f"{h['nombre']}: {'por vigilar' if h['en_vigilancia'] else h['estado']}",
         "texto": _texto(h), "hechos": [h["id"]]}
        for h in individuales
    ]
    if agrupados:
        detalle = "; ".join(f"{h['nombre']} {h['valor_texto']}" for h in agrupados)
        hallazgos.append(
            {
                "titulo": "Otros indicadores en alerta o por vigilar",
                "texto": f"También en {mes}: {detalle}.",
                "hechos": [h["id"] for h in agrupados],
            }
        )
    while len(hallazgos) < min(3, len(hechos)) and verdes:  # relleno si hay pocos temas
        h = verdes.pop(0)
        texto = f"{h['nombre']} fue {h['valor_texto']} en {mes}"
        if h["var_mes_ant_texto"]:
            texto += f" ({h['var_mes_ant_texto']} frente al mes anterior)"
        hallazgos.append({"titulo": f"{h['nombre']}: {h['estado']}", "texto": texto + ".", "hechos": [h["id"]]})

    # todas las alertas en rojo reciben recomendacion (maximo 3); se etiquetan con su confianza
    recomendaciones = [
        {"accion": RECOMENDACIONES[h["indicador"]], "hechos": [h["id"]]}
        for h in temas[:3]
    ]
    if not recomendaciones and hechos:
        recomendaciones = [
            {
                "accion": "Mantener el seguimiento mensual de los indicadores; no hay alertas en este periodo.",
                "hechos": [hechos[0]["id"]],
            }
        ]
    return {"resumen": resumen, "hallazgos": hallazgos, "recomendaciones": recomendaciones}


# ---------------------------------------------------------- orquestacion
def _enriquecer(items: list[dict], por_id: dict, campos: tuple) -> list[dict]:
    """Deja solo los campos esperados y agrega confianza y fuentes calculadas por codigo."""
    resultado = []
    for item in items:
        ids = list(dict.fromkeys(item["hechos"]))
        citados = [por_id[i] for i in ids]
        resultado.append(
            {
                **{c: item[c].strip() for c in campos},
                "hechos": ids,
                "confianza": _confianza_minima(citados),
                "fuentes": sorted({h["fuente"] for h in citados}),
            }
        )
    return resultado


def generar_narrativa(periodo=None, area_id=CORPORATIVO, proveedor=None, df=None) -> dict:
    """Genera la narrativa ejecutiva de un area y mes.

    proveedor: objeto con .generar(mensajes, esquema); None = solo plantilla.
    Lanza ValueError si el periodo o el area no existen.
    """
    df = df if df is not None else calcular_kpis()
    periodo = pd.Timestamp(periodo) if periodo is not None else df["periodo"].max()
    if not (df["periodo"] == periodo).any():
        raise ValueError(f"No hay datos para el periodo {periodo:%Y-%m}")
    if area_id not in set(df["area_id"]):
        raise ValueError(f"El area {area_id} no existe")
    area = df.loc[df["area_id"] == area_id, "area"].iloc[0]

    hechos = construir_hechos(df, periodo, area_id)
    conteo = conteo_estados(hechos)
    advertencias, aceptada, origen = [], None, "plantilla"
    proveedor_usado, modelo = None, None

    if not hechos:
        advertencias.append("No hay indicadores con datos disponibles para este periodo y alcance.")
        proveedor = None
    elif not hechos_para_modelo(hechos):
        advertencias.append("No hay alertas ni indicadores por vigilar: se usó la plantilla sin consultar al modelo.")
        proveedor = None
    if proveedor is not None:
        mensajes = construir_mensajes(hechos, periodo, area)
        visibles = hechos_para_modelo(hechos)
        cifras_resumen = cifras_de(*conteo.values())
        esquema = esquema_narrativa([h["id"] for h in visibles])
        for intento in range(1, INTENTOS + 1):
            try:
                crudo = proveedor.generar(mensajes, esquema)
            except Exception as exc:  # frontera externa: cualquier fallo -> plantilla
                advertencias.append(f"El modelo de lenguaje no estuvo disponible: {exc}")
                break
            try:
                salida = json.loads(crudo)
                errores = validar_narrativa(salida, visibles, cifras_resumen)
            except json.JSONDecodeError as exc:
                salida, errores = None, [f"La respuesta no es JSON válido ({exc.msg})"]
            if not errores:
                aceptada = salida
                break
            advertencias.append(
                f"Intento {intento}: la respuesta del modelo no pasó la validación: "
                + " | ".join(errores)
            )
            mensajes = mensajes + [
                {"role": "assistant", "content": crudo},
                {
                    "role": "user",
                    "content": "Tu respuesta tuvo estos problemas:\n- "
                    + "\n- ".join(errores)
                    + "\nCorrígela y responde solo con el JSON.",
                },
            ]

    if aceptada is not None:
        origen = "llm"
        proveedor_usado = getattr(proveedor, "nombre", type(proveedor).__name__)
        modelo = getattr(proveedor, "modelo", None)
        cuerpo = aceptada
    else:
        if proveedor is not None:
            advertencias.append("Se usó la plantilla determinista como respaldo.")
        cuerpo = narrativa_plantilla(hechos, periodo, area) if hechos else {
            "resumen": "Sin datos disponibles.", "hallazgos": [], "recomendaciones": []
        }

    por_id = {h["id"]: h for h in hechos}
    return {
        "periodo": f"{periodo:%Y-%m}",
        "area_id": int(area_id),
        "area": area,
        "origen": origen,
        "proveedor": proveedor_usado,
        "modelo": modelo,
        "version_prompt": VERSION_PROMPT,
        "generado_en": datetime.now(timezone.utc),
        "requiere_revision": True,  # human-in-the-loop, regla 10.3.6
        "resumen": cuerpo["resumen"].strip(),
        "hallazgos": _enriquecer(cuerpo["hallazgos"], por_id, ("titulo", "texto")),
        "recomendaciones": _enriquecer(cuerpo["recomendaciones"], por_id, ("accion",)),
        "conteo_estados": conteo,
        "hechos": hechos,
        "advertencias": advertencias,
    }