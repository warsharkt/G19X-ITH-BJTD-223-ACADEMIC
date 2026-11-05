"""API de Talentia Insights: analitica de Recursos Humanos con IA (pasos 4 a 10).

KPIs de solo lectura, narrativas generadas por IA en segundo plano (se
guardan en la tabla `narrativas`), avisos, umbrales editables y programacion
mensual. Todo, salvo /health y /auth/login, requiere iniciar sesion; cada rol
ve solo lo que le corresponde (ver app/seguridad.py y la regla 10.3.2 del PRD).

Aqui solo se arma la aplicacion: los endpoints estan en app/rutas/, uno por tema.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app import avisos, cargas, mfa, origen, programacion, seguridad, trabajos
from app.database import ejecutar_sql
from app.kpis import inicializar_umbrales
from app.rutas import (
    avisos as rutas_avisos,
    cargas as rutas_cargas,
    catalogos,
    configuracion,
    cuentas,
    demostracion,
    firmas,
    indicadores,
    narrativas,
    sesion,
    sistema,
)


@asynccontextmanager
async def ciclo_de_vida(_app):
    try:
        seguridad.asegurar_tabla()
        try:
            if cifrados := mfa.cifrar_pendientes():
                print(f"Se cifraron {cifrados} secretos de verificación en dos pasos que estaban en claro.")
        except mfa.LlaveMfaInvalida as exc:
            print(f"Verificación en dos pasos sin llave: {exc}")  # quien la use recibe un 503
        trabajos.marcar_interrumpidas()
        inicializar_umbrales()
        avisos.asegurar_tabla()
        programacion.asegurar_tabla()
        cargas.asegurar_tabla()
        ejecutar_sql("rls.sql")  # al final: cubre todas las tablas ya creadas
    except SQLAlchemyError:
        pass  # sin BD la API arranca igual; /health lo reporta
    programacion.iniciar()  # alertas y reportes del mes; si no hay BD, reintenta solo
    yield
    programacion.detener()


app = FastAPI(
    lifespan=ciclo_de_vida,
    title="Talentia Insights",
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
    allow_methods=["GET", "POST", "PUT", "PATCH"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # nombre del archivo al exportar
)


@app.middleware("http")
async def origen_y_sin_cache(request, siguiente):
    """La IP de quien hace la peticion, para las bitacoras (app/origen.py), y
    Cache-Control: no-store, porque las respuestas llevan datos de RRHH que
    el navegador no debe guardar en disco (un equipo compartido los dejaria
    a la vista)."""
    origen.actual.set(request.client.host if request.client else None)
    respuesta = await siguiente(request)
    respuesta.headers.setdefault("Cache-Control", "no-store")
    return respuesta


@app.exception_handler(SQLAlchemyError)
def base_no_disponible(_request, _exc: SQLAlchemyError):
    """Las rutas ya lo traducen; esto cubre lo que corre antes de ellas (la sesion)."""
    return JSONResponse(status_code=503, content={"detail": "Base de datos no disponible"})


@app.exception_handler(mfa.LlaveMfaInvalida)
def sin_llave_de_mfa(_request, exc: mfa.LlaveMfaInvalida):
    """MFA_LLAVE mal configurada: es un problema del servidor, no de la persona."""
    return JSONResponse(status_code=503, content={"detail": f"Verificación en dos pasos no disponible: {exc}"})


# En este orden aparecen en /docs
for modulo in (
    sistema, sesion, catalogos, indicadores, narrativas, configuracion, firmas, rutas_avisos, cuentas,
    demostracion, rutas_cargas,
):
    app.include_router(modulo.router)
