# Motor Inteligente de Reportes Ejecutivos de RRHH

Consolida los datos de Recursos Humanos (reclutamiento, desempeño, capacitación, rotación, clima laboral y productividad), calcula indicadores con su semáforo y genera con IA la narrativa ejecutiva de cada área y mes: resumen, hallazgos y recomendaciones.

- **Motor analítico (sin IA):** calcula los KPIs con SQL y pandas, de forma reproducible y verificada con pruebas.
- **Motor de narrativa (con IA):** el modelo redacta **solo** a partir de los KPIs ya calculados. Unos guardarrailes rechazan cifras inventadas, causas no demostradas y alertas omitidas. Todo reporte requiere revisión humana.
- **Acceso por rol:** Dirección ve el consolidado, RRHH ve todo, cada gerente ve solo su área y TI ve la configuración.

Requisitos, decisiones y reglas de negocio: [`docs/PRD.md`](docs/PRD.md).

> Los datos incluidos son **sintéticos** (empleados ficticios generados por `scripts/seed.py`). No contienen información de personas reales.

## Tecnologías

Python 3.14 · FastAPI · PostgreSQL 16 (Docker local o Supabase) · pandas · Ollama + Qwen3 8B (IA local) o Groq (IA en la nube, solo con datos sintéticos) · pytest

## Instalación local

Necesitas [Python 3.14](https://www.python.org/downloads/), [Docker Desktop](https://www.docker.com/products/docker-desktop/) y Git. Los comandos son para PowerShell en Windows.

```powershell
git clone https://github.com/warsharkt/Motor-Inteligente.git
cd Motor-Inteligente

# 1. Configuración: copia el ejemplo y edítalo
copy .env.example .env
#    - cambia POSTGRES_PASSWORD
#    - genera JWT_SECRETO con:  python -c "import secrets; print(secrets.token_urlsafe(48))"

# 2. Base de datos (PostgreSQL en Docker)
docker compose up -d

# 3. Entorno de Python
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 4. Datos sintéticos (24 meses, 6 áreas)
python -m scripts.seed

# 5. Tu usuario (la contraseña se escribe oculta; mínimo 10 caracteres)
python -m scripts.crear_usuario --usuario admin --nombre "Tu Nombre" --rol rrhh

# 6. Arrancar la API
python -m uvicorn app.main:app --reload
```

Abre http://localhost:8000/docs, pulsa **Authorize**, escribe tu usuario y contraseña, y prueba los endpoints.

## Inteligencia artificial

La narrativa siempre la redacta un modelo. Hay dos opciones, y se elige en el `.env`:

| Opción | Configuración | Cuándo usarla |
|---|---|---|
| **Ollama local** (por defecto) | Instala [Ollama](https://ollama.com), ejecuta `ollama pull qwen3:8b` y deja `LLM_PROVEEDOR=ollama` | Datos reales: nada sale de tu equipo. En CPU tarda de 2 a 5 minutos por reporte |
| **Groq** (nube, gratis) | Crea una llave en https://console.groq.com/keys y pon `LLM_PROVEEDOR=groq`, `MODO_DATOS=sinteticos` y `GROQ_API_KEY=...` | Para revisar el proyecto rápido: responde en segundos. **Solo con datos sintéticos**; el sistema se niega a usarla si `MODO_DATOS` no es `sinteticos` |

Los reportes se generan en segundo plano: `POST /narrativas` devuelve un id y `GET /narrativas/{id}` muestra el resultado cuando está listo.

## Usuarios y roles

```powershell
python -m scripts.crear_usuario --usuario dir  --nombre "Dirección"      --rol direccion
python -m scripts.crear_usuario --usuario luis --nombre "Gerente Ventas" --rol gerente --area Ventas
python -m scripts.crear_usuario --usuario ti   --nombre "Soporte TI"     --rol admin_ti
python -m scripts.crear_usuario --listar
python -m scripts.crear_usuario --usuario luis --cambiar-contrasena   # también desbloquea la cuenta
```

| Rol | Ve |
|---|---|
| `direccion` | Solo el consolidado corporativo |
| `rrhh` | Todo |
| `gerente` | Solo su área |
| `admin_ti` | Catálogos y configuración, sin datos de colaboradores |

## Base de datos compartida en Supabase (opcional)

Sirve para que varias personas usen la misma base sin instalar Docker. Usa **solo datos sintéticos**.

1. Crea una cuenta en https://supabase.com y un proyecto nuevo (plan Free). Elige la región **East US** y guarda la contraseña de la base que definas.
2. En el proyecto, pulsa **Connect**, elige **Session pooler** y copia la cadena de conexión.
3. En tu `.env`, agrega `DATABASE_URL=` con esa cadena, cambiando `[YOUR-PASSWORD]` por tu contraseña. El SSL se activa solo.
4. Carga los datos y crea los usuarios, ahora en Supabase:
   ```powershell
   python -m scripts.seed          # pide escribir BORRAR para confirmar
   python -m scripts.crear_usuario --usuario admin --nombre "Tu Nombre" --rol rrhh
   ```
5. Arranca la API como siempre. Al iniciar, activa *Row Level Security* en todas las tablas: así la API pública de Supabase no puede leer ni modificar nada, y solo este backend accede a los datos.

Para volver a la base local, comenta `DATABASE_URL` en el `.env`.

Notas del plan gratuito: el proyecto **se pausa tras 7 días sin actividad** (se reactiva desde el panel) y tiene un límite de 500 MB. Esta base ocupa unos 13 MB.

## Pruebas

```powershell
cd backend
python -m pytest -q
```

Usan el PostgreSQL local y **no** necesitan Ollama, Groq ni internet: el modelo se simula. Por seguridad, se niegan a correr si `DATABASE_URL` apunta a una base remota.

## Estructura

```
backend/
  app/
    main.py          API (endpoints)
    kpis.py          motor analítico: indicadores, tendencias, semáforo
    narrativa.py     motor de narrativa: hechos, prompt, reintentos
    guardrails.py    validación de lo que redacta la IA
    llm.py           proveedores de IA (Ollama, Groq) y candado de datos
    trabajos.py      generación de narrativas en segundo plano
    seguridad.py     inicio de sesión, contraseñas, tokens y permisos por rol
    database.py      conexión a PostgreSQL (local o Supabase)
  scripts/           seed, crear_usuario, generar_narrativa, evaluar_narrativa
  tests/             pruebas automáticas
  reportes/          resultados de las evaluaciones del modelo de IA
db/                  esquema y tablas (SQL)
docs/PRD.md          documento de requerimientos del producto
```
