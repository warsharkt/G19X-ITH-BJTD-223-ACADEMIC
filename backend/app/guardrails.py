"""Guardarrailes: validan lo que redacta el modelo de lenguaje (regla 10.3.5).

El modelo NO es de fiar por defecto. Este modulo comprueba, con codigo
determinista, que su respuesta cumple las reglas del PRD:

  1. No inventa cifras: todo numero debe estar en los hechos que cita.
  2. Trazabilidad: cita solo hechos que se le entregaron.
  3. No atribuye causalidad ("causo", "debido a"...).
  4. Estructura y cantidad de hallazgos (3 a 5, seccion 10.1).

Reglas anadidas tras probar con Llama 3.1 8B (prompt v1), que dejo pasar
errores de criterio que las reglas 1-4 no ven:

  5. Cubre TODOS los hechos en rojo (max. 5): no puede ignorar una alerta.
  6. No habla de "confianza": la calcula el codigo y se muestra aparte.
  7. No compara contra umbrales ("supera el umbral"): la direccion de la
     comparacion depende del indicador (en eNPS, menos es peor) y el modelo
     la invirtio. Debe usar la frase neutra que le da el sistema.
  8. Longitud maxima (resumen 3 oraciones, hallazgo 3, recomendacion 2).

Reglas anadidas tras la segunda prueba real (prompt v2): el modelo cumplia
las reglas escribiendo lo minimo, con textos correctos pero vacios:

  9. El resumen incluye alguna cifra, y cada hallazgo incluye cifras
     (ver regla 12).
 10. TODAS las alertas (rojo y amarillo) deben aparecer en algun hallazgo;
     puede agrupar varias en uno.
 11. Cada hecho en rojo (max. 3) debe tener al menos una recomendacion.

Reglas anadidas tras la tercera prueba real (prompt v3):

 12. Cada hallazgo incluye el VALOR de cada hecho que cita, no solo su cambio
     (los hallazgos de Ventas decian "empeoro 1.1 puntos" sin decir en cuanto quedo).

Huecos cerrados tras una revision del codigo (noviembre de 2026):

 13. Causalidad tambien con "por eso", "porque", "a raiz de", "derivado de".
 14. Un hallazgo no puede decir "mejoro" si el codigo calculo que empeoro
     (ni al reves): la direccion la decide el sistema, no el modelo.
 15. Solo se ignoran los anios del reporte (el del periodo y el anterior, para
     la comparacion anual): "2031 MXN" ya no pasa como si fuera un anio.
 16. Causalidad tambien con "atribuible a" y con las contracciones "al" y
     "del": "debido al aumento" o "a raiz del cambio" pasaban, porque la
     regla pedia que despues de "a" o "de" no siguiera ninguna letra.

Limite conocido: no puede comprobar que una frase sea semanticamente
correcta. Por eso la revision humana (10.3.9) sigue siendo obligatoria.
"""
import re

TOLERANCIA = 0.051  # las cifras se muestran con 1 decimal
MAX_ORACIONES = {"resumen": 3, "texto": 3, "accion": 2}

_ID = re.compile(r"\bH\d{2}\b")
# Anio suelto (2026) o periodo (2026-04); solo se ignoran los del reporte
_ANIO = re.compile(r"\b(20\d{2})(?:-\d{2})?\b")
_NUMERO = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?")
_MILES = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")
_ORACION = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\"“])")

# Frases que afirman una causa. "causas" como sustantivo (p. ej. "investigar
# las causas") NO se marca: solo las formas que atribuyen causalidad.
# "al?" y "del?" cubren las contracciones: "debido al aumento" tambien es una
# causa. "resultado de" se queda sin "del": "el resultado del eNPS" no lo es.
_CAUSAL = re.compile(
    r"(?<!\w)("
    r"caus[óo]|causaron|causando|causad[oa]s?|"
    r"provoc\w+|ocasion\w+|"
    r"debido al?|a causa del?|por culpa del?|se debe(?:n)?\s+al?|se debi[óo]\s+al?|se debieron\s+al?|"
    r"gracias al?|consecuencia del?|producto del?|resultado de|origin[óo]|originaron|"
    r"por eso|por ello|porque|a ra[íi]z del?|derivad[oa]s? del?|atribuibles? al?"
    r")(?!\w)",
    re.IGNORECASE,
)
# Palabras que afirman una evolucion. Se comparan con evolucion_mes_ant y
# evolucion_anio_ant, que calcula el codigo segun el sentido del indicador.
_EVOLUCION = {
    "mejoró": re.compile(r"(?<!\w)(mejor[óo]|mejoraron|mejorad[oa]s?|mejor[íi]a)(?!\w)", re.IGNORECASE),
    "empeoró": re.compile(
        r"(?<!\w)(empeor[óo]|empeoraron|empeorad[oa]s?|deterior[óo]|deterioraron|deteriorad[oa]s?|deterioro)(?!\w)",
        re.IGNORECASE,
    ),
}
_NEGACION = re.compile(r"(?<!\w)(no|ni|sin)\W*$", re.IGNORECASE)
_CONFIANZA = re.compile(r"(?<!\w)(confian\w*|confiabl\w*|fiabilidad)(?!\w)", re.IGNORECASE)
_COMPARA_UMBRAL = re.compile(
    r"(?<!\w)(supera\w*|excede\w*|rebasa\w*|sobrepasa\w*|por encima|por debajo|"
    r"inferior\w*|superior\w*|debajo)(?!\w)",
    re.IGNORECASE,
)


def extraer_numeros(texto: str, anios=frozenset()) -> list[float]:
    """Numeros de un texto, ignorando ids de hecho (H01) y los anios y periodos
    (2026, 2026-04) cuyo anio este en `anios`. Cualquier otro 20xx es una cifra."""
    limpio = _ID.sub(" ", texto)
    limpio = _ANIO.sub(lambda m: " " if int(m.group(1)) in anios else m.group(0), limpio)
    numeros = []
    for m in _NUMERO.findall(limpio):
        if _MILES.fullmatch(m):
            numeros.append(float(m.replace(",", "")))
        else:
            numeros.append(float(m.replace(",", ".")))
    return numeros


def cifras_de(*textos) -> set[float]:
    """Conjunto de cifras (en valor absoluto) que aparecen en los textos dados."""
    cifras = set()
    for t in textos:
        if t is None:
            continue
        cifras.update(abs(x) for x in extraer_numeros(str(t)))
    return cifras


def cifras_permitidas(hecho: dict) -> set[float]:
    """Cifras que el modelo puede citar de un hecho: valor, cambios, muestra y conteo de personas.

    Los umbrales NO se incluyen: el modelo no los recibe (ver regla 7).
    """
    return cifras_de(
        hecho["valor_texto"], hecho["var_mes_ant_texto"], hecho["var_anio_ant_texto"], hecho["n"],
        hecho.get("personas_texto"),
    )


def _usa_alguna(texto: str, cifras: set[float]) -> bool:
    return any(abs(abs(x) - c) <= TOLERANCIA for x in extraer_numeros(texto) for c in cifras)


_PORCENTAJE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|por\s*ciento)", re.IGNORECASE)


def incluye_valor(texto: str, hecho: dict) -> bool:
    """El texto menciona el VALOR del hecho, no solo su cambio.

    En indicadores en %, el valor se escribe con "%" y el cambio con "pts":
    se exige el "%" para que un cambio igual al valor no cuente como valor
    (visto en la evaluacion real: cobertura 25.0 % con cambio anual -25.0 pts).
    """
    objetivo = cifras_de(hecho["valor_texto"])
    if hecho.get("unidad") != "%":
        return _usa_alguna(texto, objetivo)
    con_signo = [float(m.replace(",", ".")) for m in _PORCENTAJE.findall(_ID.sub(" ", texto))]
    return any(abs(x - c) <= TOLERANCIA for x in con_signo for c in objetivo)


def anios_del_reporte(hechos: list[dict]) -> frozenset[int]:
    """Anios que el texto puede mencionar: el del periodo y el anterior."""
    anios = {int(h["periodo"][:4]) for h in hechos if h.get("periodo")}
    return frozenset(anios | {a - 1 for a in anios})


def _numeros_no_permitidos(texto: str, permitidas: set[float], anios) -> list[float]:
    return [
        x for x in extraer_numeros(texto, anios)
        if not any(abs(abs(x) - p) <= TOLERANCIA for p in permitidas)
    ]


def _oraciones(texto: str) -> list[str]:
    return [o for o in _ORACION.split(texto.strip()) if o.strip()]


def _contradice_evolucion(etiqueta: str, texto: str, citados: list[dict]) -> list[str]:
    """El texto dice "mejoro" (o "empeoro") y ningun hecho citado lo hizo."""
    errores = []
    for evolucion, patron in _EVOLUCION.items():
        palabras = [m.group(0) for m in patron.finditer(texto) if not _NEGACION.search(texto[: m.start()])]
        if not palabras or any(evolucion in (h.get("evolucion_mes_ant"), h.get("evolucion_anio_ant")) for h in citados):
            continue
        calculado = "; ".join(
            f"{h['nombre']} ({h['id']}): {h.get('evolucion_mes_ant') or 'sin dato'} frente al mes anterior"
            + (f", {h['evolucion_anio_ant']} frente al año anterior" if h.get("evolucion_anio_ant") else "")
            for h in citados
        )
        errores.append(
            f"{etiqueta}: dice '{palabras[0]}', pero el sistema calculó otra cosa ({calculado}); "
            "usa lo que dice entre paréntesis el campo 'cambio'"
        )
    return errores


def _revisar_texto(etiqueta: str, campo: str, texto: str, permitidas: set[float], anios=frozenset()) -> list[str]:
    errores = []
    extra = _numeros_no_permitidos(texto, permitidas, anios)
    if extra:
        cifras = ", ".join(f"{x:g}" for x in extra)
        errores.append(f"{etiqueta}: contiene cifras que no estan en los hechos citados ({cifras})")
    causal = _CAUSAL.search(texto)
    if causal:
        errores.append(f"{etiqueta}: atribuye causalidad ('{causal.group(0)}')")
    if _CONFIANZA.search(texto):
        errores.append(f"{etiqueta}: menciona la confianza; el sistema la muestra por separado, no la comentes")
    for oracion in _oraciones(texto):
        if "umbral" in oracion.lower() and _COMPARA_UMBRAL.search(oracion):
            errores.append(
                f"{etiqueta}: compara contra un umbral; usa solo la frase de 'situacion' "
                "(por ejemplo 'cruzó el umbral crítico')"
            )
            break
    maximo = MAX_ORACIONES.get(campo)
    if maximo and len(_oraciones(texto)) > maximo:
        pista = ""
        if campo == "texto":
            # visto con Qwen3: al corregir un valor faltante agrupaba mas hechos
            # en el mismo hallazgo y se pasaba de largo una y otra vez
            pista = "; acórtalo y, si cita varios hechos, repártelos en hallazgos separados (puede haber hasta 5)"
        errores.append(f"{etiqueta}: demasiado largo (maximo {maximo} oraciones){pista}")
    return errores


def validar_narrativa(salida, hechos: list[dict], cifras_extra_resumen: set[float]) -> list[str]:
    """Devuelve la lista de problemas; vacia = la narrativa es valida.

    `hechos` son los que se le entregaron al modelo: solo esos puede citar.
    """
    if not isinstance(salida, dict):
        return ["La respuesta no es un objeto JSON"]

    por_id = {h["id"]: h for h in hechos}
    todas = set().union(*(cifras_permitidas(h) for h in hechos)) if hechos else set()
    anios = anios_del_reporte(hechos)
    errores = []

    resumen = salida.get("resumen")
    if not isinstance(resumen, str) or not resumen.strip():
        errores.append("Falta el resumen")
    else:
        errores += _revisar_texto("resumen", "resumen", resumen, todas | cifras_extra_resumen, anios)
        if not extraer_numeros(resumen, anios):
            errores.append(
                "resumen: no incluye ninguna cifra; menciona cuantos indicadores estan en rojo "
                "y en amarillo, o el valor de los mas graves"
            )

    hallazgos = salida.get("hallazgos")
    if not isinstance(hallazgos, list):
        errores.append("Faltan los hallazgos")
        hallazgos = []
    minimo = min(3, len(hechos))
    if not (minimo <= len(hallazgos) <= 5):
        errores.append(f"Debe haber entre {minimo} y 5 hallazgos (hay {len(hallazgos)})")

    recomendaciones = salida.get("recomendaciones")
    if not isinstance(recomendaciones, list):
        errores.append("Faltan las recomendaciones")
        recomendaciones = []
    if len(recomendaciones) > 3:
        errores.append(f"Debe haber como maximo 3 recomendaciones (hay {len(recomendaciones)})")

    citados_en_hallazgos, citados_en_recomendaciones = set(), set()
    items = [("hallazgo", i, h, ("titulo", "texto")) for i, h in enumerate(hallazgos, 1)]
    items += [("recomendacion", i, r, ("accion",)) for i, r in enumerate(recomendaciones, 1)]
    for tipo, i, item, campos in items:
        etiqueta = f"{tipo} {i}"
        if not isinstance(item, dict):
            errores.append(f"{etiqueta}: formato invalido")
            continue
        ids = item.get("hechos")
        if not isinstance(ids, list) or not ids:
            errores.append(f"{etiqueta}: no cita ningun hecho")
            continue
        ajenos = [x for x in ids if x not in por_id]
        if ajenos:
            errores.append(
                f"{etiqueta}: cita hechos que no se te entregaron ({', '.join(map(str, ajenos))}); "
                "usa solo los ids de la lista de hechos"
            )
            continue
        (citados_en_hallazgos if tipo == "hallazgo" else citados_en_recomendaciones).update(ids)
        permitidas = set().union(*(cifras_permitidas(por_id[x]) for x in ids))
        for campo in campos:
            valor = item.get(campo)
            if not isinstance(valor, str) or not valor.strip():
                errores.append(f"{etiqueta}: falta '{campo}'")
            else:
                errores += _revisar_texto(f"{etiqueta} ({campo})", campo, valor, permitidas, anios)
                if tipo == "hallazgo":
                    errores += _contradice_evolucion(f"{etiqueta} ({campo})", valor, [por_id[x] for x in ids])
                if tipo == "hallazgo" and campo == "texto":
                    for x in ids:
                        if not incluye_valor(valor, por_id[x]):
                            # el valor exacto en el mensaje: con solo "copia su campo
                            # 'valor'" Qwen3 repitio el mismo error 3 veces seguidas
                            v = por_id[x]["valor_texto"]
                            errores.append(
                                f"{etiqueta} (texto): no incluye el valor de {por_id[x]['nombre']} ({x}), "
                                f"que es {v}; escríbelo tal cual, por ejemplo: '... quedó en {v}'"
                            )

    # Reglas 5 y 10: ningun hecho entregado (alerta o "por vigilar") puede quedar sin mencionar
    for h in hechos:
        if (h["estado"] != "verde" or h.get("en_vigilancia")) and h["id"] not in citados_en_hallazgos:
            etiqueta_estado = "por vigilar" if h["estado"] == "verde" else h["estado"]
            errores.append(
                f"Ningun hallazgo cubre el hecho {h['id']}, que esta {etiqueta_estado} "
                "(puedes agrupar varios hechos en un mismo hallazgo)"
            )
    # Regla 11: cada rojo tiene al menos una recomendacion
    for h in [x for x in hechos if x["estado"] == "rojo"][:3]:
        if h["id"] not in citados_en_recomendaciones:
            errores.append(f"Ninguna recomendacion cubre el hecho {h['id']}, que esta en rojo")
    return errores