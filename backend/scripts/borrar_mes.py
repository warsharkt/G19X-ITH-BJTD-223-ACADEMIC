"""Borra un mes cargado por error de una fuente mensual.

Sirve para corregir un mes equivocado: la app no borra datos, y un archivo
nuevo no quita el mes que ya entro. Pide confirmar escribiendo el mes. Queda en
la bitacora de cuentas. Los reportes ya firmados no cambian: guardan sus cifras.

Uso (en Docker, desde la raiz del proyecto):
    docker compose exec api python -m scripts.borrar_mes --fuente productividad --mes 2016-09

Fuentes: desempeno, capacitacion, clima, productividad.
"""
import argparse
import getpass
from datetime import datetime

from sqlalchemy import text

from app import seguridad
from app.cargas import MENSUALES
from app.database import engine
from app.seguridad import ErrorDeUsuario


def borrar(fuente: str, mes: str, por: str) -> int:
    """Borra las filas de ese mes y devuelve cuantas. ErrorDeUsuario si no aplica."""
    if fuente not in MENSUALES:
        raise ErrorDeUsuario(f"La fuente debe ser una de: {', '.join(MENSUALES)}")
    try:
        periodo = datetime.strptime(mes, "%Y-%m").date()
    except ValueError:
        raise ErrorDeUsuario("El mes va como AAAA-MM")
    tabla = MENSUALES[fuente]
    seguridad.asegurar_tabla()
    with engine.begin() as conn:
        if fuente == "capacitacion":  # las inscripciones dependen del programa
            conn.execute(
                text("DELETE FROM inscripciones_capacitacion WHERE programa_id IN "
                     "(SELECT id FROM programas_capacitacion WHERE periodo = :p)"),
                {"p": periodo},
            )
        filas = conn.execute(text(f"DELETE FROM {tabla} WHERE periodo = :p"), {"p": periodo}).rowcount
        if filas:
            seguridad.registrar(conn, f"datos: {fuente}", "borrar_mes", por, {"mes": mes, "filas": filas})
    return filas


def main():
    ap = argparse.ArgumentParser(description="Borra un mes cargado por error")
    ap.add_argument("--fuente", required=True, help=", ".join(MENSUALES))
    ap.add_argument("--mes", required=True, help="AAAA-MM")
    args = ap.parse_args()
    print(f"Se van a BORRAR los datos de {args.fuente} del mes {args.mes}. No se puede deshacer.")
    if input("Para confirmar escribe el mes: ").strip() != args.mes:
        raise SystemExit("No se confirmó: no se borró nada")
    try:
        print(f"Se borraron {borrar(args.fuente, args.mes, f'consola:{getpass.getuser()}')} filas.")
    except ErrorDeUsuario as exc:
        raise SystemExit(f"No se pudo: {exc}")


if __name__ == "__main__":
    main()
