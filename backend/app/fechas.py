"""La fecha de hoy en la empresa. El contenedor corre en UTC: con date.today(),
una suplencia terminaba a las 18:00 de Mexico de su ultimo dia."""
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo


def hoy() -> date:
    return datetime.now(ZoneInfo(os.getenv("ZONA_HORARIA", "America/Mexico_City"))).date()
