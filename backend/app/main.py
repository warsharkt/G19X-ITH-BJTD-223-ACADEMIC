"""API del Motor Inteligente de Reportes de RRHH (pasos 4 a 10).

KPIs de solo lectura, narrativas generadas por IA en segundo plano (se
guardan en la tabla `narrativas`), avisos, umbrales editables y programacion
mensual. Todo, salvo /health y /auth/login, requiere iniciar sesion; cada rol
ve solo lo que le corresponde (ver app/seguridad.py y la regla 10.3.2 del PRD).
"""
import time
from contextlib import asynccontextmanager
from typing import Literal

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import avisos, exportar, narrativa, programacion, schemas, seguridad, trabajos, umbrales
from app.database import ejecutar_sql, engine
from app.kpis import CORPORATIVO, calcular_kpis, inicializar_umbrales
from app.llm import ConfiguracionIA, obtener_proveedor
from app.seguridad import (
    Usuario,
    area_por_defecto,
    areas_visibles,
    con_acceso_a_datos,
    exigir_acceso_a_datos,
    usuario_actual,
)


@asynccontextmanager
async def ciclo_de_vida(_app):
    try:
        seguridad.asegurar_tabla()
        trabajos.marcar_interrumpidas()
        inicializar_umbrales()
        avisos.asegurar_tabla()
        programacion.asegurar_tabla()
        ejecutar_sql("rls.sql")  # al final: cubre todas las tablas ya creadas
    except SQLAlchemyError:
        pass  # sin BD la API arranca igual; /health lo reporta
    programacion.iniciar()  # alertas y reportes del mes; si no hay BD, reintenta solo
    yield
    programacion.detener()


app = FastAPI(
    lifespan=ciclo_de_vida,
    title="Motor Inteligente de Reportes de RRHH",
    description=(
        "Indicadores de Recursos Humanos calculados por el motor analitico "
        "(sin IA): rotacion, clima, desempeno, capacitacion, reclutamiento y "
        "productividad, con tendencias y semaforo."
    ),
    version="0.10.0",
)

# El frontend de React (paso 7) se sirve en local desde estos origenes.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # nombre del archivo al exportar
)

PATRON_MES = r"^\d{4}-(0[1-9]|1[0-2])$"
SEGUNDOS_CACHE = 60

# Calcular los KPIs toma casi un segundo: se guardan en memoria unos segundos
# para no recalcular en cada peticion del dashboard.
_cache = {"df": None, "momento": 0.0}


def kpis_df() -> pd.DataFrame:
    ahora = time.monotonic()
    if _cache["df"] is None or ahora - _cache["momento"] > SEGUNDOS_CACHE:
        try:
            _cache["df"] = calcular_kpis()
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")
        _cache["momento"] = ahora
    return _cache["df"]


def a_registros(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> lista de dicts JSON-compatible (NaN pasa a null)."""
    df = df.assign(periodo=df["periodo"].dt.date).astype(object)
    return df.where(df.notna(), None).to_dict("records")


def _mes(texto: str) -> pd.Timestamp:
    return pd.Timestamp(texto + "-01")


@app.get("/health", tags=["Sistema"])
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {type(exc).__name__}"
    return {"status": "ok", "database": db_status}


# ------------------------------------------------------------------ sesion
@app.post("/auth/login", response_model=schemas.Token, tags=["Sesión"])
def login(formulario: OAuth2PasswordRequestForm = Depends()):
    """Inicia sesion con usuario y contrasena; devuelve un token que caduca.

    En /docs usa el boton "Authorize". Tras varios intentos fallidos seguidos
    la cuenta se bloquea unos minutos.
    """
    try:
        u = seguridad.autenticar(formulario.username, formulario.password)
        token = seguridad.crear_token(u)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    return {"access_token": token, "token_type": "bearer", "expira_en_minutos": seguridad.minutos_de_sesion()}


@app.get("/auth/yo", response_model=schemas.UsuarioOut, tags=["Sesión"])
def yo(u: Usuario = Depends(usuario_actual)):
    """Quien eres y que areas puedes consultar (para armar el menu del frontend)."""
    return {**u.__dict__, "areas_permitidas": areas_visibles(u, _ids_de_areas())}


def _ids_de_areas() -> list[int]:
    try:
        with engine.connect() as conn:
            return [CORPORATIVO] + list(conn.execute(text("SELECT id FROM areas ORDER BY id")).scalars())
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


# --------------------------------------------------------------- catalogos
@app.get("/areas", response_model=list[schemas.Area], tags=["Catalogos"])
def areas(u: Usuario = Depends(usuario_actual)):
    """Areas que el usuario puede consultar. El id 0 es el consolidado corporativo."""
    try:
        with engine.connect() as conn:
            filas = conn.execute(text("SELECT id, nombre FROM areas ORDER BY id")).all()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    todas = [{"id": CORPORATIVO, "nombre": "Corporativo"}] + [{"id": i, "nombre": n} for i, n in filas]
    permitidas = set(areas_visibles(u, [a["id"] for a in todas]))
    return [a for a in todas if a["id"] in permitidas]


@app.get("/periodos", response_model=list[str], tags=["Catalogos"])
def periodos(_u: Usuario = Depends(usuario_actual)):
    """Meses con datos, en formato AAAA-MM, del mas antiguo al mas reciente."""
    return sorted(p.strftime("%Y-%m") for p in kpis_df()["periodo"].unique())


@app.get("/umbrales", response_model=list[schemas.Umbral], tags=["Catalogos"])
def ver_umbrales(_u: Usuario = Depends(usuario_actual)):
    """Umbrales de atencion y criticos que definen el semaforo de cada indicador."""
    try:
        return umbrales.listar()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@app.get("/kpis", response_model=list[schemas.KpiFila], tags=["KPIs"])
def kpis(
    periodo: str | None = Query(
        None, pattern=PATRON_MES, description="AAAA-MM. Por defecto, el ultimo mes con datos."
    ),
    area_id: int | None = Query(
        None, description="0 = consolidado corporativo. Por defecto: tu area si eres gerente, si no el 0."
    ),
    indicador: str | None = Query(None, description="Filtra por un indicador"),
    u: Usuario = Depends(con_acceso_a_datos),
):
    """KPIs de un mes y un area, con tendencias y semaforo."""
    area_id = area_por_defecto(u) if area_id is None else area_id
    exigir_acceso_a_datos(u, area_id)
    df = kpis_df()
    mes = _mes(periodo) if periodo else df["periodo"].max()
    if not (df["periodo"] == mes).any():
        raise HTTPException(status_code=404, detail=f"No hay datos para el periodo {periodo}")
    if area_id not in set(df["area_id"]):
        raise HTTPException(status_code=404, detail=f"El area {area_id} no existe")
    if indicador is not None and indicador not in set(df["indicador"]):
        raise HTTPException(status_code=404, detail=f"El indicador '{indicador}' no existe")

    filtro = (df["periodo"] == mes) & (df["area_id"] == area_id)
    if indicador is not None:
        filtro &= df["indicador"] == indicador
    return a_registros(df[filtro])


@app.get("/kpis/serie/{indicador}", response_model=list[schemas.PuntoSerie], tags=["KPIs"])
def serie(
    indicador: str,
    area_id: int | None = Query(
        None, description="0 = consolidado corporativo. Por defecto: tu area si eres gerente, si no el 0."
    ),
    desde: str | None = Query(None, pattern=PATRON_MES, description="AAAA-MM"),
    hasta: str | None = Query(None, pattern=PATRON_MES, description="AAAA-MM"),
    u: Usuario = Depends(con_acceso_a_datos),
):
    """Serie de tiempo de un indicador (para las graficas del dashboard)."""
    area_id = area_por_defecto(u) if area_id is None else area_id
    exigir_acceso_a_datos(u, area_id)
    df = kpis_df()
    if indicador not in set(df["indicador"]):
        raise HTTPException(status_code=404, detail=f"El indicador '{indicador}' no existe")
    if area_id not in set(df["area_id"]):
        raise HTTPException(status_code=404, detail=f"El area {area_id} no existe")

    f = df[(df["indicador"] == indicador) & (df["area_id"] == area_id)]
    if desde:
        f = f[f["periodo"] >= _mes(desde)]
    if hasta:
        f = f[f["periodo"] <= _mes(hasta)]
    f = f.sort_values("periodo")[["periodo", "valor", "n", "suprimido", "estado"]]
    return a_registros(f)


def proveedor_configurado():
    """Proveedor del .env; 503 con el motivo si la configuracion no es valida o segura."""
    try:
        return obtener_proveedor()
    except ConfiguracionIA as exc:
        raise HTTPException(status_code=503, detail=f"IA no disponible: {exc}")


@app.post(
    "/narrativas", status_code=202, response_model=schemas.TrabajoNarrativa, tags=["Narrativa"]
)
def crear_narrativa(
    solicitud: schemas.NarrativaSolicitud,
    u: Usuario = Depends(con_acceso_a_datos),
    proveedor=Depends(proveedor_configurado),
):
    """Solicita la narrativa ejecutiva (resumen, hallazgos y recomendaciones).

    Responde de inmediato con un id y estado `en_proceso`; el modelo la redacta
    en segundo plano (en CPU tarda minutos). Consulta el resultado con
    `GET /narrativas/{id}`. La redacta SIEMPRE el modelo de lenguaje, solo a
    partir de los KPIs ya calculados, y su respuesta se valida (cifras,
    trazabilidad, sin causalidad); si no lo logra, termina en `error` con el
    motivo. Siempre requiere revision humana antes de distribuirse.
    """
    area_id = area_por_defecto(u) if solicitud.area_id is None else solicitud.area_id
    exigir_acceso_a_datos(u, area_id)
    df = kpis_df()
    try:
        periodo, _ = narrativa.validar_solicitud(
            df, _mes(solicitud.periodo) if solicitud.periodo else None, area_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    try:
        id_ = trabajos.encolar(periodo, area_id, proveedor, df, solicitante=u.usuario)
        return trabajos.obtener(id_)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@app.get("/narrativas/{id_narrativa}", response_model=schemas.TrabajoNarrativa, tags=["Narrativa"])
def ver_narrativa(id_narrativa: int, u: Usuario = Depends(con_acceso_a_datos)):
    """Estado de una solicitud y, cuando esta `lista`, la narrativa completa."""
    try:
        trabajo = trabajos.obtener(id_narrativa)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    if trabajo is None:
        raise HTTPException(status_code=404, detail=f"La narrativa {id_narrativa} no existe")
    exigir_acceso_a_datos(u, trabajo["area_id"])
    return trabajo


@app.post(
    "/narrativas/{id_narrativa}/revision", response_model=schemas.TrabajoNarrativa, tags=["Narrativa"]
)
def revisar_narrativa(
    id_narrativa: int, solicitud: schemas.RevisionSolicitud, u: Usuario = Depends(con_acceso_a_datos)
):
    """Aprueba o rechaza una narrativa terminada (RF-05) y registra quien lo hizo (RF-11).

    Solo RRHH puede revisar, y nunca una narrativa que la misma persona
    solicito: siempre la revisa alguien distinto. La decision es definitiva;
    si se rechaza, se explica el motivo y se solicita una nueva.
    """
    if u.rol != "rrhh":
        raise HTTPException(status_code=403, detail="Solo Recursos Humanos puede aprobar o rechazar reportes")
    try:
        trabajo = trabajos.revisar(id_narrativa, solicitud.decision, u.usuario, solicitud.comentario)
    except trabajos.RevisionNoPermitida as exc:
        raise HTTPException(status_code=409 if exc.conflicto else 403, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    if trabajo is None:
        raise HTTPException(status_code=404, detail=f"La narrativa {id_narrativa} no existe")
    return trabajo


@app.get(
    "/narrativas/{id_narrativa}/exportar",
    tags=["Narrativa"],
    response_class=Response,
    responses={200: {"content": {tipo: {} for tipo in exportar.FORMATOS.values()},
                     "description": "Archivo del reporte"}},
)
def exportar_narrativa(
    id_narrativa: int,
    formato: Literal["pdf", "pptx"] = Query("pdf", description="pdf (reporte) o pptx (presentacion ejecutiva)"),
    u: Usuario = Depends(con_acceso_a_datos),
):
    """Descarga el reporte en PDF o como presentacion ejecutiva (RF-08).

    Solo los reportes **aprobados** por RRHH se pueden exportar (regla 10.3.9),
    y cada quien solo los de las areas que puede ver. El archivo se arma con
    la narrativa aprobada tal como quedo guardada (no se recalcula nada) y
    cada descarga queda en la bitacora: quien, en que formato y cuando.
    """
    try:
        trabajo = trabajos.obtener(id_narrativa)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    if trabajo is None:
        raise HTTPException(status_code=404, detail=f"La narrativa {id_narrativa} no existe")
    exigir_acceso_a_datos(u, trabajo["area_id"])
    if trabajo["estado"] != "lista" or trabajo["revision"] != "aprobada":
        estado = trabajo["revision"] if trabajo["estado"] == "lista" else trabajo["estado"]
        raise HTTPException(
            status_code=409,
            detail=f"Solo se pueden exportar reportes aprobados por RRHH; este está {estado.replace('_', ' ')}",
        )
    contenido = exportar.generar(trabajo, formato)
    try:
        trabajos.registrar_exportacion(id_narrativa, formato, u.usuario)
    except SQLAlchemyError:  # sin bitacora no se distribuye
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    return Response(
        contenido,
        media_type=exportar.FORMATOS[formato],
        headers={"Content-Disposition": f'attachment; filename="{exportar.nombre_archivo(trabajo, formato)}"'},
    )


@app.get("/narrativas", response_model=list[schemas.TrabajoNarrativa], tags=["Narrativa"])
def historial_narrativas(
    area_id: int | None = Query(None, description="0 = consolidado corporativo"),
    periodo: str | None = Query(None, pattern=PATRON_MES, description="AAAA-MM"),
    revision: str | None = Query(
        None, pattern="^(pendiente|aprobada|rechazada)$", description="Solo narrativas listas con esa revision"
    ),
    limite: int = Query(20, ge=1, le=100),
    u: Usuario = Depends(con_acceso_a_datos),
):
    """Historial de solicitudes de las areas que puedes ver, de la mas reciente a la mas antigua."""
    if area_id is not None:
        exigir_acceso_a_datos(u, area_id)
        area_ids = [area_id]
    else:
        area_ids = None if u.rol == "rrhh" else areas_visibles(u, [])
    try:
        return trabajos.listar(area_ids, _mes(periodo) if periodo else None, limite, revision)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


# ------------------------------------------------- configuracion (RF-12)
def solo_rrhh(u: Usuario = Depends(usuario_actual)) -> Usuario:
    """Dependencia: los umbrales y la programacion los cambia solo RRHH (regla 10.3.3)."""
    if u.rol != "rrhh":
        raise HTTPException(status_code=403, detail="Solo Recursos Humanos puede cambiar esta configuración")
    return u


@app.put("/umbrales/{indicador}", response_model=schemas.Umbral, tags=["Configuración"])
def cambiar_umbral(indicador: str, cambio: schemas.UmbralCambio, u: Usuario = Depends(solo_rrhh)):
    """Cambia los umbrales de un indicador (solo RRHH). Queda en la bitacora.

    El semaforo se recalcula de inmediato. Las alertas que resulten se avisan
    en la siguiente revision de la programacion (cada hora)."""
    try:
        nuevo = umbrales.actualizar(indicador, cambio.umbral_atencion, cambio.umbral_critico, u.usuario)
    except umbrales.UmbralInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    if nuevo is None:
        raise HTTPException(status_code=404, detail=f"El indicador '{indicador}' no existe")
    _cache["df"] = None  # el semaforo cambio: recalcular en la siguiente consulta
    return nuevo


@app.get("/umbrales/cambios", response_model=list[schemas.CambioUmbral], tags=["Configuración"])
def cambios_de_umbrales(limite: int = Query(20, ge=1, le=100), _u: Usuario = Depends(usuario_actual)):
    """Bitacora de cambios de umbrales: quien, cuando, y valores de antes y despues."""
    try:
        return umbrales.cambios(limite)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@app.get("/programacion", response_model=schemas.Programacion, tags=["Configuración"])
def ver_programacion(_u: Usuario = Depends(usuario_actual)):
    """Programacion mensual de reportes (RF-07) y los meses que ya genero."""
    try:
        return {
            **programacion.leer(),
            "correo_activo": avisos.configuracion_smtp() is not None,
            "corridas": programacion.corridas(),
        }
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@app.put("/programacion", response_model=schemas.Programacion, tags=["Configuración"])
def cambiar_programacion(cambio: schemas.ProgramacionCambio, u: Usuario = Depends(solo_rrhh)):
    """Activa o desactiva la programacion y elige el dia del mes (solo RRHH).

    Cada mes, a partir de ese dia, se generan los reportes del ultimo mes
    cerrado con datos: el consolidado y cada area. Al guardar, la API revisa
    de inmediato si ya toca."""
    try:
        programacion.guardar(cambio.activa, cambio.dia_del_mes, u.usuario)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    programacion.revisar_pronto()
    return ver_programacion(u)


# ----------------------------------------------------------- avisos (RF-09)
@app.get("/avisos", response_model=schemas.Avisos, tags=["Avisos"])
def ver_avisos(
    solo_no_leidos: bool = False,
    limite: int = Query(50, ge=1, le=200),
    u: Usuario = Depends(usuario_actual),
):
    """Tus avisos (alertas en rojo, reportes por revisar, aprobados o
    rechazados), del mas reciente al mas antiguo, y cuantos no has leido.
    Solo los de las areas que puedes ver hoy."""
    try:
        return avisos.listar(u, solo_no_leidos, limite)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


@app.post("/avisos/{id_aviso}/leido", status_code=204, tags=["Avisos"])
def marcar_aviso_leido(id_aviso: int, u: Usuario = Depends(usuario_actual)):
    try:
        existe = avisos.marcar_leido(u, id_aviso)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    if not existe:
        raise HTTPException(status_code=404, detail=f"El aviso {id_aviso} no existe")
    return Response(status_code=204)


@app.post("/avisos/leidos", tags=["Avisos"])
def marcar_todos_los_avisos(u: Usuario = Depends(usuario_actual)) -> dict[str, int]:
    """Marca como leidos todos tus avisos."""
    try:
        return {"marcados": avisos.marcar_todos(u)}
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
