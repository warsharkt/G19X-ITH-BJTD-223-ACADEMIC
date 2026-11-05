"""Arranque de la API dentro de Docker (docker-compose.yml, servicio api).

Deja todo listo para entrar sin correr scripts a mano:
  1. Si la base esta vacia y MODO_DATOS=sinteticos, carga los datos ficticios
     de Nordika (scripts/seed.py). Con datos reales nunca siembra nada.
  2. Si el modo demostracion esta activo, crea o restablece las cuentas
     del personal de Nordika (app/demo.py). Si esta apagado, las desactiva.
  3. Crea o actualiza las tablas y prepara la cuenta de PostgreSQL con la que
     se conecta la API (talentia_api): sin privilegios de superusuario, sin ser
     duena de nada, con una contrasena nueva al azar en cada arranque y sin
     poder cambiar ni borrar las bitacoras ni lo ya firmado. Asi una falla en
     la API no da control de la base, ni deja borrar el rastro. Los pasos 1 y
     2, los scripts y las pruebas siguen usando POSTGRES_USER.
  4. Si no hay JWT_SECRETO, genera uno al azar para esta ejecucion (las
     sesiones se cierran al reiniciar el contenedor; nada se guarda en disco).
  5. Arranca la API (uvicorn) en el puerto 8000 del contenedor.

Uso (lo llama el Dockerfile; no hace falta correrlo a mano):
    python -m scripts.arranque
"""
import os
import re
import secrets
import sys

from psycopg import sql
from sqlalchemy import text

from app import avisos, cargas, demo, programacion, seguridad, trabajos
from app.database import ejecutar_sql, engine
from app.kpis import inicializar_umbrales
from app.llm import ConfiguracionIA, modo_datos
from app.seguridad import ErrorDeUsuario


CONTRASENA_DE_EJEMPLO = "cambia_esto"
# La API solo agrega a estas tablas: ni aun ejecutando codigo en ella se borra el rastro
SOLO_AGREGAR = ("usuarios_cambios", "accesos", "exportaciones", "umbrales_cambios")
# Las cuentas y los reportes se desactivan o se rechazan, no se borran
SIN_BORRAR = ("usuarios", "narrativas", "suplencias", "cargas")


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
        # Solo las tablas, sin datos: sin ellas la API no arranca. schema.sql
        # borra las tablas de las fuentes, por eso solo corre con la base vacia.
        ejecutar_sql("schema.sql")
        print("Base vacia y MODO_DATOS=reales: tablas creadas; carga los datos reales desde Carga de datos.")
        return
    from scripts import seed

    print("Base vacia: cargando los datos ficticios de Nordika...")
    seed.cargar()
    ejecutar_sql("rls.sql")


def preparar_demo():
    if (motivo := demo.motivo_inactivo()) is not None:
        for linea in demo.apagar_cuentas(por="arranque:docker"):
            print(f"  {linea}")
        if os.getenv("MODO_DEMO", "no").strip().lower() == "si":
            print(f"Modo demostracion sin cuentas: {motivo}")
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


def preparar_esquema():
    """Crea o actualiza las tablas aqui, como superusuario: la API ya no puede."""
    seguridad.asegurar_tabla()
    trabajos.asegurar_tabla()
    inicializar_umbrales()
    avisos.asegurar_tabla()
    programacion.asegurar_tabla()
    cargas.asegurar_tabla()
    ejecutar_sql("rls.sql")
    if purgados := seguridad.purgar_accesos():
        print(f"Se purgaron {purgados} registros de accesos de hace más de un año.")


def preparar_cuenta_de_la_api() -> dict[str, str]:
    """Crea o actualiza la cuenta de la API y le da solo los permisos que usa.
    Devuelve las variables de entorno que usa app/database.py (vacio si no aplica)."""
    if os.getenv("DATABASE_URL", "").strip():
        print("DATABASE_URL configurada: la API usa esa cuenta tal cual.")
        return {}
    usuario = os.getenv("DB_API_USUARIO", "talentia_api").strip()
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,40}", usuario):
        sys.exit(f"DB_API_USUARIO no es un nombre de rol valido: {usuario!r}")
    contrasena = secrets.token_urlsafe(32)
    with engine.begin() as conn:
        driver = conn.connection.driver_connection

        def ejecutar(plantilla: str, **partes):
            conn.exec_driver_sql(sql.SQL(plantilla).format(**partes).as_string(driver))

        ident = sql.Identifier(usuario)
        existe = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :u"), {"u": usuario}).first()
        ejecutar(
            ("ALTER ROLE {u} WITH" if existe else "CREATE ROLE {u}")
            # BYPASSRLS: las tablas tienen RLS sin politicas, para cerrar la Data API
            # de Supabase (db/rls.sql). Sin ser duena, la API no veria ninguna fila.
            + " LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS PASSWORD {p}",
            u=ident, p=sql.Literal(contrasena),
        )
        ejecutar("GRANT CONNECT ON DATABASE {d} TO {u}", d=sql.Identifier(engine.url.database), u=ident)
        ejecutar("GRANT USAGE ON SCHEMA public TO {u}", u=ident)
        ejecutar("REVOKE CREATE ON SCHEMA public FROM {u}", u=ident)
        # Las versiones anteriores le pasaban las tablas: se las devuelve. Las
        # secuencias de columnas SERIAL cambian de dueno junto con su tabla.
        objetos = conn.execute(text(
            "SELECT c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'S') "
            "AND pg_get_userbyid(c.relowner) = :u "
            "AND NOT (c.relkind = 'S' AND EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype IN ('a', 'i'))) "
            "ORDER BY c.relkind = 'S'"
        ), {"u": usuario}).all()
        tipos = {"r": "TABLE", "p": "TABLE", "v": "VIEW", "m": "MATERIALIZED VIEW", "S": "SEQUENCE"}
        for nombre, tipo in objetos:
            ejecutar(f"ALTER {tipos[tipo]} {{t}} OWNER TO CURRENT_USER", t=sql.Identifier("public", nombre))
        ejecutar("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {u}", u=ident)
        ejecutar("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {u}", u=ident)
        ejecutar("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {u}", u=ident)
        ejecutar("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {u}", u=ident)
        for tabla in SOLO_AGREGAR:
            ejecutar("REVOKE UPDATE, DELETE ON {t} FROM {u}", t=sql.Identifier("public", tabla), u=ident)
        for tabla in SIN_BORRAR:
            ejecutar("REVOKE DELETE ON {t} FROM {u}", t=sql.Identifier("public", tabla), u=ident)
        # Lo que creen despues POSTGRES_USER (seed, respaldo) tambien lo puede usar
        ejecutar("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {u}", u=ident)
        ejecutar("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {u}", u=ident)
        ejecutar("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {u}", u=ident)
        ejecutar("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {u}", u=ident)
    print(f"La API se conecta como '{usuario}' (sin privilegios y sin ser duena de las tablas).")
    return {"DB_API_USUARIO": usuario, "DB_API_CONTRASENA": contrasena, "DB_ESQUEMA_PREPARADO": "si"}


def revisar_contrasena_de_la_base():
    """La del .env.example la conoce cualquiera que lea el repositorio."""
    if os.getenv("POSTGRES_PASSWORD", "") != CONTRASENA_DE_EJEMPLO:
        return
    mensaje = f"POSTGRES_PASSWORD sigue siendo '{CONTRASENA_DE_EJEMPLO}', el valor de ejemplo: cámbiala en el .env"
    if modo_datos() == "reales":
        sys.exit(mensaje)
    print(f"AVISO: {mensaje}")


def main():
    revisar_contrasena_de_la_base()
    sembrar_si_hace_falta()
    preparar_demo()
    preparar_esquema()
    cuenta_api = preparar_cuenta_de_la_api()
    os.environ.update(cuenta_api)
    if cuenta_api:
        # La API ya no la necesita: si se queda en su entorno, cualquier codigo
        # que llegue a ejecutarse en la API podria entrar como superusuario.
        # Los scripts (docker compose exec api ...) la siguen recibiendo del .env.
        os.environ.pop("POSTGRES_PASSWORD", None)
    if len(os.getenv("JWT_SECRETO", "")) < 32:
        os.environ["JWT_SECRETO"] = secrets.token_urlsafe(48)
        print("JWT_SECRETO no configurado: se genero uno temporal para esta ejecucion.")
    os.execvp(
        sys.executable,
        # --proxy-headers: la IP real de quien entra llega de nginx en
        # X-Forwarded-For (el bloqueo por intentos fallidos es por IP). La API
        # solo se publica en 127.0.0.1 y en la red interna de Docker.
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000",
         "--proxy-headers", "--forwarded-allow-ips", "*"],
    )


if __name__ == "__main__":
    main()
