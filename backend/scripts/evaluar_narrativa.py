"""Evalua el modelo de lenguaje en varias combinaciones de area y mes.

Corre generar_narrativa() con IA real en una muestra de casos y mide, para
cada uno: si el modelo acerto a la primera, cuantos intentos necesito, si
no logro una narrativa valida (FALLO), cuanto tardo, y una senal (heuristica,
no un guardarrail) de posibles generalizaciones de direccion incorrectas al
agrupar hechos con "mejoro"/"empeoro" distintos (el error real que
encontramos en Operaciones-febrero).

Usa el proveedor del .env (LLM_PROVEEDOR). Con Ollama en CPU cada caso tarda
2-5 minutos: la muestra por defecto (12 casos) puede tardar 30-60 minutos.
Con Groq (solo datos sinteticos) tarda segundos por caso. Se guarda un CSV
para el informe de QA aunque el script se interrumpa a la mitad (se escribe
fila por fila).

Uso (desde la carpeta backend, con el entorno virtual activo):
    python -m scripts.evaluar_narrativa                       # muestra curada de 12 casos
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
from app.llm import ConfiguracionIA, obtener_proveedor
from app.narrativa import (
    NarrativaNoGenerada,
    construir_hechos,
    conteo_estados,
    es_mes_estable,
    generar_narrativa,
)

RAIZ_REPORTES = Path(__file__).resolve().parents[1] / "reportes"

# Cubre los escenarios que ya vimos a mano: crisis (rojo+amarillo), solo
# amarillo, solo "por vigilar" (sin ninguna alerta), un area pequena con
# indicadores suprimidos y dos meses estables (todo en verde). Los 10
# primeros son los de las evaluaciones anteriores, para poder comparar.
MUESTRA_CURADA = [
    ("Corporativo", "2026-08"), ("Corporativo", "2026-03"),
    ("Operaciones", "2026-04"), ("Operaciones", "2026-02"), ("Operaciones", "2026-07"),
    ("Ventas", "2026-06"), ("TI", "2026-05"), ("Finanzas", "2026-01"),
    ("Marketing", "2026-06"), ("Legal", "2026-08"),
    ("Ventas", "2024-10"), ("Finanzas", "2025-04"),
]

COLUMNAS = [
    "proveedor", "modelo", "area", "periodo", "rojo", "amarillo", "por_vigilar", "mes_estable",
    "resultado", "acerto_a_la_primera", "intentos", "motivo_fallo", "detalle",
    "posibles_inconsistencias", "segundos",
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
    mes = pd.Timestamp(periodo + "-01")
    hechos = construir_hechos(df, mes, area_id)
    c = conteo_estados(hechos)
    fila = {
        "proveedor": proveedor.nombre, "modelo": proveedor.modelo, "area": area, "periodo": periodo,
        "rojo": c["rojo"], "amarillo": c["amarillo"], "por_vigilar": c["por_vigilar"],
        "mes_estable": es_mes_estable(hechos),
    }
    inicio = time.perf_counter()
    try:
        n = generar_narrativa(mes, area_id, proveedor=proveedor, df=df)
    except NarrativaNoGenerada as exc:
        fila.update(
            resultado="fallo", acerto_a_la_primera=False, intentos=len(exc.detalle) or 1,
            motivo_fallo=exc.motivo, detalle=" | ".join(exc.detalle), posibles_inconsistencias="",
        )
    else:
        fila.update(
            resultado="ok", acerto_a_la_primera=n["intentos"] == 1, intentos=n["intentos"],
            motivo_fallo="", detalle=" | ".join(n["advertencias"]),
            posibles_inconsistencias=" | ".join(posibles_inconsistencias(n)),
        )
    fila["segundos"] = round(time.perf_counter() - inicio, 1)
    return fila


def imprimir_resumen(filas: list[dict]):
    total = len(filas)
    if not total:
        print("No se evaluo ningun caso.")
        return
    primera = sum(f["acerto_a_la_primera"] is True for f in filas)
    fallos = sum(f["resultado"] != "ok" for f in filas)
    con_retry = total - primera - fallos
    inconsist = sum(1 for f in filas if f["posibles_inconsistencias"])
    tiempos = [f["segundos"] for f in filas if f["segundos"] != ""]
    tiempo_prom = sum(tiempos) / len(tiempos) if tiempos else 0

    print(f"\n{'='*70}\nRESUMEN ({total} casos) - {filas[0]['proveedor']} / {filas[0]['modelo']}\n{'='*70}")
    print(f"  Acerto a la primera:        {primera:>3} ({100*primera/total:.0f}%)")
    print(f"  Acerto tras corregir:       {con_retry:>3} ({100*con_retry/total:.0f}%)")
    print(f"  FALLO (sin narrativa):      {fallos:>3} ({100*fallos/total:.0f}%)")
    print(f"  Con posible inconsistencia: {inconsist:>3} ({100*inconsist/total:.0f}%)  <- heuristica, revisar a mano")
    print(f"  Tiempo promedio por caso:   {tiempo_prom:.1f} s")

    print(f"\n{'area':<14}{'periodo':<10}{'rojo':>5}{'ambar':>6}{'vigilar':>8}   {'resultado':<26}{'seg':>7}")
    for f in filas:
        if f["resultado"] != "ok":
            resultado = "FALLO"
        elif f["intentos"] > 1:
            resultado = f"IA (corrigio {f['intentos'] - 1}x)"
        else:
            resultado = "IA (a la primera)"
        if f["mes_estable"] is True:
            resultado += " estable"
        marca = " !" if f["posibles_inconsistencias"] else ""
        print(
            f"{f['area']:<14}{f['periodo']:<10}{f['rojo']:>5}{f['amarillo']:>6}{f['por_vigilar']:>8}   "
            f"{resultado:<26}{f['segundos']:>7}{marca}"
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--casos", help='ej. "Operaciones:2026-04,Ventas:2026-06" (por defecto, una muestra curada de 12)')
    ap.add_argument("--aleatorio", type=int, metavar="N", help="N casos al azar (semilla fija) en vez de la muestra curada")
    ap.add_argument("--salida", help="ruta del CSV (por defecto: reportes/evaluacion_AAAAMMDD_HHMM.csv)")
    args = ap.parse_args()

    try:
        proveedor = obtener_proveedor()
    except ConfiguracionIA as exc:
        raise SystemExit(f"Configuracion de IA no valida: {exc}")

    df = calcular_kpis()
    casos = elegir_casos(df, args)
    areas = df[["area_id", "area"]].drop_duplicates().set_index("area")["area_id"]

    RAIZ_REPORTES.mkdir(exist_ok=True)
    salida = Path(args.salida) if args.salida else RAIZ_REPORTES / f"evaluacion_{datetime.now():%Y%m%d_%H%M}.csv"

    print(f"{proveedor.nombre} / {proveedor.modelo}  |  Casos: {len(casos)}  |  Guardando en: {salida}")
    print("Con Ollama en CPU cada caso puede tardar varios minutos. Progreso:\n")

    filas = []
    with open(salida, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
        escritor.writeheader()
        for i, (area, periodo) in enumerate(casos, 1):
            print(f"[{i}/{len(casos)}] {area} {periodo}...", end=" ", flush=True)
            try:
                fila = evaluar_uno(int(areas[area]), area, periodo, proveedor, df)
            except Exception as exc:
                print(f"ERROR: {exc}")
                fila = {c: "" for c in COLUMNAS}
                fila.update(
                    proveedor=proveedor.nombre, modelo=proveedor.modelo, area=area, periodo=periodo,
                    rojo=0, amarillo=0, por_vigilar=0, resultado="error",
                    acerto_a_la_primera=False, motivo_fallo=f"error: {exc}",
                )
            else:
                estado = "FALLO" if fila["resultado"] != "ok" else f"IA ({fila['intentos']} intento(s))"
                print(f"{estado} en {fila['segundos']}s")
            filas.append(fila)
            escritor.writerow(fila)
            f.flush()  # progreso guardado aunque se interrumpa a la mitad

    imprimir_resumen(filas)
    print(f"\nCSV guardado en: {salida}")


if __name__ == "__main__":
    main()
