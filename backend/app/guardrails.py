"""Guardarrailes: validan lo que redacta el modelo de lenguaje (regla 10.3.5).

El modelo NO es de fiar por defecto. Este modulo comprueba, con codigo
determinista, que su respuesta cumple las reglas del PRD:

  1. No inventa cifras: todo numero que escribe debe estar en los hechos
     que cita (el motor de lenguaje "no calcula ni infiere cifras").
  2. Trazabilidad: cada hallazgo y recomendacion cita hechos que existen.
  3. No atribuye causalidad ("causo", "debido a"...).
  4. Estructura completa y cantidad de hallazgos (3 a 5, seccion 10.1).

Limite conocido: valida cifras, ids y lenguaje causal, pero no puede
comprobar que una frase sea semanticamente correcta. Por eso la revision
humana (10.3.6) sigue siendo obligatoria.
"""
import re

TOLERANCIA = 0.051  # las cifras se muestran con 1 decimal

_ID = re.compile(r"\bH\d{2}\b")
_PERIODO = re.compile(r"\b20\d{2}-\d{2}\b")
_ANIO = re.compile(r"\b20\d{2}\b")
_NUMERO = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?")
_MILES = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")

# Frases que afirman una causa. "causas" como sustantivo (p. ej. "investigar
# las causas") NO se marca: solo las formas que atribuyen causalidad.
_CAUSAL = re.compile(
    r"(?<!\w)("
    r"caus[óo]|causaron|causando|causad[oa]s?|"
    r"provoc\w+|ocasion\w+|"
    r"debido a|a causa de|por culpa de|se debe|se deben|se debi[óo]|se debieron|"
    r"gracias a|consecuencia de|producto de|resultado de|origin[óo]|originaron"
    r")(?!\w)",
    re.IGNORECASE,
)


def extraer_numeros(texto: str) -> list[float]:
    """Numeros de un texto, ignorando ids de hecho (H01), anios y periodos (2026-04)."""
    limpio = _ID.sub(" ", texto)
    limpio = _PERIODO.sub(" ", limpio)
    limpio = _ANIO.sub(" ", limpio)
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
    return cifras_de(
        hecho["valor_texto"],
        hecho["var_mes_ant_texto"],
        hecho["var_anio_ant_texto"],
        hecho["umbral_atencion_texto"],
        hecho["umbral_critico_texto"],
        hecho["n"],
    )


def _numeros_no_permitidos(texto: str, permitidas: set[float]) -> list[float]:
    return [
        x for x in extraer_numeros(texto)
        if not any(abs(abs(x) - p) <= TOLERANCIA for p in permitidas)
    ]


def _revisar_texto(etiqueta: str, texto: str, permitidas: set[float]) -> list[str]:
    errores = []
    extra = _numeros_no_permitidos(texto, permitidas)
    if extra:
        cifras = ", ".join(f"{x:g}" for x in extra)
        errores.append(f"{etiqueta}: contiene cifras que no estan en los hechos citados ({cifras})")
    causal = _CAUSAL.search(texto)
    if causal:
        errores.append(f"{etiqueta}: atribuye causalidad ('{causal.group(0)}')")
    return errores


def validar_narrativa(salida, hechos: list[dict], cifras_extra_resumen: set[float]) -> list[str]:
    """Devuelve la lista de problemas; vacia = la narrativa es valida."""
    if not isinstance(salida, dict):
        return ["La respuesta no es un objeto JSON"]

    por_id = {h["id"]: h for h in hechos}
    todas = set().union(*(cifras_permitidas(h) for h in hechos)) if hechos else set()
    errores = []

    resumen = salida.get("resumen")
    if not isinstance(resumen, str) or not resumen.strip():
        errores.append("Falta el resumen")
    else:
        errores += _revisar_texto("resumen", resumen, todas | cifras_extra_resumen)

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
        desconocidos = [x for x in ids if x not in por_id]
        if desconocidos:
            errores.append(f"{etiqueta}: cita hechos que no existen ({', '.join(map(str, desconocidos))})")
            continue
        permitidas = set().union(*(cifras_permitidas(por_id[x]) for x in ids))
        for campo in campos:
            valor = item.get(campo)
            if not isinstance(valor, str) or not valor.strip():
                errores.append(f"{etiqueta}: falta '{campo}'")
            else:
                errores += _revisar_texto(f"{etiqueta} ({campo})", valor, permitidas)
    return errores
