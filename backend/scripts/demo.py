"""Crea o restablece las cuentas del personal de Nordika (modo demostracion).

Requiere en el .env MODO_DEMO=si y MODO_DATOS=sinteticos (se niega con datos
reales). Deja cada cuenta como nueva: contrasena inicial, activa,
desbloqueada y sin verificacion en dos pasos, para que quien revise vea como se
configura. Correrlo otra vez restablece las cuentas despues de una revision.
Las cuentas demo_* de versiones anteriores se renombran (eva.munoz, ana.rios...).

Uso (desde la carpeta backend, con el entorno virtual activo):
    python -m scripts.demo
"""
import getpass

from app import demo
from app.seguridad import ErrorDeUsuario


def main():
    try:
        hecho = demo.preparar_cuentas(por=f"consola:{getpass.getuser()}")
    except ErrorDeUsuario as exc:
        raise SystemExit(f"No se pudo: {exc}")
    for linea in hecho:
        print(linea)
    print("\nCuentas (la pantalla de inicio no las muestra; están en el README):")
    for usuario, nombre, *_, cargo, _que_hace in demo.CUENTAS:
        print(f"  {usuario:<16}{nombre}, {cargo}")
    print(f"\nContraseña de todas las cuentas: {demo.contrasena()}")
    print("Dirección, RRHH y TI configurarán la verificación en dos pasos al entrar;")
    print("un teléfono simulado en pantalla muestra el código que daría la app del celular.")


if __name__ == "__main__":
    main()
