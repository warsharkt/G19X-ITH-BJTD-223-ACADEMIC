"""Desde donde llega la peticion (IP), para las bitacoras.

La pone el middleware de app/main.py en cada peticion; detras de nginx es la
IP real de quien usa el tablero (X-Forwarded-For, ver scripts/arranque.py).
Fuera de una peticion (scripts, programacion mensual) vale None.
"""
from contextvars import ContextVar

actual: ContextVar[str | None] = ContextVar("origen", default=None)
