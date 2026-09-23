"""Evalua el modelo de lenguaje en varias combinaciones de area y mes.

Corre generar_narrativa() con IA real en una muestra de casos y mide, para
cada uno: si el modelo acerto a la primera, cuantos intentos necesito, si
termino en la plantilla, cuanto tardo, y una senal (heuristica, no un
guardarrail) de posibles generalizaciones de direccion incorrectas al
agrupar hechos con "mejoro"/"empeoro" distintos (el error real que
encontramos en Operaciones-febrero).

Cada llamada al modelo tarda 30-90 segundos en CPU: la muestra por defecto
(10 casos) puede tardar 10-20 minutos. Se guarda un CSV para el informe de
QA aunque el script se interrumpa a la mitad (se escribe fila por fila).

Uso (desde la carpeta backend, con el entorno virtual activo y Ollama abierto):
    python -m scripts.evaluar_narrativa                       # muestra curada de 10 casos
    python -m scripts.evaluar_narrativa --aleatorio 15         # 15 casos al azar (semilla fija)
    python -m scripts.evaluar_narrativa --casos "Operaciones:2026-04,Ventas:2026-06"
    python -m scripts.evaluar_narrativa --salida reportes/mi_evaluacion.csv
"""
import argparse
import csv
import random
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.kpis import calcular_kpis
from app.llm import obtener_proveedor
from app.narrativa import generar_narrativa

RAIZ_REPORTES = Path(__file__).resolve().parents[1] / "reportes"

# Cubre los escenarios que ya vimos a mano: crisis (rojo+amarillo), solo
# amarillo, solo "por vigilar" (sin ninguna alerta), y un area pequena con
# indicadores suprimidos.
MUESTRA_CURADA = [
    ("Corporativo", "2026-08"), ("Corporativo", "2026-03"),
    ("Operaciones", "2026-04"), ("Operaciones", "2026-02"), ("Operaciones", "2026-07"),
    ("Ventas", "2026-06"), ("TI", "2026-05"), ("Finanzas", "2026-01"),
    ("Marketing", "2026-06"), ("Legal", "2026-08"),
]

_MEJORO = re.compile(r"mejor[oó]|mejorad[oa]s?|mejorando", re.IGNORECASE)
_EMPEORO = re.compile(r"empeor[oó]|empeorad[oa]s?|empeorando", re.IGNORECASE)


def elegir_casos(df: pd.DataFrame, args) -> list[tuple[str, str]]:
    periodos = sorted(p.strftime("%Y-%m") for p in df["periodo"].unique())
    areas = set(df["area"])
    if args.casos:
        casos = []
        for par in args.casos.split(","):
            area, periodo = par.split(":")
            area, periodo = area.strip(), periodo.strip()
            if area not in areas:
                raise SystemExit(f"Area '{area}' no existe. Opciones: {', '.join(sorted(areas))}")
            if periodo not in periodos:
                raise SystemExit(f"Periodo '{periodo}' no existe. Opciones: {periodos[0]} a {periodos[-1]}")
            casos.append((area, periodo))
        return casos
    if args.aleatorio:
        random.seed(42)
        return [(random.choice(sorted(areas)), random.choice(periodos)) for _ in range(args.aleatorio)]
    return MUESTRA_CURADA


def posibles_inconsistencias(narrativa: dict) -> list[str]:
    """Senal heuristica (NO un guardarrail): un hallazgo que agrupa hechos con
    'mejoro' y 'empeoro' reales distintos, pero solo usa una de las dos
    palabras en el texto, puede estar generalizando mal a todos por igual
    (el error real que encontramos en Operaciones-febrero: dos hechos con
    direcciones opuestas descritos con un solo verbo compartido)."""
    por_id = {h["id"]: h for h in narrativa["hechos"]}
    avisos = []
    for h in narrativa["hallazgos"]:
        citados = [por_id[i] for i in h["hechos"] if i in por_id]
        direcciones = {
            e for f in citados for e in (f["evolucion_mes_ant"], f["evolucion_anio_ant"]) if e
        }
        if len(citados) < 2 or "mejoró" not in direcciones or "empeoró" not in direcciones:
            continue  # no hay mezcla real de direcciones que generalizar mal
        usa_mejoro, usa_empeoro = _MEJORO.search(h["texto"]), _EMPEORO.search(h["texto"])
        if (usa_mejoro and not usa_empeoro) or (usa_empeoro and not usa_mejoro):
            avisos.append(f"{h['titulo']!r} mezcla hechos que mejoraron y empeoraron, pero el texto solo usa un verbo")
    return avisos


def evaluar_uno(area_id: int, area: str, periodo: str, proveedor, df) -> dict:
    inicio = time.perf_counter()
    n = generar_narrativa(pd.Timestamp(periodo + "-01"), area_id, proveedor=proveedor, df=df)
    segundos = round(time.perf_counter() - inicio, 1)

    intentos_fallidos = sum(1 for a in n["advertencias"] if a.startswith("Intento"))
    cayo_a_plantilla = n["origen"] == "plantilla"
    inconsistencias = posibles_inconsistencias(n) if not cayo_a_plantilla else []
    return {
        "area": area,
        "periodo": periodo,
        "rojo": n["conteo_estados"]["rojo"],
        "amarillo": n["conteo_estados"]["amarillo"],
        "por_vigilar": n["conteo_estados"]["por_vigilar"],
        "origen": n["origen"],
        "acerto_a_la_primera": (not cayo_a_plantilla) and intentos_fallidos == 0,
        "intentos_fallidos_antes_de_aceptar": 0 if cayo_a_plantilla else intentos_fallidos,
        "cayo_a_plantilla": cayo_a_plantilla,
        "motivo_plantilla": " | ".join(n["advertencias"]) if cayo_a_plantilla else "",
        "posibles_inconsistencias": " | ".join(inconsistencias),
        "segundos": segundos,
    }


def imprimir_resumen(filas: list[dict]):
    total = len(filas)
    if not total:
        print("No se evaluo ningun caso.")
        return
    primera = sum(f["acerto_a_la_primera"] for f in filas)
    plantilla = sum(f["cayo_a_plantilla"] for f in filas)
    con_retry = total - primera - plantilla
    inconsist = sum(1 for f in filas if f["posibles_inconsistencias"])
    tiempo_prom = sum(f["segundos"] for f in filas) / total

    print(f"\n{'='*70}\nRESUMEN ({total} casos)\n{'='*70}")
    print(f"  Acerto a la primera:        {primera:>3} ({100*primera/total:.0f}%)")
    print(f"  Acerto tras corregir:       {con_retry:>3} ({100*con_retry/total:.0f}%)")
    print(f"  Cayo a la plantilla:        {plantilla:>3} ({100*plantilla/total:.0f}%)")
    print(f"  Con posible inconsistencia: {inconsist:>3} ({100*inconsist/total:.0f}%)  <- heuristica, revisar a mano")
    print(f"  Tiempo promedio por caso:   {tiempo_prom:.1f} s")

    print(f"\n{'area':<14}{'periodo':<10}{'rojo':>5}{'ambar':>6}{'vigilar':>8}   {'resultado':<22}{'seg':>6}")
    for f in filas:
        if f["cayo_a_plantilla"]:
            resultado = "plantilla (fallo)"
        elif f["intentos_fallidos_antes_de_aceptar"]:
            resultado = f"IA (corrigio {f['intentos_fallidos_antes_de_aceptar']}x)"
        else:
            resultado = "IA (a la primera)"
        marca = " !" if f["posibles_inconsistencias"] else ""
        print(
            f"{f['area']:<14}{f['periodo']:<10}{f['rojo']:>5}{f['amarillo']:>6}{f['por_vigilar']:>8}   "
            f"{resultado:<22}{f['segundos']:>6.1f}{marca}"
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--casos", help='ej. "Operaciones:2026-04,Ventas:2026-06" (por defecto, una muestra curada de 10)')
    ap.add_argument("--aleatorio", type=int, metavar="N", help="N casos al azar (semilla fija) en vez de la muestra curada")
    ap.add_argument("--salida", help="ruta del CSV (por defecto: reportes/evaluacion_AAAAMMDD_HHMM.csv)")
    args = ap.parse_args()

    proveedor = obtener_proveedor()
    if proveedor is None:
        raise SystemExit("LLM_PROVEEDOR esta desactivado en tu .env; esta evaluacion necesita un modelo real.")

    df = calcular_kpis()
    casos = elegir_casos(df, args)
    areas = df[["area_id", "area"]].drop_duplicates().set_index("area")["area_id"]

    RAIZ_REPORTES.mkdir(exist_ok=True)
    salida = Path(args.salida) if args.salida else RAIZ_REPORTES / f"evaluacion_{datetime.now():%Y%m%d_%H%M}.csv"
    columnas = [
        "area", "periodo", "rojo", "amarillo", "por_vigilar", "origen", "acerto_a_la_primera",
        "intentos_fallidos_antes_de_aceptar", "cayo_a_plantilla", "motivo_plantilla",
        "posibles_inconsistencias", "segundos",
    ]

    print(f"Modelo: {proveedor.modelo}  |  Casos: {len(casos)}  |  Guardando en: {salida}")
    print("Cada caso puede tardar 30-90 segundos en CPU. Progreso:\n")

    filas = []
    with open(salida, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=columnas)
        escritor.writeheader()
        for i, (area, periodo) in enumerate(casos, 1):
            print(f"[{i}/{len(casos)}] {area} {periodo}...", end=" ", flush=True)
            try:
                fila = evaluar_uno(int(areas[area]), area, periodo, proveedor, df)
            except Exception as exc:
                print(f"ERROR: {exc}")
                fila = {c: "" for c in columnas}
                fila.update(area=area, periodo=periodo, motivo_plantilla=f"error: {exc}")
            else:
                estado = "plantilla" if fila["cayo_a_plantilla"] else f"IA ({fila['intentos_fallidos_antes_de_aceptar']} correccion(es))"
                print(f"{estado} en {fila['segundos']}s")
            filas.append(fila)
            escritor.writerow(fila)
            f.flush()  # progreso guardado aunque se interrumpa a la mitad

    imprimir_resumen(filas)
    print(f"\nCSV guardado en: {salida}")


if __name__ == "__main__":
    main()