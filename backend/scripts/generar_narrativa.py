"""Genera la narrativa ejecutiva de un area y mes y la muestra en consola.

Uso (desde la carpeta backend, con el entorno virtual activo):
    python -m scripts.generar_narrativa --sin-ia                   # solo plantilla, sin modelo
    python -m scripts.generar_narrativa                            # con Ollama (corporativo, ultimo mes)
    python -m scripts.generar_narrativa --area Operaciones --periodo 2026-04
    python -m scripts.generar_narrativa --area Operaciones --periodo 2026-04 --ver-prompt
"""
import argparse
import textwrap

import pandas as pd

from app.kpis import calcular_kpis
from app.llm import obtener_proveedor
from app.narrativa import construir_hechos, construir_mensajes, generar_narrativa


def parrafo(texto, sangria="  "):
    return textwrap.fill(texto, width=96, initial_indent=sangria, subsequent_indent=sangria)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--periodo", help="AAAA-MM (por defecto el ultimo mes con datos)")
    ap.add_argument("--area", default="Corporativo", help="nombre del area (por defecto Corporativo)")
    ap.add_argument("--sin-ia", action="store_true", help="usar solo la plantilla determinista")
    ap.add_argument("--ver-prompt", action="store_true", help="mostrar el prompt que recibe el modelo y salir")
    args = ap.parse_args()

    df = calcular_kpis()
    areas = df[["area_id", "area"]].drop_duplicates()
    coincidencia = areas[areas["area"].str.lower() == args.area.lower()]
    if coincidencia.empty:
        raise SystemExit(f"Area '{args.area}' no existe. Opciones: {', '.join(areas['area'])}")
    area_id = int(coincidencia["area_id"].iloc[0])
    periodo = pd.Timestamp(args.periodo + "-01") if args.periodo else df["periodo"].max()

    if args.ver_prompt:
        hechos = construir_hechos(df, periodo, area_id)
        for m in construir_mensajes(hechos, periodo, coincidencia["area"].iloc[0]):
            print(f"--- {m['role'].upper()} ---\n{m['content']}\n")
        return

    proveedor = None if args.sin_ia else obtener_proveedor()
    if proveedor is not None:
        print(f"Consultando al modelo '{proveedor.modelo}' (en CPU puede tardar uno o dos minutos)...")

    n = generar_narrativa(periodo=periodo, area_id=area_id, proveedor=proveedor, df=df)

    origen = f"IA ({n['modelo']})" if n["origen"] == "llm" else "plantilla determinista (sin IA)"
    c = n["conteo_estados"]
    print(f"\n=== {n['area']} - {n['periodo']} ===")
    print(f"Redactado por: {origen}")
    print(f"Indicadores: {c['rojo']} rojo, {c['amarillo']} amarillo, {c['verde']} verde\n")
    print("RESUMEN")
    print(parrafo(n["resumen"]))

    print("\nHALLAZGOS")
    for i, h in enumerate(n["hallazgos"], 1):
        print(f"  {i}. {h['titulo']}   [confianza {h['confianza']}; hechos {', '.join(h['hechos'])}]")
        print(parrafo(h["texto"], "     "))

    print("\nRECOMENDACIONES (sugerencias para valoracion de RRHH)")
    for i, r in enumerate(n["recomendaciones"], 1):
        print(f"  {i}. [confianza {r['confianza']}; hechos {', '.join(r['hechos'])}]")
        print(parrafo(r["accion"], "     "))
        print(f"     Fuentes: {'; '.join(r['fuentes'])}")

    if n["advertencias"]:
        print("\nADVERTENCIAS")
        for a in n["advertencias"]:
            print(parrafo("- " + a))
    print("\nRequiere revision y aprobacion de RRHH antes de distribuirse.")


if __name__ == "__main__":
    main()
