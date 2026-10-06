"""Crea o restablece las cuentas del modo demostracion.

Requiere en el .env MODO_DEMO=si y MODO_DATOS=sinteticos (se niega con datos
reales). Deja cada cuenta como nueva: contrasena de demostracion, activa,
desbloqueada y sin verificacion en dos pasos, para que quien revise vea como se
configura. Correrlo otra vez restablece las cuentas despues de una revision.

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
    print(f"\nContraseña de todas las cuentas: {demo.contrasena()}")
    print("Dirección, RRHH y TI configurarán la verificación en dos pasos al entrar;")
    print("un teléfono simulado en pantalla muestra el código que daría la app del celular.")


if __name__ == "__main__":
    main()
