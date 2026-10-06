"""Crea usuarios del sistema o les cambia la contrasena.

La contrasena se escribe oculta (no aparece en pantalla ni en el historial
de la terminal). Minimo 10 caracteres y sin incluir el nombre de usuario.

Uso (desde la carpeta backend, con el entorno virtual activo):
    python -m scripts.crear_usuario --usuario ana --nombre "Ana Lopez" --rol rrhh --correo ana@empresa.com
    python -m scripts.crear_usuario --usuario luis --nombre "Luis Perez" --rol gerente --area Ventas
    python -m scripts.crear_usuario --usuario dir --nombre "Direccion General" --rol direccion
    python -m scripts.crear_usuario --usuario ti --nombre "Soporte TI" --rol admin_ti
    python -m scripts.crear_usuario --usuario ana --cambiar-contrasena
    python -m scripts.crear_usuario --usuario ana --cambiar-correo ana@empresa.com   ("" lo quita)
    python -m scripts.crear_usuario --usuario ana --reiniciar-mfa   (telefono perdido)
    python -m scripts.crear_usuario --listar

Roles: direccion (solo consolidado), rrhh (todo), gerente (solo su area),
admin_ti (configuracion, sin datos de colaboradores).

El correo es opcional: si el .env tiene SMTP, se usa para avisar que hay
avisos nuevos en el sistema (sin datos, solo la liga).

Lo normal es administrar las cuentas desde el panel (Usuarios, rol admin_ti).
Este script sirve para crear la primera cuenta de TI y como respaldo si TI
pierde el acceso. Todo lo que hace queda en la bitacora como
"consola:<usuario de Windows>".
"""
import argparse
import getpass

from sqlalchemy import text

from app import mfa
from app.database import engine
from app.seguridad import (
    ROLES,
    ErrorDeUsuario,
    asegurar_tabla,
    cambiar_contrasena,
    cambiar_correo,
    crear_usuario,
)


def pedir_contrasena() -> str:
    primera = getpass.getpass("Contraseña: ")
    if getpass.getpass("Repite la contraseña: ") != primera:
        raise SystemExit("Las contraseñas no coinciden.")
    return primera


POR = f"consola:{getpass.getuser()}"


def id_de_usuario(usuario: str) -> int:
    asegurar_tabla()
    with engine.connect() as conn:
        id_ = conn.execute(text("SELECT id FROM usuarios WHERE usuario = :u"), {"u": usuario.strip().lower()}).scalar()
    if id_ is None:
        raise SystemExit(f"El usuario '{usuario}' no existe")
    return id_


def id_de_area(nombre: str) -> int:
    with engine.connect() as conn:
        filas = dict(conn.execute(text("SELECT lower(nombre), id FROM areas")).all())
    if nombre.lower() not in filas:
        raise SystemExit(f"Area '{nombre}' no existe. Opciones: {', '.join(sorted(filas))}")
    return filas[nombre.lower()]


def listar():
    asegurar_tabla()
    with engine.connect() as conn:
        filas = conn.execute(
            text(
                "SELECT u.usuario, u.nombre, u.rol, a.nombre AS area, u.activo, u.ultimo_acceso, u.correo, u.mfa_activo, "
                "u.bloqueado_hasta > now() AS bloqueado "
                "FROM usuarios u LEFT JOIN areas a ON a.id = u.area_id ORDER BY u.usuario"
            )
        ).mappings().all()
    if not filas:
        print("No hay usuarios. Crea el primero con --usuario, --nombre y --rol.")
    for f in filas:
        estado = "activo" if f["activo"] else "inactivo"
        if f["bloqueado"]:
            estado += ", BLOQUEADO"
        if f["mfa_activo"]:
            estado += ", MFA"
        acceso = f["ultimo_acceso"].strftime("%Y-%m-%d %H:%M") if f["ultimo_acceso"] else "nunca"
        print(
            f"{f['usuario']:<16}{f['rol']:<11}{(f['area'] or '-'):<13}{estado:<20}ultimo acceso: {acceso}  "
            f"({f['nombre']}{', ' + f['correo'] if f['correo'] else ''})"
        )


def main():
    ap = argparse.ArgumentParser(description="Usuarios del Motor de Reportes de RRHH")
    ap.add_argument("--usuario")
    ap.add_argument("--nombre", help="nombre para mostrar")
    ap.add_argument("--rol", choices=ROLES)
    ap.add_argument("--area", help="nombre del area (solo para el rol gerente)")
    ap.add_argument("--correo", help="correo para avisos (opcional)")
    ap.add_argument("--cambiar-contrasena", action="store_true", help="cambia la contraseña y desbloquea la cuenta")
    ap.add_argument("--cambiar-correo", metavar="CORREO", help='pone el correo de un usuario ("" lo quita)')
    ap.add_argument("--reiniciar-mfa", action="store_true", help="borra su verificacion en dos pasos (telefono perdido)")
    ap.add_argument("--listar", action="store_true", help="muestra los usuarios existentes")
    args = ap.parse_args()

    try:
        if args.listar:
            listar()
        elif args.cambiar_contrasena:
            if not args.usuario:
                raise SystemExit("Indica --usuario")
            cambiar_contrasena(args.usuario, pedir_contrasena(), por=POR)
            print(f"Contraseña de '{args.usuario}' actualizada (y cuenta desbloqueada).")
        elif args.cambiar_correo is not None:
            if not args.usuario:
                raise SystemExit("Indica --usuario")
            cambiar_correo(args.usuario, args.cambiar_correo, por=POR)
            print(f"Correo de '{args.usuario}' {'actualizado' if args.cambiar_correo.strip() else 'eliminado'}.")
        elif args.reiniciar_mfa:
            if not args.usuario:
                raise SystemExit("Indica --usuario")
            mfa.reiniciar(id_de_usuario(args.usuario), POR)
            print(f"Verificación en dos pasos de '{args.usuario}' reiniciada: la configurará al entrar.")
        else:
            if not (args.usuario and args.nombre and args.rol):
                ap.error("para crear un usuario indica --usuario, --nombre y --rol")
            area_id = id_de_area(args.area) if args.area else None
            crear_usuario(args.usuario, args.nombre, args.rol, pedir_contrasena(), area_id, args.correo, por=POR)
            print(f"Usuario '{args.usuario.lower()}' creado con rol {args.rol}.")
    except ErrorDeUsuario as exc:
        raise SystemExit(f"No se pudo: {exc}")


if __name__ == "__main__":
    main()
