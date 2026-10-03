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
    estado: str = Field(
        description="verde, amarillo, rojo, suprimido, sin_dato o muestra_insuficiente "
        "(valor visible pero sin semaforo: muy pocas personas detras del dato)"
    )
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
    personas_texto: str | None = Field(None, description="Conteo en personas (tasas de capacitacion)")
    umbral_atencion: float
    umbral_atencion_texto: str
    umbral_critico: float
    umbral_critico_texto: str
    sentido: str
    evolucion_mes_ant: str | None = Field(None, description="mejoró, empeoró o sin cambio (calculado por código)")
    evolucion_anio_ant: str | None = None
    en_vigilancia: bool = Field(False, description="Verde, pero con señales de deterioro")
    motivo_vigilancia: str | None = None
    situacion: str = Field(description="Relación con los umbrales, en palabras neutras")
    accion_base: str | None = Field(None, description="Acción sugerida base (solo indicadores en alerta)")
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
    por_vigilar: int = Field(0, description="Indicadores en verde que conviene vigilar")
    total: int


class Narrativa(BaseModel):
    periodo: str
    area_id: int
    area: str
    proveedor: str = Field(description="ollama (local) o groq (nube, solo datos sinteticos)")
    modelo: str | None
    version_prompt: str
    generado_en: datetime
    requiere_revision: bool = Field(description="Siempre True: un responsable de RRHH debe aprobarla")
    mes_estable: bool = Field(description="True si no hubo alertas ni indicadores por vigilar")
    indicadores_sin_evaluar: list[str] = Field(
        [], description="Indicadores con muestra insuficiente: se ven en el dashboard, pero no generan alertas"
    )
    intentos: int = Field(description="Llamadas al modelo hasta pasar los guardarrailes")
    resumen: str
    hallazgos: list[Hallazgo]
    recomendaciones: list[Recomendacion]
    conteo_estados: ConteoEstados
    hechos: list[HechoOut]
    advertencias: list[str] = Field(description="Errores de validacion de los intentos previos")


class TrabajoNarrativa(BaseModel):
    """Solicitud de narrativa: se genera en segundo plano y se consulta por id."""
    id: int
    area_id: int
    periodo: str
    estado: str = Field(description="en_proceso, lista o error")
    solicitada_en: datetime
    terminada_en: datetime | None
    proveedor: str | None
    modelo: str | None
    version_prompt: str | None
    rondas: int = Field(description="Veces que se pidio al modelo desde cero")
    error: str | None = Field(None, description="Motivo si estado = error")
    detalle_error: list[str] | None = None
    narrativa: Narrativa | None = Field(None, description="Presente cuando estado = lista")