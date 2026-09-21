"""Modelos de respuesta de la API (validacion y documentacion OpenAPI)."""
from datetime import date

from pydantic import BaseModel, Field


class Area(BaseModel):
    id: int = Field(description="0 = consolidado corporativo")
    nombre: str


class Umbral(BaseModel):
    indicador: str
    nombre: str
    unidad: str
    sentido: str = Field(description="mayor_es_peor o menor_es_peor")
    umbral_atencion: float
    umbral_critico: float


class KpiFila(BaseModel):
    indicador: str
    nombre: str
    unidad: str
    area_id: int
    area: str
    periodo: date = Field(description="Primer dia del mes")
    valor: float | None = Field(description="null si el valor esta suprimido o no hay dato")
    n: int = Field(description="Personas o registros detras del valor")
    suprimido: bool = Field(description="True si se oculto por la regla de tamano minimo de grupo")
    var_mes_ant: float | None = None
    var_mes_ant_pct: float | None = None
    var_anio_ant: float | None = None
    var_anio_ant_pct: float | None = None
    estado: str = Field(description="verde, amarillo, rojo, suprimido o sin_dato")


class PuntoSerie(BaseModel):
    periodo: date
    valor: float | None
    n: int
    suprimido: bool
    estado: str
