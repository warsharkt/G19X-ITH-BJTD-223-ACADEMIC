"""Arranque de la API dentro de Docker (docker-compose.yml, servicio api).

Deja todo listo para entrar sin correr scripts a mano:
  1. Si la base esta vacia y MODO_DATOS=sinteticos, carga los datos ficticios
     de Nordika (scripts/seed.py). Con datos reales nunca siembra nada.
  2. Si el modo demostracion esta activo, crea o restablece las cuentas
     del personal de Nordika (app/demo.py).
  3. Si no hay JWT_SECRETO, genera uno al azar para esta ejecucion (las
     sesiones se cierran al reiniciar el contenedor; nada se guarda en disco).
  4. Arranca la API (uvicorn) en el puerto 8000 del contenedor.

Uso (lo llama el Dockerfile; no hace falta correrlo a mano):
    python -m scripts.arranque
"""
import os
import secrets
import sys

from sqlalchemy import text

from app import demo
from app.database import ejecutar_sql, engine
from app.llm import ConfiguracionIA, modo_datos
from app.seguridad import ErrorDeUsuario


def base_vacia() -> bool:
    with engine.connect() as conn:
        return not conn.execute(text("SELECT to_regclass('public.empleados') IS NOT NULL")).scalar()


def sembrar_si_hace_falta():
    try:
        sinteticos = modo_datos() == "sinteticos"
    except ConfiguracionIA as exc:
        sys.exit(f"Configuracion de IA no valida: {exc}")
    if not base_vacia():
        print("Base de datos con datos: no se siembra nada.")
        return
    if not sinteticos:
        print("Base vacia y MODO_DATOS=reales: carga los datos reales desde Carga de datos.")
        return
    from scripts import seed

    print("Base vacia: cargando los datos ficticios de Nordika...")
    seed.cargar()
    ejecutar_sql("rls.sql")


def preparar_demo():
    if os.getenv("MODO_DEMO", "no").strip().lower() != "si":
        return
    try:
        for linea in demo.preparar_cuentas(por="arranque:docker"):
            print(f"  {linea}")
    except ErrorDeUsuario as exc:
        print(f"Modo demostracion sin cuentas: {exc}")
        return
    # los usuarios salen en el log (docker compose logs api); la contrasena no
    print("Cuentas de prueba (contrasena: DEMO_CONTRASENA del .env):")
    for usuario, nombre, *_, cargo, _que_hace in demo.CUENTAS:
        print(f"  {usuario:<16}{nombre}, {cargo}")


def main():
    sembrar_si_hace_falta()
    preparar_demo()
    if len(os.getenv("JWT_SECRETO", "")) < 32:
        os.environ["JWT_SECRETO"] = secrets.token_urlsafe(48)
        print("JWT_SECRETO no configurado: se genero uno temporal para esta ejecucion.")
    os.execvp(
        sys.executable,
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
    )


if __name__ == "__main__":
    main()
