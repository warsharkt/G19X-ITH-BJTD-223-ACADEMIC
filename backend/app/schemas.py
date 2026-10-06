"""Modelos de respuesta de la API (validacion y documentacion OpenAPI)."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Token(BaseModel):
    """Respuesta del inicio de sesion. Con MFA activo, el primer paso NO trae
    access_token sino mfa_token: se manda con el codigo a POST /auth/mfa."""
    access_token: str | None = None
    token_type: str = "bearer"
    expira_en_minutos: int
    mfa_requerido: bool = False
    mfa_token: str | None = Field(None, description="Solo sirve para POST /auth/mfa, por unos minutos")


class UsuarioOut(BaseModel):
    id: int
    usuario: str
    nombre: str
    rol: str = Field(description="direccion, rrhh, gerente o admin_ti")
    area_id: int | None = Field(description="Solo los gerentes tienen area")
    areas_permitidas: list[int] = Field(description="Areas que puede consultar (0 = corporativo)")
    pendiente: str | None = Field(
        None, description="cambiar_contrasena o configurar_mfa: hasta resolverlo, el resto de la API da 403"
    )
    mfa_activo: bool = False
    mfa_obligatorio: bool = Field(False, description="Su rol debe usar verificacion en dos pasos")
    codigos_respaldo_restantes: int = 0


class MfaPaso(BaseModel):
    """Segundo paso del inicio de sesion."""
    mfa_token: str
    codigo: str = Field(max_length=20, description="6 digitos de la app, o un codigo de respaldo")


class MfaConfiguracion(BaseModel):
    secreto: str = Field(description="Para escribirlo a mano si no se puede escanear el QR")
    uri: str
    qr: str = Field(description="Imagen SVG del QR como data URI")


class MfaActivar(BaseModel):
    codigo: str = Field(max_length=10)


class CodigosRespaldo(BaseModel):
    codigos: list[str] = Field(description="De un solo uso. No se vuelven a mostrar")


class CambioContrasena(BaseModel):
    actual: str = Field(max_length=200)
    nueva: str = Field(max_length=200)


# ---------------------------------------------------------- cuentas (TI)
class Cuenta(BaseModel):
    id: int
    usuario: str
    nombre: str
    rol: str
    area_id: int | None
    correo: str | None
    activo: bool
    bloqueado: bool
    debe_cambiar_contrasena: bool
    mfa_activo: bool
    creado_en: datetime
    ultimo_acceso: datetime | None


class CuentaNueva(BaseModel):
    usuario: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    nombre: str = Field(min_length=1, max_length=120)
    rol: str
    area_id: int | None = None
    correo: str | None = None


class CuentaCambio(BaseModel):
    """Solo los campos que se mandan se cambian."""
    nombre: str | None = Field(None, min_length=1, max_length=120)
    rol: str | None = None
    area_id: int | None = None
    correo: str | None = None
    activo: bool | None = None


class CuentaCreada(BaseModel):
    cuenta: Cuenta
    contrasena_temporal: str = Field(description="Se muestra una sola vez; la persona la cambia al entrar")


class ContrasenaTemporal(BaseModel):
    contrasena_temporal: str = Field(description="Se muestra una sola vez; la persona la cambia al entrar")


class CambioCuenta(BaseModel):
    """Bitacora de cuentas: quien hizo que, a que cuenta y cuando."""
    id: int
    usuario: str
    accion: str
    detalle: dict
    hecho_por: str
    hecho_en: datetime


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


class UmbralCambio(BaseModel):
    """Nuevos umbrales de un indicador (solo RRHH)."""
    umbral_atencion: float
    umbral_critico: float


class CambioUmbral(BaseModel):
    """Bitacora: quien cambio un umbral, cuando y de que valores a cuales."""
    id: int
    indicador: str
    nombre: str
    unidad: str
    atencion_antes: float
    critico_antes: float
    atencion_nuevo: float
    critico_nuevo: float
    usuario: str
    cambiado_en: datetime


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
    area_id: int | None = Field(
        None, description="0 = consolidado corporativo. Por defecto: tu area si eres gerente, si no el 0."
    )


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
    solicitada_por: str | None = Field(None, description="Usuario que la solicito (bitacora RF-11)")
    revision: str = Field(
        "pendiente", description="pendiente, aprobada o rechazada (RF-05). Solo aplica si estado = lista"
    )
    revisada_por: str | None = Field(None, description="Usuario que la aprobo o rechazo (bitacora RF-11)")
    revisada_en: datetime | None = None
    comentario_revision: str | None = None
    programada: bool = Field(False, description="La solicito la programacion mensual, no una persona")
    narrativa: Narrativa | None = Field(None, description="Presente cuando estado = lista")


class RevisionSolicitud(BaseModel):
    """Decision de RRHH sobre una narrativa lista (RF-05)."""
    decision: Literal["aprobada", "rechazada"]
    comentario: str | None = Field(
        None, max_length=1000, description="Obligatorio al rechazar: que hay que corregir"
    )

    @model_validator(mode="after")
    def _rechazo_con_motivo(self):
        self.comentario = (self.comentario or "").strip() or None
        if self.decision == "rechazada" and (self.comentario is None or len(self.comentario) < 10):
            raise ValueError("Al rechazar, explica el motivo en el comentario (mínimo 10 caracteres)")
        return self

# ------------------------------------------------------------ paso 10
class Aviso(BaseModel):
    id: int
    tipo: str = Field(description="alerta, revision, aprobado, rechazado o error")
    area_id: int
    titulo: str
    enlace: str = Field(description="Ruta del tablero a la que lleva el aviso")
    creado_en: datetime
    leido_en: datetime | None


class Avisos(BaseModel):
    no_leidos: int
    avisos: list[Aviso]


class Corrida(BaseModel):
    periodo: str = Field(description="Mes reportado, AAAA-MM")
    iniciada_en: datetime
    origen: str = Field(description="api o script")
    narrativas: int = Field(description="Reportes que se solicitaron")


class Programacion(BaseModel):
    activa: bool
    dia_del_mes: int = Field(description="A partir de este dia se generan los reportes del mes cerrado")
    modificada_por: str | None
    modificada_en: datetime | None
    correo_activo: bool = Field(description="True si el servidor tiene SMTP para avisar por correo")
    corridas: list[Corrida]


class ProgramacionCambio(BaseModel):
    """Configuracion de la programacion mensual (solo RRHH)."""
    activa: bool
    dia_del_mes: int = Field(ge=1, le=28, description="1 a 28: todos los meses tienen ese dia")


# -------------------------------------------------------- modo demostracion
class CuentaDemo(BaseModel):
    usuario: str
    nombre: str
    rol: str
    descripcion: str


class Demo(BaseModel):
    activo: bool
    contrasena: str | None = Field(None, description="Contrasena de las cuentas de demostracion")
    cuentas: list[CuentaDemo] = []


class CodigoDemo(BaseModel):
    codigo: str = Field(description="El codigo que en produccion solo se veria en la app del telefono")
    segundos: int = Field(description="Segundos para que cambie")


class CodigoDemoSolicitud(BaseModel):
    mfa_token: str


# ------------------------------------------------------- carga de datos
class Carga(BaseModel):
    """Un archivo subido: su validacion y, si se aplico, su conciliacion."""
    id: int
    fuente: str
    archivo: str
    sha256: str = Field(description="Huella del archivo: prueba que se cargo exactamente ese")
    bytes: int
    filas: int
    estado: str = Field(description="validada, con_errores, aplicada o descartada")
    errores: list[dict]
    descartadas: list[dict] = Field(description="Columnas que no se guardaron y por que")
    periodos: list[str]
    resultado: dict | None
    subida_por: str
    subida_en: datetime
    aplicada_por: str | None
    aplicada_en: datetime | None
