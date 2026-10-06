"""Carga de datos desde los sistemas fuente de RRHH (hito 11, RF-01).

RRHH sube el archivo que exporta cada sistema (CSV o Excel). Dos pasos:

1. validar(): lee el archivo completo y revisa cada fila (tipos, fechas,
   areas y empleados que existan, reglas como "logradas <= asignadas",
   duplicados). Muestra una vista previa y que se agregara o actualizara.
2. aplicar(): solo si no hubo NINGUN error (todo o nada: un archivo a
   medias dejaria indicadores inconsistentes). Despues concilia: compara lo
   que decia el archivo con lo que quedo en la base.

Seguridad y privacidad:
  - Solo se guardan las columnas que necesita cada indicador. Las demas se
    descartan sin guardarse; si parecen datos personales (nombre, CURP,
    RFC, correo...) se avisa. El sistema solo conoce codigos de empleado.
  - Limite de tamano y solo .csv o .xlsx.
  - Cada carga queda en la tabla `cargas`: quien, cuando, archivo, huella
    SHA-256, filas, columnas descartadas y conciliacion.

ejemplo() genera los archivos del mes siguiente para la empresa de
demostracion, consistentes entre si y con lo que ya hay en la base.
"""
import calendar
import hashlib
import io
import json
import math
import random
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import text

from app.database import ejecutar_sql, engine
from app.narrativa import MESES_ES

BYTES_MAXIMOS = 5 * 1024 * 1024
EXTENSIONES = (".csv", ".xlsx")
ERRORES_MOSTRADOS = 100
FILAS_DE_MUESTRA = 8

# Columnas que nunca se guardan: datos personales. Se descartan y se avisa.
PERSONALES = {
    "nombre", "nombres", "apellido", "apellidos", "apellido_paterno", "apellido_materno", "nombre_completo",
    "curp", "rfc", "nss", "imss", "correo", "email", "correo_electronico", "telefono", "celular", "domicilio",
    "direccion", "fecha_nacimiento", "edad", "sexo", "genero", "salario", "sueldo", "cuenta_bancaria", "clabe",
}


class ErrorDeCarga(ValueError):
    """El archivo no se puede leer o la operacion no aplica."""


# ------------------------------------------------------------ definicion
@dataclass(frozen=True)
class Columna:
    nombre: str
    tipo: str  # texto, fecha, mes, entero, numero, area, empleado, opcion, si_no
    requerida: bool = True
    minimo: float | None = None
    maximo: float | None = None
    opciones: tuple = ()
    ayuda: str = ""


@dataclass(frozen=True)
class Fuente:
    clave: str
    nombre: str
    sistema: str
    descripcion: str
    columnas: tuple
    llave: tuple = field(default=())  # columnas que no se pueden repetir en el archivo


FUENTES = {
    f.clave: f
    for f in (
        Fuente(
            "hris", "Plantilla de personal", "HRIS / Nómina",
            "Altas y bajas de cada colaborador. Se carga primero: las demás fuentes se refieren a sus códigos.",
            (
                Columna("codigo", "texto", ayuda="Código de empleado (nunca el nombre)"),
                Columna("area", "area"),
                Columna("fecha_ingreso", "fecha"),
                Columna("fecha_baja", "fecha", requerida=False, ayuda="Vacía si sigue activo"),
                Columna("tipo_baja", "opcion", requerida=False, opciones=("voluntaria", "involuntaria")),
            ),
            ("codigo",),
        ),
        Fuente(
            "ats", "Vacantes", "ATS (reclutamiento)",
            "Vacantes abiertas y cubiertas, con su costo. El folio evita duplicarlas al volver a cargar.",
            (
                Columna("folio", "texto"),
                Columna("area", "area"),
                Columna("fecha_apertura", "fecha"),
                Columna("fecha_contratacion", "fecha", requerida=False, ayuda="Vacía si sigue abierta"),
                Columna("costo_proceso", "numero", minimo=0, ayuda="MXN"),
            ),
            ("folio",),
        ),
        Fuente(
            "desempeno", "Metas de desempeño", "Sistema de desempeño",
            "Metas asignadas y logradas por colaborador y mes.",
            (
                Columna("codigo_empleado", "empleado"),
                Columna("periodo", "mes", ayuda="AAAA-MM"),
                Columna("metas_asignadas", "entero", minimo=1),
                Columna("metas_logradas", "entero", minimo=0),
                Columna("calificacion", "entero", minimo=1, maximo=5),
            ),
            ("codigo_empleado", "periodo"),
        ),
        Fuente(
            "capacitacion", "Capacitación", "LMS",
            "Inscripciones a programas de capacitación y si se completaron.",
            (
                Columna("programa", "texto"),
                Columna("periodo", "mes", ayuda="AAAA-MM"),
                Columna("horas_programa", "numero", minimo=0.5),
                Columna("area_programa", "area", requerida=False, ayuda="Vacía si es para toda la empresa"),
                Columna("codigo_empleado", "empleado"),
                Columna("completado", "si_no"),
                Columna("horas_cursadas", "numero", minimo=0),
            ),
            ("programa", "periodo", "area_programa", "codigo_empleado"),
        ),
        Fuente(
            "clima", "Encuesta de clima", "Encuestas (respuestas anónimas)",
            "Respuestas anónimas por área y mes: sin código de empleado. Reemplaza la encuesta de ese mes.",
            (
                Columna("area", "area"),
                Columna("periodo", "mes", ayuda="AAAA-MM"),
                Columna("dimension", "opcion", opciones=("enps", "satisfaccion", "liderazgo", "carga_trabajo")),
                Columna("puntaje", "entero", minimo=0, maximo=10),
            ),
        ),
        Fuente(
            "productividad", "Productividad", "Sistema de proyectos y tickets",
            "Horas efectivas y disponibles, y entregables, por área y mes.",
            (
                Columna("area", "area"),
                Columna("periodo", "mes", ayuda="AAAA-MM"),
                Columna("horas_efectivas", "numero", minimo=0),
                Columna("horas_disponibles", "numero", minimo=1),
                Columna("entregables_planificados", "entero", minimo=0),
                Columna("entregables_completados", "entero", minimo=0),
            ),
            ("area", "periodo"),
        ),
    )
}

# Reglas entre columnas de una misma fila: (condicion de error, mensaje)
REGLAS = {
    "hris": [
        (lambda f: (f["fecha_baja"] is None) != (f["tipo_baja"] is None),
         "fecha_baja y tipo_baja van juntas: las dos llenas o las dos vacías"),
        (lambda f: f["fecha_baja"] is not None and f["fecha_baja"] < f["fecha_ingreso"],
         "La fecha de baja es anterior a la de ingreso"),
    ],
    "ats": [(lambda f: f["fecha_contratacion"] is not None and f["fecha_contratacion"] < f["fecha_apertura"],
             "La vacante se cubrió antes de abrirse")],
    "desempeno": [(lambda f: f["metas_logradas"] > f["metas_asignadas"], "Hay más metas logradas que asignadas")],
    "capacitacion": [(lambda f: f["horas_cursadas"] > f["horas_programa"], "Se cursaron más horas de las que tiene el programa")],
    "productividad": [
        (lambda f: f["horas_efectivas"] > f["horas_disponibles"], "Hay más horas efectivas que disponibles"),
        (lambda f: f["entregables_completados"] > f["entregables_planificados"], "Hay más entregables completados que planificados"),
    ],
}


def catalogo() -> list[dict]:
    """Fuentes y sus columnas, para la pantalla y las plantillas."""
    return [
        {
            "clave": f.clave, "nombre": f.nombre, "sistema": f.sistema, "descripcion": f.descripcion,
            "columnas": [{"nombre": c.nombre, "requerida": c.requerida, "ayuda": c.ayuda} for c in f.columnas],
        }
        for f in FUENTES.values()
    ]


def _fuente(clave: str) -> Fuente:
    if clave not in FUENTES:
        raise LookupError(f"La fuente '{clave}' no existe. Opciones: {', '.join(FUENTES)}")
    return FUENTES[clave]


def asegurar_tabla():
    # Sin cache: el seed recrea `vacantes` y se llevaria la columna folio.
    ejecutar_sql("cargas.sql")


# ---------------------------------------------------------------- lectura
def _clave(texto: str) -> str:
    """'Fecha de Ingreso ' -> 'fecha_de_ingreso' (sin acentos ni mayusculas)."""
    sin_acentos = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return "_".join(sin_acentos.strip().lower().replace("-", " ").split())


def leer_archivo(nombre: str, contenido: bytes) -> pd.DataFrame:
    extension = ("." + nombre.rsplit(".", 1)[-1].lower()) if "." in nombre else ""
    if extension not in EXTENSIONES:
        raise ErrorDeCarga("Solo se aceptan archivos .csv o .xlsx (Excel)")
    if len(contenido) > BYTES_MAXIMOS:
        raise ErrorDeCarga(f"El archivo pesa más de {BYTES_MAXIMOS // (1024 * 1024)} MB")
    if not contenido:
        raise ErrorDeCarga("El archivo está vacío")
    try:
        if extension == ".xlsx":
            df = pd.read_excel(io.BytesIO(contenido), dtype=object, engine="openpyxl")
        else:
            try:
                texto = contenido.decode("utf-8-sig")
            except UnicodeDecodeError:
                texto = contenido.decode("latin-1")
            df = pd.read_csv(io.StringIO(texto), dtype=str, sep=None, engine="python", keep_default_na=False)
    except ErrorDeCarga:
        raise
    except Exception as exc:
        raise ErrorDeCarga(f"No se pudo leer el archivo: {exc}")
    columnas = [_clave(c) for c in df.columns]
    # vacio, NaN o NaT (fecha vacia en Excel) -> None. dtype=object: si no,
    # pandas vuelve a inferir fechas y convierte los None otra vez en NaT.
    filas = [
        [None if v is None or pd.isna(v) or str(v).strip() == "" else v for v in fila]
        for fila in df.itertuples(index=False, name=None)
    ]
    df = pd.DataFrame(filas, columns=columnas, dtype=object)
    return df.dropna(how="all").reset_index(drop=True)


# ------------------------------------------------------------- validacion
def _hoy() -> date:
    return date.today()


def _texto(v) -> str:
    return str(v).strip()


def _a_fecha(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _texto(v)[:10]
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, formato).date()
        except ValueError:
            pass
    raise ValueError("no es una fecha (usa AAAA-MM-DD o DD/MM/AAAA)")


def _a_mes(v) -> date:
    if isinstance(v, (datetime, date)):
        d = v.date() if isinstance(v, datetime) else v
        return d.replace(day=1)
    s = _texto(v)
    try:
        return datetime.strptime(s[:7], "%Y-%m").date()
    except ValueError:
        raise ValueError("no es un mes (usa AAAA-MM)")


def _a_numero(v) -> float:
    try:
        n = float(_texto(v).replace(",", "")) if not isinstance(v, (int, float)) else float(v)
    except ValueError:
        raise ValueError("no es un número")
    if not math.isfinite(n):
        raise ValueError("no es un número")
    return n


def _a_entero(v) -> int:
    n = _a_numero(v)
    if n != int(n):
        raise ValueError("debe ser un número entero")
    return int(n)


_SI = {"si", "s", "1", "true", "verdadero", "x"}
_NO = {"no", "n", "0", "false", "falso"}


def _convertir(c: Columna, v, contexto: dict):
    """Valor ya convertido (ids para area y empleado); ValueError con el motivo."""
    if c.tipo == "texto":
        s = _texto(v)
        if len(s) > 120:
            raise ValueError("es demasiado largo (máximo 120 caracteres)")
        return s
    if c.tipo == "fecha":
        d = _a_fecha(v)
        if d > _hoy():
            raise ValueError("es una fecha futura")
        if d.year < 1950:
            raise ValueError("es una fecha demasiado antigua")
        return d
    if c.tipo == "mes":
        d = _a_mes(v)
        if d > _hoy().replace(day=1):
            raise ValueError("es un mes futuro")
        return d
    if c.tipo in ("entero", "numero"):
        n = _a_entero(v) if c.tipo == "entero" else _a_numero(v)
        if c.minimo is not None and n < c.minimo:
            raise ValueError(f"debe ser al menos {c.minimo:g}")
        if c.maximo is not None and n > c.maximo:
            raise ValueError(f"debe ser como máximo {c.maximo:g}")
        return n
    if c.tipo == "area":
        id_ = contexto["areas"].get(_clave(v))
        if id_ is None:
            raise ValueError(f"el área '{_texto(v)}' no existe. Áreas: {', '.join(contexto['nombres_area'])}")
        return id_
    if c.tipo == "empleado":
        id_ = contexto["empleados"].get(_texto(v).upper())
        if id_ is None:
            raise ValueError(f"el empleado '{_texto(v)}' no existe: carga primero la plantilla de personal (HRIS)")
        return id_
    if c.tipo == "opcion":
        s = _clave(v)
        if s not in c.opciones:
            raise ValueError(f"debe ser una de: {', '.join(c.opciones)}")
        return s
    if c.tipo == "si_no":
        s = _clave(v)
        if s in _SI:
            return True
        if s in _NO:
            return False
        raise ValueError("debe ser sí o no")
    raise AssertionError(c.tipo)


def _contexto(conn, fuente: Fuente) -> dict:
    filas = conn.execute(text("SELECT id, nombre FROM areas ORDER BY nombre")).all()
    ctx = {"areas": {_clave(n): i for i, n in filas}, "nombres_area": [n for _, n in filas], "empleados": {}}
    if any(c.tipo == "empleado" for c in fuente.columnas):
        ctx["empleados"] = {c.upper(): i for i, c in conn.execute(text("SELECT id, codigo FROM empleados"))}
    return ctx


def _validar_filas(fuente: Fuente, df: pd.DataFrame, ctx: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """(filas convertidas, errores, muestra legible)."""
    filas, errores, vistas = [], [], set()
    for i, original in df.iterrows():
        numero = int(i) + 2  # fila 1 = encabezados, como en Excel
        fila, ok = {}, True
        for c in fuente.columnas:
            v = original.get(c.nombre)
            if v is None:
                if c.requerida:
                    errores.append({"fila": numero, "columna": c.nombre, "mensaje": "está vacía"})
                    ok = False
                fila[c.nombre] = None
                continue
            try:
                fila[c.nombre] = _convertir(c, v, ctx)
            except ValueError as exc:
                errores.append({"fila": numero, "columna": c.nombre, "mensaje": f"'{_texto(v)}' {exc}"})
                ok = False
        if not ok:
            continue
        for regla, mensaje in REGLAS.get(fuente.clave, []):
            if regla(fila):
                errores.append({"fila": numero, "columna": None, "mensaje": mensaje})
                ok = False
        if ok and fuente.llave:
            llave = tuple(fila[c] for c in fuente.llave)
            if llave in vistas:
                errores.append({"fila": numero, "columna": None,
                                "mensaje": f"Registro repetido en el archivo ({', '.join(fuente.llave)})"})
                ok = False
            vistas.add(llave)
        if ok:
            filas.append(fila)
    # Solo las columnas que se guardan: la muestra nunca enseña ni guarda las
    # descartadas. Columnas y filas por separado: JSONB no conserva el orden de las llaves.
    esperadas = [c.nombre for c in fuente.columnas if c.nombre in df.columns]
    muestra = {
        "columnas": esperadas,
        "filas": [
            [None if v is None else str(v)[:10] if isinstance(v, datetime) else str(v) for v in fila]
            for fila in df[esperadas].head(FILAS_DE_MUESTRA).itertuples(index=False, name=None)
        ],
    }
    return filas, errores, muestra


def _a_json(filas: list[dict]) -> list[dict]:
    return [{k: (v.isoformat() if isinstance(v, date) else v) for k, v in f.items()} for f in filas]


def _de_json(filas: list[dict], fuente: Fuente) -> list[dict]:
    fechas = {c.nombre for c in fuente.columnas if c.tipo in ("fecha", "mes")}
    return [{k: (date.fromisoformat(v) if k in fechas and v else v) for k, v in f.items()} for f in filas]


def _nombre_mes(d: date) -> str:
    return f"{MESES_ES[d.month - 1]} {d.year}"


def _periodos(fuente: Fuente, filas: list[dict]) -> list[str]:
    meses = set()
    for f in filas:
        for c in fuente.columnas:
            if c.tipo in ("fecha", "mes") and f.get(c.nombre):
                meses.add(f[c.nombre].replace(day=1))
    if fuente.clave == "hris":  # la plantilla trae ingresos de hace anios: importan altas y bajas recientes
        return []
    return [d.strftime("%Y-%m") for d in sorted(meses)]


def _existentes(conn, fuente: Fuente, filas: list[dict]) -> int:
    """Cuantas filas del archivo ya estan en la base (se actualizarian)."""
    if not filas:
        return 0
    if fuente.clave == "hris":
        return conn.execute(text("SELECT COUNT(*) FROM empleados WHERE codigo = ANY(:c)"),
                            {"c": [f["codigo"] for f in filas]}).scalar_one()
    if fuente.clave == "ats":
        return conn.execute(text("SELECT COUNT(*) FROM vacantes WHERE folio = ANY(:c)"),
                            {"c": [f["folio"] for f in filas]}).scalar_one()
    if fuente.clave == "desempeno":
        return conn.execute(
            text("SELECT COUNT(*) FROM metas_desempeno m JOIN unnest(CAST(:e AS int[]), CAST(:p AS date[])) AS x(e, p) "
                 "ON m.empleado_id = x.e AND m.periodo = x.p"),
            {"e": [f["codigo_empleado"] for f in filas], "p": [f["periodo"] for f in filas]},
        ).scalar_one()
    if fuente.clave == "productividad":
        return conn.execute(
            text("SELECT COUNT(*) FROM productividad t JOIN unnest(CAST(:a AS int[]), CAST(:p AS date[])) AS x(a, p) "
                 "ON t.area_id = x.a AND t.periodo = x.p"),
            {"a": [f["area"] for f in filas], "p": [f["periodo"] for f in filas]},
        ).scalar_one()
    if fuente.clave == "clima":
        pares = {(f["area"], f["periodo"]) for f in filas}
        return conn.execute(
            text("SELECT COUNT(*) FROM respuestas_clima r JOIN unnest(CAST(:a AS int[]), CAST(:p AS date[])) AS x(a, p) "
                 "ON r.area_id = x.a AND r.periodo = x.p"),
            {"a": [a for a, _ in pares], "p": [p for _, p in pares]},
        ).scalar_one()
    return 0  # capacitacion: se calcula al aplicar


def validar(clave_fuente: str, archivo: str, contenido: bytes, usuario: str) -> dict:
    """Lee y valida el archivo completo. Lo registra como 'validada' (lista
    para aplicar) o 'con_errores' (no se puede aplicar)."""
    fuente = _fuente(clave_fuente)
    asegurar_tabla()
    df = leer_archivo(archivo, contenido)
    columnas = set(df.columns)
    faltan = [c.nombre for c in fuente.columnas if c.requerida and c.nombre not in columnas]
    esperadas = {c.nombre for c in fuente.columnas}
    descartadas = [
        {"columna": c, "motivo": "dato personal: no se guarda" if c in PERSONALES else "no la usa ningún indicador"}
        for c in df.columns if c not in esperadas
    ]
    with engine.connect() as conn:
        if faltan:
            filas, muestra = [], {"columnas": [], "filas": []}
            errores = [{"fila": None, "columna": c, "mensaje": "Falta esta columna en el archivo"} for c in faltan]
        elif df.empty:
            filas, muestra = [], {"columnas": [], "filas": []}
            errores = [{"fila": None, "columna": None, "mensaje": "El archivo no tiene filas"}]
        else:
            filas, errores, muestra = _validar_filas(fuente, df, _contexto(conn, fuente))
        existentes = 0 if errores else _existentes(conn, fuente, filas)

    estado = "con_errores" if errores else "validada"
    resumen = {"filas": len(df), "validas": len(filas), "existentes": existentes,
               "nuevas": len(filas) - existentes if fuente.clave != "clima" else len(filas)}
    with engine.begin() as conn:
        id_ = conn.execute(
            text(
                "INSERT INTO cargas (fuente, archivo, sha256, bytes, filas, estado, errores, descartadas, periodos, "
                "datos, resultado, subida_por) VALUES (:f, :a, :h, :b, :n, :e, CAST(:err AS jsonb), "
                "CAST(:d AS jsonb), CAST(:p AS jsonb), CAST(:datos AS jsonb), CAST(:r AS jsonb), :u) RETURNING id"
            ),
            {
                "f": fuente.clave, "a": archivo[:200], "h": hashlib.sha256(contenido).hexdigest(), "b": len(contenido),
                "n": len(df), "e": estado, "err": json.dumps(errores[:ERRORES_MOSTRADOS], ensure_ascii=False),
                "d": json.dumps(descartadas, ensure_ascii=False),
                "p": json.dumps(_periodos(fuente, filas)),
                "datos": None if errores else json.dumps(_a_json(filas), ensure_ascii=False),
                "r": json.dumps({"previo": resumen, "errores_totales": len(errores), "muestra": muestra}, ensure_ascii=False),
                "u": usuario,
            },
        ).scalar_one()
    return obtener(id_)


# ---------------------------------------------------------------- aplicar
def _aplicar_hris(conn, filas):
    nuevas = 0
    for f in filas:
        nuevas += conn.execute(
            text(
                "INSERT INTO empleados (codigo, area_id, fecha_ingreso, fecha_baja, tipo_baja) "
                "VALUES (:codigo, :area, :fecha_ingreso, :fecha_baja, :tipo_baja) "
                "ON CONFLICT (codigo) DO UPDATE SET area_id = EXCLUDED.area_id, fecha_ingreso = EXCLUDED.fecha_ingreso, "
                "fecha_baja = EXCLUDED.fecha_baja, tipo_baja = EXCLUDED.tipo_baja RETURNING (xmax = 0)"
            ),
            f,
        ).scalar_one()
    codigos = [f["codigo"] for f in filas]
    base = conn.execute(
        text("SELECT COUNT(*), COUNT(*) FILTER (WHERE fecha_baja IS NOT NULL) FROM empleados WHERE codigo = ANY(:c)"),
        {"c": codigos},
    ).one()
    conciliacion = [
        {"concepto": "Colaboradores", "archivo": len(filas), "base": base[0]},
        {"concepto": "Bajas registradas", "archivo": sum(f["fecha_baja"] is not None for f in filas), "base": base[1]},
    ]
    return nuevas, conciliacion


def _aplicar_ats(conn, filas):
    nuevas = 0
    for f in filas:
        nuevas += conn.execute(
            text(
                "INSERT INTO vacantes (folio, area_id, fecha_apertura, fecha_contratacion, costo_proceso) "
                "VALUES (:folio, :area, :fecha_apertura, :fecha_contratacion, :costo_proceso) "
                "ON CONFLICT (folio) DO UPDATE SET area_id = EXCLUDED.area_id, fecha_apertura = EXCLUDED.fecha_apertura, "
                "fecha_contratacion = EXCLUDED.fecha_contratacion, costo_proceso = EXCLUDED.costo_proceso "
                "RETURNING (xmax = 0)"
            ),
            f,
        ).scalar_one()
    base = conn.execute(
        text("SELECT COUNT(*), COALESCE(SUM(costo_proceso), 0)::float8 FROM vacantes WHERE folio = ANY(:c)"),
        {"c": [f["folio"] for f in filas]},
    ).one()
    conciliacion = [
        {"concepto": "Vacantes", "archivo": len(filas), "base": base[0]},
        {"concepto": "Costo total (MXN)", "archivo": round(sum(f["costo_proceso"] for f in filas), 2), "base": round(base[1], 2)},
    ]
    return nuevas, conciliacion


def _aplicar_desempeno(conn, filas):
    nuevas = 0
    for f in filas:
        nuevas += conn.execute(
            text(
                "INSERT INTO metas_desempeno (empleado_id, periodo, metas_asignadas, metas_logradas, calificacion) "
                "VALUES (:codigo_empleado, :periodo, :metas_asignadas, :metas_logradas, :calificacion) "
                "ON CONFLICT (empleado_id, periodo) DO UPDATE SET metas_asignadas = EXCLUDED.metas_asignadas, "
                "metas_logradas = EXCLUDED.metas_logradas, calificacion = EXCLUDED.calificacion RETURNING (xmax = 0)"
            ),
            f,
        ).scalar_one()
    base = conn.execute(
        text("SELECT COUNT(*), COALESCE(SUM(m.metas_logradas), 0) FROM metas_desempeno m "
             "JOIN unnest(CAST(:e AS int[]), CAST(:p AS date[])) AS x(e, p) ON m.empleado_id = x.e AND m.periodo = x.p"),
        {"e": [f["codigo_empleado"] for f in filas], "p": [f["periodo"] for f in filas]},
    ).one()
    conciliacion = [
        {"concepto": "Evaluaciones", "archivo": len(filas), "base": base[0]},
        {"concepto": "Metas logradas", "archivo": sum(f["metas_logradas"] for f in filas), "base": base[1]},
    ]
    return nuevas, conciliacion


def _aplicar_capacitacion(conn, filas):
    programas, nuevas = {}, 0
    for f in filas:
        llave = (f["programa"], f["periodo"], f["area_programa"])
        if llave not in programas:
            id_ = conn.execute(
                text("SELECT id FROM programas_capacitacion WHERE nombre = :n AND periodo = :p "
                     "AND area_id IS NOT DISTINCT FROM :a"),
                {"n": f["programa"], "p": f["periodo"], "a": f["area_programa"]},
            ).scalar()
            if id_ is None:
                id_ = conn.execute(
                    text("INSERT INTO programas_capacitacion (nombre, horas, periodo, area_id) "
                         "VALUES (:n, :h, :p, :a) RETURNING id"),
                    {"n": f["programa"], "h": f["horas_programa"], "p": f["periodo"], "a": f["area_programa"]},
                ).scalar_one()
            else:
                conn.execute(text("UPDATE programas_capacitacion SET horas = :h WHERE id = :i"),
                             {"h": f["horas_programa"], "i": id_})
            programas[llave] = id_
        nuevas += conn.execute(
            text(
                "INSERT INTO inscripciones_capacitacion (programa_id, empleado_id, completado, horas_cursadas) "
                "VALUES (:p, :e, :c, :h) ON CONFLICT (programa_id, empleado_id) DO UPDATE SET "
                "completado = EXCLUDED.completado, horas_cursadas = EXCLUDED.horas_cursadas RETURNING (xmax = 0)"
            ),
            {"p": programas[llave], "e": f["codigo_empleado"], "c": f["completado"], "h": f["horas_cursadas"]},
        ).scalar_one()
    base = conn.execute(
        text("SELECT COUNT(*), COUNT(*) FILTER (WHERE completado) FROM inscripciones_capacitacion "
             "WHERE programa_id = ANY(:p)"),
        {"p": list(programas.values())},
    ).one()
    conciliacion = [
        {"concepto": "Inscripciones", "archivo": len(filas), "base": base[0]},
        {"concepto": "Cursos completados", "archivo": sum(f["completado"] for f in filas), "base": base[1]},
    ]
    return nuevas, conciliacion


def _aplicar_clima(conn, filas):
    """Una encuesta por area y mes: la nueva reemplaza a la anterior."""
    pares = sorted({(f["area"], f["periodo"]) for f in filas})
    for area, periodo in pares:
        conn.execute(text("DELETE FROM respuestas_clima WHERE area_id = :a AND periodo = :p"), {"a": area, "p": periodo})
    for f in filas:
        conn.execute(
            text("INSERT INTO respuestas_clima (area_id, periodo, dimension, puntaje) VALUES (:area, :periodo, :dimension, :puntaje)"),
            f,
        )
    base = conn.execute(
        text("SELECT COUNT(*), COALESCE(SUM(r.puntaje), 0) FROM respuestas_clima r "
             "JOIN unnest(CAST(:a AS int[]), CAST(:p AS date[])) AS x(a, p) ON r.area_id = x.a AND r.periodo = x.p"),
        {"a": [a for a, _ in pares], "p": [p for _, p in pares]},
    ).one()
    conciliacion = [
        {"concepto": "Respuestas", "archivo": len(filas), "base": base[0]},
        {"concepto": "Suma de puntajes", "archivo": sum(f["puntaje"] for f in filas), "base": base[1]},
    ]
    return len(filas), conciliacion


def _aplicar_productividad(conn, filas):
    nuevas = 0
    for f in filas:
        nuevas += conn.execute(
            text(
                "INSERT INTO productividad (area_id, periodo, horas_efectivas, horas_disponibles, "
                "entregables_planificados, entregables_completados) VALUES (:area, :periodo, :horas_efectivas, "
                ":horas_disponibles, :entregables_planificados, :entregables_completados) "
                "ON CONFLICT (area_id, periodo) DO UPDATE SET horas_efectivas = EXCLUDED.horas_efectivas, "
                "horas_disponibles = EXCLUDED.horas_disponibles, entregables_planificados = EXCLUDED.entregables_planificados, "
                "entregables_completados = EXCLUDED.entregables_completados RETURNING (xmax = 0)"
            ),
            f,
        ).scalar_one()
    base = conn.execute(
        text("SELECT COUNT(*), COALESCE(SUM(t.horas_efectivas), 0)::float8 FROM productividad t "
             "JOIN unnest(CAST(:a AS int[]), CAST(:p AS date[])) AS x(a, p) ON t.area_id = x.a AND t.periodo = x.p"),
        {"a": [f["area"] for f in filas], "p": [f["periodo"] for f in filas]},
    ).one()
    conciliacion = [
        {"concepto": "Registros de área y mes", "archivo": len(filas), "base": base[0]},
        {"concepto": "Horas efectivas", "archivo": round(sum(f["horas_efectivas"] for f in filas), 1), "base": round(base[1], 1)},
    ]
    return nuevas, conciliacion


_APLICAR = {
    "hris": _aplicar_hris, "ats": _aplicar_ats, "desempeno": _aplicar_desempeno,
    "capacitacion": _aplicar_capacitacion, "clima": _aplicar_clima, "productividad": _aplicar_productividad,
}


def aplicar(id_: int, usuario: str) -> dict:
    """Aplica una carga validada en UNA transaccion y concilia. LookupError si
    no existe; ErrorDeCarga si no esta lista (con errores, ya aplicada...)."""
    asegurar_tabla()
    with engine.begin() as conn:
        carga = conn.execute(
            text("SELECT id, fuente, estado, datos, resultado FROM cargas WHERE id = :i FOR UPDATE"), {"i": id_}
        ).mappings().first()
        if carga is None:
            raise LookupError(f"La carga {id_} no existe")
        if carga["estado"] != "validada":
            raise ErrorDeCarga({
                "con_errores": "Esta carga tiene errores: corrige el archivo y vuelve a subirlo",
                "aplicada": "Esta carga ya se aplicó",
                "descartada": "Esta carga se descartó",
            }[carga["estado"]])
        fuente = FUENTES[carga["fuente"]]
        filas = _de_json(carga["datos"], fuente)
        nuevas, conciliacion = _APLICAR[fuente.clave](conn, filas)
        for c in conciliacion:
            c["cuadra"] = c["archivo"] == c["base"]
        resultado = {
            **carga["resultado"],
            "nuevas": int(nuevas),
            "actualizadas": len(filas) - int(nuevas) if fuente.clave != "clima" else 0,
            "conciliacion": conciliacion,
        }
        conn.execute(
            text("UPDATE cargas SET estado = 'aplicada', datos = NULL, resultado = CAST(:r AS jsonb), "
                 "aplicada_por = :u, aplicada_en = now() WHERE id = :i"),
            {"i": id_, "u": usuario, "r": json.dumps(resultado, ensure_ascii=False)},
        )
    return obtener(id_)


def descartar(id_: int, usuario: str) -> dict:
    asegurar_tabla()
    with engine.begin() as conn:
        estado = conn.execute(text("SELECT estado FROM cargas WHERE id = :i FOR UPDATE"), {"i": id_}).scalar()
        if estado is None:
            raise LookupError(f"La carga {id_} no existe")
        if estado == "aplicada":
            raise ErrorDeCarga("Una carga aplicada no se puede descartar")
        conn.execute(
            text("UPDATE cargas SET estado = 'descartada', datos = NULL, aplicada_por = :u, aplicada_en = now() WHERE id = :i"),
            {"i": id_, "u": usuario},
        )
    return obtener(id_)


_COLUMNAS = (
    "id, fuente, archivo, sha256, bytes, filas, estado, errores, descartadas, periodos, resultado, "
    "subida_por, subida_en, aplicada_por, aplicada_en"
)


def obtener(id_: int) -> dict | None:
    with engine.connect() as conn:
        fila = conn.execute(text(f"SELECT {_COLUMNAS} FROM cargas WHERE id = :i"), {"i": id_}).mappings().first()
    return dict(fila) if fila else None


def listar(limite: int = 50) -> list[dict]:
    asegurar_tabla()
    with engine.connect() as conn:
        filas = conn.execute(text(f"SELECT {_COLUMNAS} FROM cargas ORDER BY id DESC LIMIT :l"), {"l": limite}).mappings().all()
    return [dict(f) for f in filas]


# ------------------------------------------------------- plantillas y ejemplos
def _exportar(df: pd.DataFrame, formato: str) -> bytes:
    if formato == "xlsx":
        salida = io.BytesIO()
        df.to_excel(salida, index=False, engine="openpyxl")
        return salida.getvalue()
    return df.to_csv(index=False).encode("utf-8-sig")  # con BOM: Excel lo abre con acentos


def plantilla(clave_fuente: str, formato: str = "csv") -> bytes:
    """Solo los encabezados de la fuente, para llenarla a mano."""
    fuente = _fuente(clave_fuente)
    return _exportar(pd.DataFrame(columns=[c.nombre for c in fuente.columnas]), formato)


def _sumar_meses(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def mes_de_ejemplo() -> date | None:
    """Mes siguiente al ultimo que tienen TODAS las fuentes mensuales. None si
    ese mes aun no termina (no se reportan meses en curso)."""
    with engine.connect() as conn:
        ultimo = conn.execute(text(
            "SELECT LEAST((SELECT MAX(periodo) FROM metas_desempeno), (SELECT MAX(periodo) FROM programas_capacitacion), "
            "(SELECT MAX(periodo) FROM respuestas_clima), (SELECT MAX(periodo) FROM productividad))"
        )).scalar()
    if ultimo is None:
        return None
    mes = _sumar_meses(ultimo, 1)
    return mes if mes < _hoy().replace(day=1) else None


# Nombres claramente ficticios para mostrar que el sistema descarta datos personales
_NOMBRES = ["Ana", "Luis", "Marta", "Jorge", "Sofía", "Raúl", "Elena", "Iván", "Lucía", "Óscar", "Paula", "Diego"]
_APELLIDOS = ["Ríos", "Vega", "Solís", "Mora", "Campos", "Lara", "Nava", "Ibarra", "Fuentes", "Ochoa"]
_PUESTOS = {"Transporte": "Operador de tractocamión", "Almacén": "Auxiliar de almacén", "Ventas": "Ejecutivo comercial",
            "Operaciones": "Coordinador de operaciones", "Finanzas": "Analista contable", "Jurídico": "Abogado corporativo"}


def _paquete(mes: date) -> dict[str, pd.DataFrame]:
    """Los seis archivos de un mes, deterministas para ese mes y consistentes
    entre si: dan lo mismo antes o despues de cargar cualquiera de ellos."""
    rng = random.Random(f"nordika-{mes:%Y-%m}")
    fin = date(mes.year, mes.month, calendar.monthrange(mes.year, mes.month)[1])
    dia = lambda: mes + timedelta(days=rng.randint(0, (fin - mes).days))  # noqa: E731
    with engine.connect() as conn:
        areas = dict(conn.execute(text("SELECT id, nombre FROM areas ORDER BY id")).all())
        activos = conn.execute(
            text("SELECT id, codigo, area_id, fecha_ingreso FROM empleados WHERE fecha_ingreso < :m "
                 "AND (fecha_baja IS NULL OR fecha_baja >= :m) ORDER BY codigo"),
            {"m": mes},
        ).mappings().all()
        ultimo = conn.execute(
            text("SELECT COALESCE(MAX(CAST(substring(codigo FROM 2) AS int)), 0) FROM empleados "
                 "WHERE fecha_ingreso < :m AND codigo ~ '^E[0-9]+$'"),
            {"m": mes},
        ).scalar()

    hris, ats, plantilla_mes = [], [], []
    altas_por_area = {a: 0 for a in areas}
    for e in activos:
        fila = {"codigo": e["codigo"], "area": areas[e["area_id"]], "fecha_ingreso": e["fecha_ingreso"],
                "fecha_baja": None, "tipo_baja": None}
        if rng.random() < 0.014:
            fila["fecha_baja"] = dia()
            fila["tipo_baja"] = "voluntaria" if rng.random() < 0.7 else "involuntaria"
            altas_por_area[e["area_id"]] += 1
        hris.append(fila)
        plantilla_mes.append((e["codigo"], e["area_id"]))
    for area_id in areas:
        if areas[area_id] != "Jurídico" and rng.random() < 0.15:
            altas_por_area[area_id] += 1
    n_vacante = 0
    for area_id, n in altas_por_area.items():
        for _ in range(n):
            ultimo += 1
            codigo, ingreso = f"E{ultimo:04d}", dia()
            hris.append({"codigo": codigo, "area": areas[area_id], "fecha_ingreso": ingreso, "fecha_baja": None, "tipo_baja": None})
            plantilla_mes.append((codigo, area_id))
            n_vacante += 1
            dias = max(10, int(rng.gauss(55 if areas[area_id] == "Transporte" else 35, 10)))
            ats.append({"folio": f"VAC-{mes:%Y%m}-{n_vacante:03d}", "area": areas[area_id],
                        "fecha_apertura": ingreso - timedelta(days=dias), "fecha_contratacion": ingreso,
                        "costo_proceso": round(rng.uniform(8000, 25000), 2)})
    n_vacante += 1
    ats.append({"folio": f"VAC-{mes:%Y%m}-{n_vacante:03d}", "area": areas[rng.choice(list(areas))],
                "fecha_apertura": dia(), "fecha_contratacion": None, "costo_proceso": round(rng.uniform(8000, 25000), 2)})

    # Lo que de verdad exporta un HRIS trae nombre y puesto: el sistema los descarta
    hris_df = pd.DataFrame(hris)
    hris_df.insert(1, "nombre_completo", [f"{rng.choice(_NOMBRES)} {rng.choice(_APELLIDOS)} {rng.choice(_APELLIDOS)}"
                                          for _ in range(len(hris_df))])
    hris_df.insert(3, "puesto", [_PUESTOS.get(a, "Colaborador") for a in hris_df["area"]])

    periodo = mes.strftime("%Y-%m")
    desempeno = []
    for codigo, _area in plantilla_mes:
        asignadas = rng.randint(4, 8)
        logradas = round(asignadas * min(1, max(0, rng.gauss(0.82, 0.15))))
        ratio = logradas / asignadas
        calificacion = 1 if ratio < 0.4 else 2 if ratio < 0.6 else 3 if ratio < 0.8 else 4 if ratio < 0.95 else 5
        desempeno.append({"codigo_empleado": codigo, "periodo": periodo, "metas_asignadas": asignadas,
                          "metas_logradas": logradas, "calificacion": calificacion})

    capacitacion = []
    programas = [("Seguridad en maniobras de carga", None, 8.0),
                 (rng.choice(["Manejo defensivo", "Servicio al cliente", "Inventarios cíclicos"]),
                  rng.choice(list(areas)), 4.0)]
    for nombre, area_id, horas in programas:
        prob = rng.uniform(0.6, 0.9)
        for codigo, area in plantilla_mes:
            if (area_id is None or area == area_id) and rng.random() < prob:
                completado = rng.random() < 0.85
                capacitacion.append({
                    "programa": nombre, "periodo": periodo, "horas_programa": horas,
                    "area_programa": areas[area_id] if area_id else None, "codigo_empleado": codigo,
                    "completado": "sí" if completado else "no",
                    "horas_cursadas": horas if completado else round(horas * rng.uniform(0.1, 0.7), 1),
                })

    clima, productividad = [], []
    for area_id, nombre in areas.items():
        n = sum(1 for _, a in plantilla_mes if a == area_id)
        for _ in range(round(n * 0.75)):
            for dimension in ("enps", "satisfaccion", "liderazgo", "carga_trabajo"):
                media = 8.0 if dimension == "enps" else 7.2
                clima.append({"area": nombre, "periodo": periodo, "dimension": dimension,
                              "puntaje": int(min(10, max(0, round(rng.gauss(media, 1.8)))))})
        disponibles = n * 160.0
        planificados = max(1, round(n * 2.5))
        productividad.append({
            "area": nombre, "periodo": periodo,
            "horas_efectivas": round(disponibles * min(0.95, max(0.4, rng.gauss(0.72, 0.04))), 1),
            "horas_disponibles": disponibles, "entregables_planificados": planificados,
            "entregables_completados": round(planificados * min(1.0, max(0.3, rng.gauss(0.88, 0.06)))),
        })

    return {
        "hris": hris_df, "ats": pd.DataFrame(ats), "desempeno": pd.DataFrame(desempeno),
        "capacitacion": pd.DataFrame(capacitacion), "clima": pd.DataFrame(clima),
        "productividad": pd.DataFrame(productividad),
    }


def ejemplo(clave_fuente: str, formato: str = "xlsx") -> tuple[bytes, str]:
    """(contenido, nombre de archivo) del ejemplo del mes siguiente."""
    _fuente(clave_fuente)
    mes = mes_de_ejemplo()
    if mes is None:
        raise ErrorDeCarga("Ya están cargados todos los meses cerrados: no hay un mes siguiente que simular")
    df = _paquete(mes)[clave_fuente]
    return _exportar(df, formato), f"{clave_fuente}-{mes:%Y-%m}.{formato}"


def info_ejemplos() -> dict:
    mes = mes_de_ejemplo()
    return {"mes": mes.strftime("%Y-%m") if mes else None, "nombre_mes": _nombre_mes(mes) if mes else None}
