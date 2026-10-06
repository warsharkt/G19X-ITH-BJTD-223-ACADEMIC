"""Revisa la programacion mensual y genera los reportes que falten (RF-07).

Hace lo mismo que la API cada hora (app/programacion.py): avisa los
indicadores en rojo del ultimo mes cerrado y, si la programacion esta activa
y ya llego el dia, solicita los reportes de ese mes. Es idempotente: si la API
o una corrida anterior ya los genero, no hace nada.

Sirve para que los reportes salgan aunque la API no este encendida. Espera a
que terminen (en CPU, minutos por reporte), asi que no reinicies la API
mientras corre: al arrancar, la API marca como interrumpido lo que estaba
"en_proceso".

Uso (desde la carpeta backend, con el entorno virtual activo):
    python -m scripts.programar           # revisa y genera lo que falte
    python -m scripts.programar --ver     # solo muestra la configuracion

Programador de tareas de Windows, todos los dias a las 7:00 (cambia la ruta):
    schtasks /create /tn "Motor RRHH" /sc daily /st 07:00 /tr "cmd /c cd /d C:\\ruta\\backend && .venv\\Scripts\\python.exe -m scripts.programar"
"""
import argparse

from app import avisos, programacion, trabajos


def ver():
    conf = programacion.leer()
    estado = "ACTIVA" if conf["activa"] else "desactivada"
    print(f"Programación mensual: {estado}; se genera a partir del día {conf['dia_del_mes']} de cada mes.")
    if conf["modificada_por"]:
        print(f"Último cambio: {conf['modificada_por']}, {conf['modificada_en']:%Y-%m-%d %H:%M}")
    print(f"Correo de avisos: {'activo' if avisos.configuracion_smtp() else 'apagado (sin SMTP_HOST en el .env)'}")
    corridas = programacion.corridas()
    if not corridas:
        print("Todavía no se ha generado ningún mes.")
    for c in corridas:
        print(f"  {c['periodo']}: {c['narrativas']} reportes, {c['iniciada_en']:%Y-%m-%d %H:%M} ({c['origen']})")


def main():
    ap = argparse.ArgumentParser(description="Programación mensual de reportes de RRHH")
    ap.add_argument("--ver", action="store_true", help="solo muestra la configuración y los meses generados")
    args = ap.parse_args()
    if args.ver:
        ver()
        return

    resultado = programacion.revisar(origen="script")
    if resultado["alertas"]:
        print(f"Avisos nuevos de indicadores en rojo: {resultado['alertas']}")
    print(resultado["mensaje"])
    if resultado["narrativas"]:
        print("Generando en este equipo (puede tardar varios minutos por reporte)…")
    trabajos.ejecutor.shutdown(wait=True)  # termina las narrativas y sus avisos
    for id_ in resultado["narrativas"]:
        t = trabajos.obtener(id_)
        print(f"  #{id_} área {t['area_id']}: {t['estado']}{' - ' + t['error'] if t['error'] else ''}")
    avisos.enviar_correos()  # lo que haya quedado pendiente, antes de salir
    avisos.ejecutor_correo.shutdown(wait=True)


if __name__ == "__main__":
    main()
