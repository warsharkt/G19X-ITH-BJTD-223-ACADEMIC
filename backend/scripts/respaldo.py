"""Respaldo de la base de datos y prueba de que se puede restaurar (P8).

Trabaja con el PostgreSQL de Docker (contenedor DB_CONTENEDOR, rrhh_db por
defecto): usa el pg_dump de adentro del contenedor, asi que no hace falta
instalar PostgreSQL en el equipo.

- Cada respaldo se PRUEBA: se restaura en una base temporal y se comparan las
  filas de cada tabla contra la base real. Si no cuadra, termina con error
  (el Programador de tareas lo marca como fallido).
- Junto a cada respaldo queda su huella SHA-256 (.sha256); al restaurar se
  verifica, para no restaurar un archivo danado o cambiado.
- Se conservan los ultimos RESPALDOS_CONSERVAR (30 por defecto); los mas
  viejos se borran.
- La llave del MFA (llaves/mfa.key o MFA_LLAVE) NUNCA va en el respaldo: con
  --llave se copia a OTRO lugar (otra unidad, una USB). Si alguien se lleva
  el respaldo sin la llave, no puede generar codigos de verificacion.

Con datos reales, los respaldos tienen datos de colaboradores: guardalos en
un disco cifrado y con acceso solo para TI.

Uso (desde la carpeta backend, con el entorno virtual activo):
    python -m scripts.respaldo                       # respalda y prueba
    python -m scripts.respaldo --llave E:\\llave     # ademas copia la llave del MFA
    python -m scripts.respaldo --ver                 # lista los respaldos
    python -m scripts.respaldo --restaurar ARCHIVO   # restaura (pide confirmacion)

Programador de tareas de Windows, todos los dias a las 2:00 (cambia la ruta):
    schtasks /create /tn "Talentia Insights respaldo" /sc daily /st 02:00 /tr "cmd /c cd /d C:\\ruta\\backend && .venv\\Scripts\\python.exe -m scripts.respaldo"
"""
import argparse
import hashlib
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from app import mfa
from app.database import RAIZ

PREFIJO = "talentia-"
BASE_DE_PRUEBA = "talentia_prueba_restauracion"
# Filas por tabla, todas las tablas del esquema public, en una sola consulta
_CONTEO = (
    "SELECT table_name || '|' || (xpath('/row/c/text()', query_to_xml("
    "format('SELECT count(*) AS c FROM public.%I', table_name), false, true, '')))[1]::text "
    "FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY 1"
)


LLAVE_JUNTO_A_RESPALDOS = "La llave del MFA no se guarda junto a los respaldos: elige otra carpeta (otra unidad o una USB)"


class ErrorDeRespaldo(RuntimeError):
    pass


# ------------------------------------------------------------- configuracion
def carpeta() -> Path:
    return Path(os.getenv("RESPALDOS_DIR") or RAIZ / "respaldos")


def contenedor() -> str:
    return os.getenv("DB_CONTENEDOR", "rrhh_db")


def usuario_db() -> str:
    return os.getenv("POSTGRES_USER", "postgres")


def base_db() -> str:
    return os.getenv("POSTGRES_DB", "postgres")


def conservar_por_defecto() -> int:
    return int(os.getenv("RESPALDOS_CONSERVAR", "30"))


# --------------------------------------------------------------- docker exec
def _docker(*args, entrada=None, salida=None, interactivo=False) -> str:
    """Corre un comando dentro del contenedor de la base. Devuelve su salida
    de texto (o la escribe en `salida`, para los respaldos binarios)."""
    comando = ["docker", "exec", *(["-i"] if interactivo else []), contenedor(), *args]
    try:
        r = subprocess.run(comando, stdin=entrada, stdout=salida or subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise ErrorDeRespaldo("No se encontró el comando docker. Abre Docker Desktop y vuelve a intentarlo")
    if r.returncode != 0:
        detalle = r.stderr.decode(errors="replace").strip()
        raise ErrorDeRespaldo(f"Falló {' '.join(args[:1])} en el contenedor {contenedor()}: {detalle}")
    return "" if salida else r.stdout.decode(errors="replace")


def _psql(base: str, consulta: str) -> str:
    return _docker("psql", "-U", usuario_db(), "-d", base, "-v", "ON_ERROR_STOP=1", "-tAc", consulta)


def conteos(base: str) -> dict[str, int]:
    filas = [linea.split("|") for linea in _psql(base, _CONTEO).splitlines() if linea.strip()]
    return {tabla: int(n) for tabla, n in filas}


def _sin_conexiones(base: str):
    """Cierra las conexiones abiertas a la base (la API, una prueba...)."""
    _psql("postgres", f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                      f"WHERE datname = '{base}' AND pid <> pg_backend_pid()")


def _restaurar_en(base: str, archivo: Path):
    """Borra `base`, la crea vacia y le carga el respaldo (todo o nada)."""
    _sin_conexiones(base)
    _docker("dropdb", "-U", usuario_db(), "--if-exists", base)
    _docker("createdb", "-U", usuario_db(), base)
    with open(archivo, "rb") as f:
        _docker("pg_restore", "-U", usuario_db(), "-d", base, "--no-owner", "--exit-on-error",
                "--single-transaction", entrada=f, interactivo=True)


# ------------------------------------------------------------------- huella
def huella(archivo: Path) -> str:
    h = hashlib.sha256()
    with open(archivo, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _archivo_de_huella(archivo: Path) -> Path:
    return archivo.with_name(archivo.name + ".sha256")


def verificar_huella(archivo: Path):
    esperado = _archivo_de_huella(archivo)
    if not esperado.exists():
        raise ErrorDeRespaldo(f"Falta {esperado.name}: no se puede comprobar que el respaldo esté completo")
    if esperado.read_text(encoding="ascii").split()[0] != huella(archivo):
        raise ErrorDeRespaldo(f"La huella de {archivo.name} no coincide: el archivo está dañado o cambió")


# ------------------------------------------------------------------- reglas
def comparar(antes: dict[str, int], despues: dict[str, int], restaurado: dict[str, int]) -> tuple[list, list]:
    """(diferencias, tablas que cambiaron mientras se respaldaba).

    El respaldo es una foto de un instante entre `antes` y `despues`. Si una
    tabla no cambio en ese lapso, la copia restaurada debe tener exactamente
    las mismas filas; si cambio (la API escribio un aviso), basta con que este
    entre los dos conteos."""
    diferencias, en_movimiento = [], []
    for tabla in sorted(set(antes) | set(despues) | set(restaurado)):
        a, d, r = antes.get(tabla), despues.get(tabla), restaurado.get(tabla)
        if r is None or (a is None and d is None):
            diferencias.append(f"{tabla}: {'falta en el respaldo' if r is None else 'sobra en el respaldo'}")
        elif a == d:
            if r != a:
                diferencias.append(f"{tabla}: {a} filas en la base y {r} en el respaldo")
        else:
            en_movimiento.append(tabla)
            if not min(a or 0, d or 0) <= r <= max(a or 0, d or 0):
                diferencias.append(f"{tabla}: {r} filas en el respaldo, fuera de {a}–{d}")
    return diferencias, en_movimiento


def respaldos(dentro: Path) -> list[Path]:
    """Los respaldos automaticos, del mas viejo al mas nuevo (el nombre lleva la fecha)."""
    return sorted(dentro.glob(f"{PREFIJO}*.dump"))


def sobrantes(archivos: list[Path], conservar: int) -> list[Path]:
    return archivos[:-conservar] if conservar > 0 and len(archivos) > conservar else []


def _dentro_de(ruta: Path, carpeta_: Path) -> bool:
    try:
        ruta.resolve().relative_to(carpeta_.resolve())
        return True
    except ValueError:
        return False


# ----------------------------------------------------------------- acciones
def respaldar(dentro: Path, prefijo: str = PREFIJO) -> Path:
    dentro.mkdir(parents=True, exist_ok=True)
    archivo = dentro / f"{prefijo}{datetime.now():%Y%m%d-%H%M%S}.dump"
    parcial = archivo.with_suffix(".parcial")
    try:
        with open(parcial, "wb") as f:
            _docker("pg_dump", "-U", usuario_db(), "-d", base_db(), "-Fc", salida=f)
        parcial.replace(archivo)  # solo se llama .dump si termino completo
    finally:
        parcial.unlink(missing_ok=True)
    _archivo_de_huella(archivo).write_text(f"{huella(archivo)}  {archivo.name}\n", encoding="ascii")
    return archivo


def probar(archivo: Path, antes: dict[str, int]) -> tuple[int, list]:
    """Restaura el respaldo en una base temporal y lo compara con la real.
    Devuelve (filas restauradas, tablas que cambiaron durante el respaldo)."""
    despues = conteos(base_db())
    try:
        _restaurar_en(BASE_DE_PRUEBA, archivo)
        restaurado = conteos(BASE_DE_PRUEBA)
    finally:
        try:
            _sin_conexiones(BASE_DE_PRUEBA)
            _docker("dropdb", "-U", usuario_db(), "--if-exists", BASE_DE_PRUEBA)
        except ErrorDeRespaldo:
            pass
    diferencias, en_movimiento = comparar(antes, despues, restaurado)
    if diferencias:
        raise ErrorDeRespaldo("El respaldo no cuadra con la base:\n  " + "\n  ".join(diferencias))
    return sum(restaurado.values()), en_movimiento


def copiar_llave(destino: Path, dentro: Path) -> Path:
    if _dentro_de(destino, dentro):
        raise ErrorDeRespaldo(LLAVE_JUNTO_A_RESPALDOS)
    texto = os.getenv("MFA_LLAVE", "").strip()
    if not texto:
        if not mfa.archivo_de_llave().exists():
            raise ErrorDeRespaldo(f"No hay llave del MFA que copiar ({mfa.archivo_de_llave()} no existe)")
        texto = mfa.archivo_de_llave().read_text(encoding="ascii").strip()
    destino.mkdir(parents=True, exist_ok=True)
    copia = destino / f"mfa-{datetime.now():%Y%m%d}.key"
    copia.write_text(texto + "\n", encoding="ascii")
    return copia


def _api_encendida() -> bool:
    """Si el contenedor de la API corre, podria escribir a media restauracion."""
    nombre = os.getenv("API_CONTENEDOR", "rrhh_api")
    try:
        r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", nombre], capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def restaurar(archivo: Path, dentro: Path):
    verificar_huella(archivo)
    if _api_encendida():
        raise ErrorDeRespaldo("Primero apaga la API para que nadie use la base mientras se restaura: docker compose stop api")
    print(f"Se va a REEMPLAZAR toda la base '{base_db()}' por el respaldo {archivo.name}.")
    print("Lo que se haya hecho después de ese respaldo se pierde (antes se guarda una copia del estado actual).")
    try:
        respuesta = input(f"Para confirmar escribe el nombre de la base ({base_db()}): ").strip()
    except EOFError:  # sin teclado (Programador de tareas): nunca se restaura solo
        respuesta = ""
    if respuesta != base_db():
        raise ErrorDeRespaldo("No se confirmó: no se cambió nada")
    previo = respaldar(dentro, prefijo="antes-de-restaurar-")
    print(f"Copia del estado actual: {previo}")
    _restaurar_en(base_db(), archivo)
    print(f"Base restaurada desde {archivo.name}. Vuelve a encender la API: docker compose up -d")


def ver(dentro: Path):
    archivos = sorted(dentro.glob("*.dump"))
    if not archivos:
        print(f"No hay respaldos en {dentro}")
    for a in archivos:
        print(f"  {a.name}  {a.stat().st_size / (1024 * 1024):.1f} MB")


def main():
    ap = argparse.ArgumentParser(description="Respaldo de la base de Talentia Insights")
    ap.add_argument("--llave", type=Path, metavar="CARPETA", help="copia también la llave del MFA a esta carpeta (fuera de los respaldos)")
    ap.add_argument("--sin-probar", action="store_true", help="no restaura el respaldo en una base temporal para probarlo")
    ap.add_argument("--conservar", type=int, default=conservar_por_defecto(), help="cuántos respaldos guardar (0 = todos)")
    ap.add_argument("--ver", action="store_true", help="lista los respaldos")
    ap.add_argument("--restaurar", type=Path, metavar="ARCHIVO", help="reemplaza la base por este respaldo")
    args = ap.parse_args()
    dentro = carpeta()
    try:
        if args.ver:
            ver(dentro)
        elif args.restaurar:
            restaurar(args.restaurar, dentro)
        else:
            if args.llave and _dentro_de(args.llave, dentro):  # antes de respaldar, no despues
                raise ErrorDeRespaldo(LLAVE_JUNTO_A_RESPALDOS)
            antes = None if args.sin_probar else conteos(base_db())
            archivo = respaldar(dentro)
            print(f"Respaldo: {archivo} ({archivo.stat().st_size / (1024 * 1024):.1f} MB)")
            if antes is not None:
                filas, en_movimiento = probar(archivo, antes)
                print(f"Prueba de restauración: correcta ({filas:,} filas en {len(antes)} tablas).")
                if en_movimiento:
                    print(f"  Cambiaron mientras se respaldaba (la API estaba en uso): {', '.join(en_movimiento)}")
            for viejo in sobrantes(respaldos(dentro), args.conservar):
                viejo.unlink()
                _archivo_de_huella(viejo).unlink(missing_ok=True)
                print(f"Se borró el respaldo viejo {viejo.name}")
            if args.llave:
                print(f"Llave del MFA copiada a {copiar_llave(args.llave, dentro)}")
            else:
                print("Recuerda: la llave del MFA no va en el respaldo; cópiala aparte con --llave CARPETA.")
    except (ErrorDeRespaldo, mfa.LlaveMfaInvalida) as exc:
        sys.exit(f"No se pudo: {exc}")


if __name__ == "__main__":
    main()
