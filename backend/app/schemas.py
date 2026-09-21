"""Modelos de respuesta de la API (validacion y documentacion OpenAPI)."""
from datetime import date, datetime

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
    sentido: str | None = Field(None, description="mayor_es_peor o menor_es_peor")
    umbral_atencion: float | None = None
    umbral_critico: float | None = None


class PuntoSerie(BaseModel):
    periodo: date
    valor: float | None
    n: int
    suprimido: bool
    estado: str


# ------------------------------------------------------------- narrativa
class NarrativaSolicitud(BaseModel):
    periodo: str | None = Field(
        None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="AAAA-MM. Por defecto, el ultimo mes."
    )
    area_id: int = Field(0, description="0 = consolidado corporativo")
    usar_ia: bool = Field(True, description="False = solo plantilla determinista (sin modelo)")


class HechoOut(BaseModel):
    id: str
    indicador: str
    nombre: str
    unidad: str
    area: str
    periodo: str
    valor: float
    valor_texto: str
    var_mes_ant: float | None
    var_mes_ant_texto: str | None
    var_anio_ant: float | None
    var_anio_ant_texto: str | None
    estado: str
    n: int
    umbral_atencion: float
    umbral_atencion_texto: str
    umbral_critico: float
    umbral_critico_texto: str
    sentido: str
    confianza: str = Field(description="alta, media o baja; calculada por reglas, no por el modelo")
    motivo_confianza: str
    fuente: str


class Hallazgo(BaseModel):
    titulo: str
    texto: str
    hechos: list[str] = Field(description="Ids de los hechos que respaldan el texto")
    confianza: str
    fuentes: list[str]


class Recomendacion(BaseModel):
    accion: str
    hechos: list[str]
    confianza: str
    fuentes: list[str]


class ConteoEstados(BaseModel):
    rojo: int
    amarillo: int
    verde: int
    total: int


class Narrativa(BaseModel):
    periodo: str
    area_id: int
    area: str
    origen: str = Field(description="'llm' si la redacto el modelo y paso la validacion; 'plantilla' si no")
    proveedor: str | None
    modelo: str | None
    version_prompt: str
    generado_en: datetime
    requiere_revision: bool = Field(description="Siempre True: un responsable de RRHH debe aprobarla")
    resumen: str
    hallazgos: list[Hallazgo]
    recomendaciones: list[Recomendacion]
    conteo_estados: ConteoEstados
    hechos: list[HechoOut]
    advertencias: list[str]