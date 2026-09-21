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
import json
from datetime import datetime, timezone

import pandas as pd

from app.guardrails import cifras_de, cifras_permitidas, validar_narrativa
from app.kpis import CORPORATIVO, calcular_kpis

VERSION_PROMPT = "v1"

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

PROMPT_SISTEMA = """Eres un analista de Recursos Humanos que redacta, en español, el resumen ejecutivo mensual para la alta dirección.

REGLAS OBLIGATORIAS
1. Usa ÚNICAMENTE los HECHOS que se te entregan. No calcules, estimes ni inventes cifras.
2. Cuando menciones una cifra, cópiala exactamente como aparece en el hecho (valor, cambio, umbral, muestra). No redondees, no sumes, no restes, no calcules porcentajes.
3. Cada hallazgo y cada recomendación debe citar en el campo "hechos" los ids (por ejemplo "H01") de los hechos que la respaldan. Cita solo hechos que apoyen directamente lo que escribes.
4. No afirmes causas. Están prohibidas expresiones como "causó", "provocó", "debido a", "se debe a", "gracias a". Si dos indicadores se mueven en la misma dirección, di solo que "coinciden" o "se observan juntos": una coincidencia no demuestra causalidad.
5. Si un hecho tiene confianza "baja", trátalo con cautela y no lo conviertas en el hallazgo principal.
6. Escribe para un directivo no técnico: frases cortas, sin jerga estadística.
7. Las recomendaciones son sugerencias para valoración de RRHH, no decisiones. Nunca propongas despidos, ascensos, sanciones ni acciones sobre personas concretas.
8. Responde SOLO con un JSON válido con el formato indicado."""


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
    conteo["total"] = len(hechos)
    return conteo


def _alcance(area: str) -> str:
    return "el consolidado corporativo" if area == "Corporativo" else f"el área {area}"


# ----------------------------------------------------------------- prompt
def construir_mensajes(hechos: list[dict], periodo: pd.Timestamp, area: str) -> list[dict]:
    """Prompt para el modelo. Solo recibe textos ya formateados, no floats crudos."""
    para_modelo = [
        {
            "id": h["id"],
            "indicador": h["nombre"],
            "valor": h["valor_texto"],
            "cambio_vs_mes_anterior": h["var_mes_ant_texto"],
            "cambio_vs_mismo_mes_del_año_anterior": h["var_anio_ant_texto"],
            "estado": h["estado"],
            "muestra": h["n"],
            "umbral_de_atencion": h["umbral_atencion_texto"],
            "umbral_critico": h["umbral_critico_texto"],
            "lectura": h["sentido"],
            "confianza": h["confianza"],
        }
        for h in hechos
    ]
    c = conteo_estados(hechos)
    usuario = (
        f"Periodo: {nombre_mes(periodo)}\n"
        f"Alcance: {_alcance(area)}\n"
        f"Conteo de estados: {c['rojo']} en rojo, {c['amarillo']} en amarillo, "
        f"{c['verde']} en verde (total {c['total']}).\n\n"
        f"HECHOS:\n{json.dumps(para_modelo, ensure_ascii=False, indent=1)}\n\n"
        "Entrega un JSON con: \"resumen\" (2 o 3 oraciones), \"hallazgos\" (de 3 a 5, "
        "ordenados por importancia, cada uno con \"titulo\", \"texto\" y \"hechos\") y "
        "\"recomendaciones\" (de 1 a 3, cada una con \"accion\" y \"hechos\")."
    )
    return [
        {"role": "system", "content": PROMPT_SISTEMA},
        {"role": "user", "content": usuario},
    ]


# -------------------------------------------------------------- plantilla
def narrativa_plantilla(hechos: list[dict], periodo: pd.Timestamp, area: str) -> dict:
    """Narrativa determinista (sin IA). Respaldo cuando el modelo falla y
    linea base para comparar contra la version con IA."""
    mes, alcance, c = nombre_mes(periodo), _alcance(area), conteo_estados(hechos)
    resumen = (
        f"En {mes}, {alcance} tiene {c['rojo']} indicadores en rojo, "
        f"{c['amarillo']} en amarillo y {c['verde']} en verde, de {c['total']} "
        "con datos disponibles."
    )

    no_verdes = [h for h in hechos if h["estado"] != "verde"]
    principales = no_verdes[:5]
    verdes = [h for h in hechos if h["estado"] == "verde"]
    while len(principales) < min(3, len(hechos)) and verdes:
        principales.append(verdes.pop(0))

    hallazgos = []
    for h in principales:
        texto = f"{h['nombre']} fue {h['valor_texto']} en {mes}"
        if h["var_mes_ant_texto"]:
            texto += f" ({h['var_mes_ant_texto']} frente al mes anterior)"
        if h["estado"] != "verde":
            texto += f"; se ubica en {h['estado']} según los umbrales definidos por RRHH"
        hallazgos.append(
            {"titulo": f"{h['nombre']}: {h['estado']}", "texto": texto + ".", "hechos": [h["id"]]}
        )

    candidatos = [h for h in no_verdes if h["confianza"] != "baja"] or no_verdes
    recomendaciones = [
        {"accion": RECOMENDACIONES[h["indicador"]], "hechos": [h["id"]]} for h in candidatos[:3]
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
    if proveedor is not None:
        mensajes = construir_mensajes(hechos, periodo, area)
        cifras_resumen = cifras_de(*conteo.values())
        for intento in (1, 2):
            try:
                crudo = proveedor.generar(mensajes, ESQUEMA_NARRATIVA)
            except Exception as exc:  # frontera externa: cualquier fallo -> plantilla
                advertencias.append(f"El modelo de lenguaje no estuvo disponible: {exc}")
                break
            try:
                salida = json.loads(crudo)
                errores = validar_narrativa(salida, hechos, cifras_resumen)
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
