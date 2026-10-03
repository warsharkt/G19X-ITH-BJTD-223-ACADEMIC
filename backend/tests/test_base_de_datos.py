"""Pruebas de la conexion (local o Supabase) y del cierre de la Data API (RLS)."""
from sqlalchemy import text

from app.database import _url_desde_entorno, ejecutar_sql, engine

SUPABASE = "postgresql://postgres.abcd:clave@aws-0-us-east-1.pooler.supabase.com:5432/postgres"


def test_sin_database_url_usa_el_postgresql_local(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url = _url_desde_entorno()
    assert url.drivername == "postgresql+psycopg"
    assert url.host in ("localhost", "127.0.0.1")


def test_database_url_de_supabase_usa_nuestro_driver_y_ssl(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", SUPABASE)
    url = _url_desde_entorno()
    assert url.drivername == "postgresql+psycopg"  # Supabase entrega "postgresql://"
    assert url.host == "aws-0-us-east-1.pooler.supabase.com" and url.port == 5432
    assert url.query["sslmode"] == "require"  # siempre cifrada fuera del equipo
    assert url.password == "clave"


def test_respeta_el_sslmode_si_ya_viene_en_la_cadena(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", SUPABASE + "?sslmode=verify-full")
    assert _url_desde_entorno().query["sslmode"] == "verify-full"


def test_todas_las_tablas_quedan_con_rls():
    """Sin RLS, la Data API de Supabase dejaria leer empleados y contrasenas
    con la llave publica. rls.sql debe cubrir TODAS las tablas de public."""
    ejecutar_sql("rls.sql")
    with engine.connect() as conn:
        sin_rls = conn.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity"
            )
        ).scalars().all()
        tablas = conn.execute(text("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")).scalar()
    assert sin_rls == []
    assert tablas >= 12  # 9 de datos + umbrales, narrativas y usuarios


def test_con_rls_el_backend_sigue_leyendo_los_datos():
    """El backend es dueno de las tablas: RLS no lo afecta."""
    ejecutar_sql("rls.sql")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM empleados")).scalar() > 0
