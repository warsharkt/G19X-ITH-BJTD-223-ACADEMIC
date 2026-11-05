"""Da de alta o renombra un area despues de la primera plantilla de personal.

Uso (en Docker, desde la raiz del proyecto):
    docker compose exec api python -m scripts.areas --listar
    docker compose exec api python -m scripts.areas --agregar "Compras"
    docker compose exec api python -m scripts.areas --renombrar "Ventas" "Comercial"

Los indicadores se actualizan solos en menos de un minuto. Cada cambio queda en
la bitacora de cuentas.
"""
import argparse
import getpass

from app import areas
from app.seguridad import ErrorDeUsuario

POR = f"consola:{getpass.getuser()}"


def main():
    ap = argparse.ArgumentParser(description="Áreas de la empresa")
    ap.add_argument("--listar", action="store_true", help="muestra las áreas")
    ap.add_argument("--agregar", metavar="NOMBRE", help="agrega un área nueva")
    ap.add_argument("--renombrar", nargs=2, metavar=("ACTUAL", "NUEVO"), help="cambia el nombre de un área")
    args = ap.parse_args()
    try:
        if args.agregar:
            print(f"Área '{areas.agregar(args.agregar, POR)}' agregada.")
        elif args.renombrar:
            print(f"El área ahora se llama '{areas.renombrar(*args.renombrar, POR)}'.")
        else:
            print("\n".join(areas.listar()) or "Todavía no hay áreas.")
    except ErrorDeUsuario as exc:
        raise SystemExit(f"No se pudo: {exc}")


if __name__ == "__main__":
    main()
