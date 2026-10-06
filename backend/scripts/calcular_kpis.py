"""Calcula los KPIs y muestra un resumen en consola.

Uso (desde la carpeta backend, con el entorno virtual activo):
    python -m scripts.calcular_kpis                  # ultimo mes con datos
    python -m scripts.calcular_kpis --periodo 2026-03
"""
import argparse

import pandas as pd

from app.kpis import calcular_kpis


def fmt(x, con_signo=False):
    if pd.isna(x):
        return "-"
    return f"{x:+.1f}" if con_signo else f"{x:,.1f}"


def tabla(df):
    print(f"  {'indicador':<34}{'valor':>10}{'vs mes ant':>12}{'vs anio ant':>13}   estado")
    for f in df.itertuples():
        print(
            f"  {f.nombre + ' (' + f.unidad + ')':<34}{fmt(f.valor):>10}"
            f"{fmt(f.var_mes_ant, True):>12}{fmt(f.var_anio_ant, True):>13}   {f.estado}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--periodo", help="mes a mostrar, formato AAAA-MM (por defecto el ultimo)")
    args = parser.parse_args()

    df = calcular_kpis()
    periodo = pd.Timestamp(args.periodo + "-01") if args.periodo else df["periodo"].max()
    print(f"Meses con datos: {df['periodo'].min():%Y-%m} a {df['periodo'].max():%Y-%m}")
    print(f"Indicadores calculados: {len(df)} filas ({df['indicador'].nunique()} indicadores)")

    print(f"\n=== Consolidado corporativo - {periodo:%Y-%m} ===")
    tabla(df[(df["area"] == "Corporativo") & (df["periodo"] == periodo)])

    print("\n=== Operaciones: clima y rotacion (escenario sembrado) ===")
    op = df[
        (df["area"] == "Operaciones")
        & df["indicador"].isin(["enps", "rotacion_total"])
        & (df["periodo"] >= periodo - pd.DateOffset(months=8))
        & (df["periodo"] <= periodo)
    ]
    print(f"  {'mes':<10}{'eNPS':>9}{'estado':>11}{'rotacion %':>13}{'estado':>11}")
    for mes, g in op.groupby("periodo"):
        e = g[g["indicador"] == "enps"].iloc[0]
        r = g[g["indicador"] == "rotacion_total"].iloc[0]
        print(
            f"  {mes:%Y-%m}   {fmt(e.valor):>9}{e.estado:>11}{fmt(r.valor):>13}{r.estado:>11}"
        )

    print(f"\n=== Jurídico (4 personas) - {periodo:%Y-%m}: regla de tamano minimo de grupo ===")
    legal = df[(df["area"] == "Jurídico") & (df["periodo"] == periodo)]
    for f in legal[legal["indicador"].isin(["cumplimiento_metas", "enps"])].itertuples():
        valor = "oculto" if f.suprimido else fmt(f.valor)
        print(f"  {f.nombre:<24} n={f.n}  valor: {valor:<8} estado: {f.estado}")


if __name__ == "__main__":
    main()
