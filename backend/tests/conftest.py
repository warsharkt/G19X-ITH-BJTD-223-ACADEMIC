"""Configuracion comun de las pruebas.

Antes de correr nada, comprueba que PostgreSQL responda y tenga datos. Si no,
detiene la corrida con un mensaje claro en segundos (sin esto, cada prueba
esperaba su propio timeout y una corrida podia tardar mas de una hora).
"""
import pytest
from sqlalchemy import text

from app.database import DB_URL, engine


@pytest.fixture(scope="session", autouse=True)
def _base_de_datos_lista():
    destino = f"{DB_URL.host}:{DB_URL.port}"
    try:
        with engine.connect() as conn:
            hay_datos = conn.execute(text("SELECT to_regclass('public.empleados') IS NOT NULL")).scalar()
    except Exception as exc:
        pytest.exit(
            f"\nNo se pudo conectar a PostgreSQL en {destino} ({type(exc).__name__}).\n"
            "  1. Abre Docker Desktop y espera a que diga que esta corriendo.\n"
            "  2. Desde la raiz del proyecto: docker compose up -d\n"
            "  3. Comprueba que el estado sea 'healthy': docker compose ps\n"
            "Si usas PostgreSQL instalado en Windows, revisa DB_PORT en tu .env.\n",
            returncode=2,
        )
    if not hay_datos:
        pytest.exit(
            "\nPostgreSQL responde pero no hay datos. Carga los datos de prueba con:\n"
            "  python -m scripts.seed\n",
            returncode=2,
        )