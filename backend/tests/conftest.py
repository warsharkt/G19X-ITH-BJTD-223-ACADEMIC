"""Configuracion comun de las pruebas.

Antes de correr nada, comprueba que PostgreSQL responda y tenga datos. Si no,
detiene la corrida con un mensaje claro en segundos (sin esto, cada prueba
esperaba su propio timeout y una corrida podia tardar mas de una hora).
"""
import os

import pytest
from sqlalchemy import text

from app.database import DB_URL, ES_REMOTA, engine
from app.main import app
from app.seguridad import Usuario, usuario_actual


@pytest.fixture(scope="session", autouse=True)
def _base_de_datos_lista():
    destino = f"{DB_URL.host}:{DB_URL.port}"
    if ES_REMOTA and os.getenv("PRUEBAS_EN_REMOTO", "").lower() != "si":
        # las pruebas crean y borran usuarios y narrativas: en una base
        # compartida (Supabase) afectarian a quien la este usando
        pytest.exit(
            f"\nLas pruebas apuntan a una base REMOTA ({destino}).\n"
            "Corre las pruebas contra el PostgreSQL local: comenta DATABASE_URL en tu .env.\n"
            "Si de verdad quieres correrlas ahi: PRUEBAS_EN_REMOTO=si\n",
            returncode=2,
        )
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

# Usuario con el que corren las pruebas que no son de seguridad: RRHH ve todo.
# Las pruebas de permisos (test_seguridad.py) quitan este atajo y usan
# usuarios reales con su contrasena y su token.
USUARIO_RRHH = Usuario(id=-1, usuario="pruebas_rrhh", nombre="Pruebas RRHH", rol="rrhh", area_id=None)


@pytest.fixture(autouse=True)
def _sesion_de_rrhh():
    app.dependency_overrides[usuario_actual] = lambda: USUARIO_RRHH
    yield
    app.dependency_overrides.pop(usuario_actual, None)
