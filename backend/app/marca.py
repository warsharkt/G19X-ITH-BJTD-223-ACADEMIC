"""Nombre del producto y de la empresa que lo usa.

El producto es Talentia Insights. La empresa cliente se configura en el .env
(EMPRESA_NOMBRE), asi el mismo producto se presenta a otra empresa sin tocar
el codigo. En la demostracion es Nordika Logistica, una empresa ficticia.
"""
import os

PRODUCTO = "Talentia Insights"


def empresa() -> str:
    return os.getenv("EMPRESA_NOMBRE", "").strip() or "Nordika Logística"


def pie_confidencial() -> str:
    """Pie de los reportes exportados."""
    return f"Confidencial: uso interno de {empresa()} · {PRODUCTO}"
