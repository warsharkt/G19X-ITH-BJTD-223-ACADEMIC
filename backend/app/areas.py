"""Las areas de la empresa despues de la primera plantilla de personal.

La primera plantilla las define (app/cargas.py). Despues, un area desconocida
en un archivo es un error, para que un error de dedo no invente una: las areas
nuevas o renombradas se dan de alta aqui (scripts/areas.py, en la consola del
servidor). Los datos van por id, asi que renombrar no pierde historia; los
reportes ya generados conservan el nombre que tenian.
"""
from sqlalchemy import text

from app import cargas, seguridad
from app.database import engine
from app.seguridad import ErrorDeUsuario


def listar() -> list[str]:
    with engine.connect() as conn:
        return list(conn.execute(text("SELECT nombre FROM areas ORDER BY nombre")).scalars())


def _validar(conn, nombre: str) -> str:
    nombre = nombre.strip()
    clave = cargas._clave(nombre)
    if not cargas.nombre_de_area_valido(nombre):
        raise ErrorDeUsuario(
            f"'{nombre}' no sirve como nombre de área (máximo {cargas.AREA_LARGO_MAXIMO} caracteres, sin símbolos; "
            "Corporativo es el consolidado)"
        )
    if clave in {cargas._clave(n) for n in conn.execute(text("SELECT nombre FROM areas")).scalars()}:
        raise ErrorDeUsuario(f"Ya existe un área llamada '{nombre}'")
    return nombre


def agregar(nombre: str, por: str) -> str:
    seguridad.asegurar_tabla()
    with engine.begin() as conn:
        if not conn.execute(text("SELECT EXISTS (SELECT 1 FROM areas)")).scalar():
            raise ErrorDeUsuario("Todavía no hay áreas: las define la primera plantilla de personal")
        nombre = _validar(conn, nombre)
        conn.execute(text("INSERT INTO areas (nombre) VALUES (:n)"), {"n": nombre})
        seguridad.registrar(conn, f"área: {nombre}", "crear_area", por)
    return nombre


def renombrar(actual: str, nuevo: str, por: str) -> str:
    seguridad.asegurar_tabla()
    with engine.begin() as conn:
        nuevo = _validar(conn, nuevo) if cargas._clave(actual) != cargas._clave(nuevo) else nuevo.strip()
        cambiadas = conn.execute(
            text("UPDATE areas SET nombre = :n WHERE nombre = :a"), {"n": nuevo, "a": actual.strip()}
        ).rowcount
        if not cambiadas:
            raise ErrorDeUsuario(f"El área '{actual}' no existe")
        seguridad.registrar(conn, f"área: {nuevo}", "renombrar_area", por, {"nombre": [actual.strip(), nuevo]})
    return nuevo
