"""Motor de narrativa ejecutiva (paso 5).

Flujo (secciones 10.3.5 y 10.5 del PRD):

    KPIs validados -> HECHOS (con id, confianza y fuente)
                   -> prompt -> modelo de lenguaje -> JSON
                   -> GUARDARRAILES (cifras, trazabilidad, causalidad)
                   -> si no pasa: reintento con los errores
                   -> si sigue sin pasar: NarrativaNoGenerada (nunca se
                      rellena con texto que no haya redactado la IA)
                   -> narrativa lista para REVISION HUMANA

Los meses sin alertas ni indicadores por vigilar ("meses estables") tambien
los redacta el modelo, a partir de todos los indicadores del mes.

Lo que el modelo NUNCA recibe: valores suprimidos por la regla de tamano
minimo de grupo (10.3.4), ni nombres ni datos personales. Con un proveedor
en la nube tampoco recibe el nombre del area (seudonimo).
El "nivel de confianza" lo calcula el codigo con reglas, no el modelo.
"""
import copy
import json
import os
from datetime import datetime, timezone

import pandas as pd

from app.guardrails import cifras_de, cifras_permitidas, validar_narrativa
from app.kpis import CORPORATIVO, INDICADORES_SOLO_VARIACION_ABSOLUTA, calcular_kpis

VERSION_PROMPT = "v5"
INTENTOS = int(os.getenv("LLM_INTENTOS", "3"))

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

# Accion base que se entrega al modelo por indicador en alerta o por vigilar.
# Sugerencias para valoracion de RRHH:
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

def rango_hallazgos(n_hechos: int) -> tuple[int, int]:
    """Cuantos hallazgos pedir: de 3 a 5, pero nunca mas que hechos citables.

    Pedir "de 3 a 5" con solo 2 hechos obligaba a un tercer hallazgo que
    repetia un hecho sin su valor, y los guardarrailes lo rechazaban siempre
    (Jurídico, agosto 2026: fallo los 3 intentos en la evaluacion real).
    """
    return min(3, n_hechos), min(5, n_hechos)


def esquema_narrativa(ids: list[str]) -> dict:
    """Esquema JSON donde `hechos` solo puede contener los ids entregados.

    Con salida estructurada, el modelo no puede escribir en ese campo nada que
    no sea un id valido (en la prueba real puso frases enteras y "H01 y H02").
    Tampoco puede escribir mas hallazgos que hechos tiene para citar.
    """
    esquema = copy.deepcopy(ESQUEMA_NARRATIVA)
    minimo, maximo = rango_hallazgos(len(ids))
    esquema["properties"]["hallazgos"].update(minItems=minimo, maxItems=maximo)
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


def texto_personas(indicador, valor, n) -> str | None:
    """Conteo en personas para las tasas de capacitacion: mas claro para un
    directivo que el porcentaje solo ("18 de 80 inscritos no completaron")."""
    si = round(float(valor) * int(n) / 100)
    if indicador == "tasa_finalizacion":
        return f"{si} de {int(n)} inscritos completaron el curso ({int(n) - si} no)"
    if indicador == "cobertura_capacitacion":
        return f"{si} de {int(n)} empleados activos se capacitaron ({int(n) - si} no)"
    return None


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
    """Hechos verificables de un area y mes.

    Excluye los valores suprimidos (grupo minimo) y los de muestra
    insuficiente: esos se ven en el dashboard, pero no son hechos que la IA
    deba evaluar (ver indicadores_sin_evaluar)."""
    filas = df[(df["periodo"] == periodo) & (df["area_id"] == area_id)]
    historia = (
        df[(df["area_id"] == area_id) & (df["periodo"] <= periodo) & df["valor"].notna()]
        .groupby("indicador")
        .size()
    )
    filas = filas[
        ~filas["suprimido"] & filas["valor"].notna() & (filas["estado"] != "muestra_insuficiente")
    ].copy()
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
                "personas_texto": texto_personas(f.indicador, f.valor, f.n),
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


def indicadores_sin_evaluar(df: pd.DataFrame, periodo: pd.Timestamp, area_id: int) -> list[str]:
    """Nombres de los indicadores con muestra insuficiente en ese area y mes."""
    filas = df[(df["periodo"] == periodo) & (df["area_id"] == area_id) & (df["estado"] == "muestra_insuficiente")]
    return sorted(filas["nombre"])


def conteo_estados(hechos: list[dict]) -> dict:
    conteo = {"rojo": 0, "amarillo": 0, "verde": 0}
    for h in hechos:
        conteo[h["estado"]] += 1
    conteo["por_vigilar"] = sum(h["en_vigilancia"] for h in hechos)
    conteo["total"] = len(hechos)
    return conteo


def _alcance(area: str, seudonimizar: bool = False) -> str:
    if area == "Corporativo":
        return "el consolidado corporativo"
    # A un proveedor en la nube no se le dice que area es: en areas pequenas,
    # area + mes + cifra podria bastar para adivinar de quien se habla.
    return "un área de la empresa" if seudonimizar else f"el área {area}"


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
    hallazgos en ellos. Excepcion: en un mes estable (sin alertas ni nada por
    vigilar) recibe todos, para redactar el resumen de estabilidad.
    """
    temas = [h for h in hechos if h["estado"] != "verde" or h["en_vigilancia"]]
    return temas or list(hechos)


def es_mes_estable(hechos: list[dict]) -> bool:
    return bool(hechos) and all(h["estado"] == "verde" and not h["en_vigilancia"] for h in hechos)


def detectar_coincidencias(hechos: list[dict]) -> list[tuple[dict, dict]]:
    en_alerta = {h["indicador"]: h for h in hechos if h["estado"] != "verde"}
    return [(en_alerta[a], en_alerta[b]) for a, b in VINCULOS if a in en_alerta and b in en_alerta]


def _cambio(texto, evolucion):
    return None if texto is None else f"{texto} ({evolucion})"


def construir_mensajes(
    hechos: list[dict], periodo: pd.Timestamp, area: str, seudonimizar: bool = False,
    sin_evaluar: list[str] = (),
) -> list[dict]:
    """Prompt para el modelo. Recibe todos los hechos y decide que se le muestra.

    seudonimizar=True (proveedores en la nube) oculta el nombre del area.
    sin_evaluar: nombres de indicadores con muestra insuficiente (sin cifras).
    """
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
            **({"personas": h["personas_texto"]} if h.get("personas_texto") else {}),
            "accion_base": h["accion_base"],
        }
        for h in visibles
    ]
    c = conteo_estados(hechos)
    estable = es_mes_estable(hechos)
    if estable:
        encabezado = "INDICADORES DEL MES (mes estable: ninguno en alerta ni por vigilar)"
    elif any(h["estado"] != "verde" for h in hechos):
        encabezado = "HECHOS EN ALERTA Y POR VIGILAR (ordenados por severidad)"
    else:
        encabezado = "HECHOS POR VIGILAR (ningún indicador está en alerta este mes)"
    partes = [
        f"Periodo: {nombre_mes(periodo)}",
        f"Alcance: {_alcance(area, seudonimizar)}",
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
    if sin_evaluar:
        partes.append(
            "\nIndicadores sin evaluar por muestra insuficiente (muy pocas personas; no son alertas "
            "ni hallazgos, menciónalos solo en el resumen y sin cifras): " + ", ".join(sin_evaluar) + "."
        )
    if estable:
        partes.append(
            "\nEste mes no hay alertas ni indicadores por vigilar. Redacta un resumen de estabilidad "
            f"que diga con números que hay 0 indicadores en rojo y 0 en amarillo de {c['total']}, "
            "y en los hallazgos describe los indicadores más relevantes con su valor (puedes agrupar los del mismo tipo; no "
            "hace falta mencionarlos todos). Como no hay \"accion_base\", la recomendación "
            "es mantener el seguimiento mensual de los indicadores citados."
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
    minimo, maximo = rango_hallazgos(len(visibles))
    cantidad = f"exactamente {minimo}" if minimo == maximo else f"de {minimo} a {maximo}"
    partes.append(
        f"\nEntrega un JSON con: \"resumen\", \"hallazgos\" ({cantidad}; cada uno con \"titulo\", "
        "\"texto\" y \"hechos\") y \"recomendaciones\" (de 1 a 3; cada una con \"accion\" y \"hechos\")."
    )
    return [
        {"role": "system", "content": PROMPT_SISTEMA},
        {"role": "user", "content": "\n".join(partes)},
    ]


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


class NarrativaNoGenerada(Exception):
    """El modelo no logro una narrativa valida. Nunca se sustituye por otro texto.

    reintentable=False si el modelo no estuvo disponible (repetir de inmediato
    no sirve); True si respondio pero no paso los guardarrailes.
    """

    def __init__(self, motivo: str, detalle: list[str], reintentable: bool):
        super().__init__(motivo)
        self.motivo = motivo
        self.detalle = detalle
        self.reintentable = reintentable


def mensajes_de_correccion(
    base: list[dict], crudo: str, errores: list[str], previos: list[str] = ()
) -> list[dict]:
    """Conversacion para el siguiente intento: el prompt original, SOLO la
    ultima respuesta y sus errores. Antes se acumulaban todos los intentos y
    al segundo reintento se rebasaba el contexto del modelo.

    `previos` son los errores de intentos anteriores (texto corto): se le
    recuerdan para que al corregir uno no vuelva a cometer el otro."""
    contenido = "Tu respuesta tuvo estos problemas:\n- " + "\n- ".join(errores)
    ya_vistos = [e for e in dict.fromkeys(previos) if e not in errores]
    if ya_vistos:
        contenido += "\nEn intentos anteriores también se te señaló (no lo repitas):\n- " + "\n- ".join(ya_vistos)
    return base + [
        {"role": "assistant", "content": crudo},
        {"role": "user", "content": contenido + "\nCorrígela y responde solo con el JSON."},
    ]


def validar_solicitud(df: pd.DataFrame, periodo=None, area_id=CORPORATIVO) -> tuple[pd.Timestamp, str]:
    """Periodo y nombre del area; ValueError si no existen o no hay indicadores."""
    periodo = pd.Timestamp(periodo) if periodo is not None else df["periodo"].max()
    if not (df["periodo"] == periodo).any():
        raise ValueError(f"No hay datos para el periodo {periodo:%Y-%m}")
    if area_id not in set(df["area_id"]):
        raise ValueError(f"El area {area_id} no existe")
    if not construir_hechos(df, periodo, area_id):
        raise ValueError("No hay indicadores con datos disponibles para este periodo y alcance")
    return periodo, df.loc[df["area_id"] == area_id, "area"].iloc[0]


def generar_narrativa(periodo=None, area_id=CORPORATIVO, proveedor=None, df=None) -> dict:
    """Genera con IA la narrativa ejecutiva de un area y mes.

    proveedor: objeto con .generar(mensajes, esquema) y .local (obligatorio).
    Lanza ValueError si el periodo o el area no existen o no hay indicadores,
    y NarrativaNoGenerada si el modelo no logra una respuesta valida.
    """
    if proveedor is None:
        raise ValueError("Se necesita un proveedor de IA: la narrativa siempre la redacta un modelo")
    df = df if df is not None else calcular_kpis()
    periodo, area = validar_solicitud(df, periodo, area_id)

    hechos = construir_hechos(df, periodo, area_id)
    conteo = conteo_estados(hechos)
    visibles = hechos_para_modelo(hechos)
    sin_evaluar = indicadores_sin_evaluar(df, periodo, area_id)
    base = construir_mensajes(
        hechos, periodo, area, seudonimizar=not getattr(proveedor, "local", True), sin_evaluar=sin_evaluar
    )
    cifras_resumen = cifras_de(*conteo.values())
    esquema = esquema_narrativa([h["id"] for h in visibles])

    mensajes, advertencias, aceptada, previos = base, [], None, []
    for intento in range(1, INTENTOS + 1):
        try:
            crudo = proveedor.generar(mensajes, esquema)
        except Exception as exc:  # frontera externa: cualquier fallo del proveedor
            raise NarrativaNoGenerada(
                f"El modelo de lenguaje no estuvo disponible: {exc}", advertencias, reintentable=False
            ) from exc
        try:
            salida = json.loads(crudo)
            errores = validar_narrativa(salida, visibles, cifras_resumen)
        except json.JSONDecodeError as exc:
            salida, errores = None, [f"La respuesta no es JSON válido ({exc.msg})"]
        if not errores:
            aceptada = salida
            break
        advertencias.append(
            f"Intento {intento}: la respuesta del modelo no pasó la validación: " + " | ".join(errores)
        )
        mensajes = mensajes_de_correccion(base, crudo, errores, previos)
        previos += errores

    if aceptada is None:
        raise NarrativaNoGenerada(
            f"El modelo no logró una narrativa válida en {INTENTOS} intentos", advertencias, reintentable=True
        )

    por_id = {h["id"]: h for h in hechos}
    return {
        "periodo": f"{periodo:%Y-%m}",
        "area_id": int(area_id),
        "area": area,
        "proveedor": getattr(proveedor, "nombre", type(proveedor).__name__),
        "modelo": getattr(proveedor, "modelo", None),
        "version_prompt": VERSION_PROMPT,
        "generado_en": datetime.now(timezone.utc),
        "requiere_revision": True,  # human-in-the-loop, regla 10.3.9
        "mes_estable": es_mes_estable(hechos),
        "indicadores_sin_evaluar": sin_evaluar,
        "intentos": len(advertencias) + 1,
        "resumen": aceptada["resumen"].strip(),
        "hallazgos": _enriquecer(aceptada["hallazgos"], por_id, ("titulo", "texto")),
        "recomendaciones": _enriquecer(aceptada["recomendaciones"], por_id, ("accion",)),
        "conteo_estados": conteo,
        "hechos": hechos,
        "advertencias": advertencias,
    }
