"""Configuracion comun de las pruebas.

Antes de correr nada, comprueba que PostgreSQL responda y tenga datos. Si no,
detiene la corrida con un mensaje claro en segundos (sin esto, cada prueba
esperaba su propio timeout y una corrida podia tardar mas de una hora).
"""
import os

import pytest
from sqlalchemy import text

from app import avisos
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

@pytest.fixture(scope="session", autouse=True)
def _sin_bitacora_de_cuentas_de_prueba(_base_de_datos_lista):
    """Las cuentas de prueba (prefijo zz_) se crean por modulo y se borran al
    final, pero su bitacora no tiene llave foranea: se limpia aqui."""
    yield
    with engine.begin() as conn:
        conn.execute(text(r"DELETE FROM usuarios_cambios WHERE usuario LIKE 'zz\_%' OR hecho_por LIKE 'pruebas\_%'"))


# Usuario con el que corren las pruebas que no son de seguridad: RRHH ve todo.
# Las pruebas de permisos (test_seguridad.py) quitan este atajo y usan
# usuarios reales con su contrasena y su token.
USUARIO_RRHH = Usuario(id=-1, usuario="pruebas_rrhh", nombre="Pruebas RRHH", rol="rrhh", area_id=None)


@pytest.fixture(autouse=True)
def _sesion_de_rrhh():
    app.dependency_overrides[usuario_actual] = lambda: USUARIO_RRHH
    yield
    app.dependency_overrides.pop(usuario_actual, None)


@pytest.fixture(autouse=True)
def _entorno_de_prueba(monkeypatch):
    """- Nunca se mandan correos reales, aunque el .env tenga SMTP.
    - El MFA obligatorio se prueba en test_cuentas.py; en las demas pruebas
      las cuentas de cada rol entran solo con contrasena.
    - Se borran los avisos y la bitacora de cuentas que genere la prueba: una
      narrativa de prueba que termina avisa a todo RRHH, incluidos los
      usuarios reales de la base local."""
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setenv("MFA_OBLIGATORIO", "")
    avisos.asegurar_tabla()
    with engine.connect() as conn:
        ultimo_aviso = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM avisos")).scalar()
        ultimo_cambio = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM usuarios_cambios")).scalar()
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM avisos WHERE id > :u"), {"u": ultimo_aviso})
        conn.execute(text("DELETE FROM usuarios_cambios WHERE id > :u"), {"u": ultimo_cambio})
