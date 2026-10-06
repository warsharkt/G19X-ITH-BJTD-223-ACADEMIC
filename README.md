# Motor Inteligente de Reportes Ejecutivos de RRHH

Consolida los datos de Recursos Humanos (reclutamiento, desempeño, capacitación, rotación, clima laboral y productividad), calcula indicadores con su semáforo y genera con IA la narrativa ejecutiva de cada área y mes: resumen, hallazgos y recomendaciones.

- **Motor analítico (sin IA):** calcula los KPIs con SQL y pandas, de forma reproducible y verificada con pruebas.
- **Motor de narrativa (con IA):** el modelo redacta **solo** a partir de los KPIs ya calculados. Unos guardarrailes rechazan cifras inventadas, causas no demostradas y alertas omitidas. Todo reporte requiere revisión humana.
- **Acceso por rol:** Dirección ve el consolidado, RRHH ve todo, cada gerente ve solo su área y TI ve la configuración.
- **Tablero web (React):** indicadores del mes con semáforo, tendencia de 24 meses con umbrales, generación de reportes con IA e historial.
- **Exportación:** los reportes aprobados se descargan en PDF y como presentación de PowerPoint.
- **Avisos y programación mensual:** cada persona recibe avisos de indicadores en rojo y de reportes por revisar o aprobados. Los reportes del mes se pueden generar solos, y RRHH ajusta los umbrales desde el panel de configuración.

Requisitos, decisiones y reglas de negocio: [`docs/PRD.md`](docs/PRD.md).

> Los datos incluidos son **sintéticos** (empleados ficticios generados por `scripts/seed.py`). No contienen información de personas reales.

## Tecnologías

Python 3.14 · FastAPI · PostgreSQL 16 (Docker local o Supabase) · pandas · Ollama + Qwen3 8B (IA local) o Groq (IA en la nube, solo con datos sintéticos) · ReportLab (PDF) y python-pptx (presentación) · React + Vite + Recharts · pytest y Vitest

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

Al crear el usuario, **escribe la contraseña a mano**: en la entrada oculta de PowerShell, Ctrl+V no pega el texto sino un carácter invisible, y la contraseña guardada no será la que crees.

## Tablero web (frontend)

Necesitas [Node.js](https://nodejs.org) 20 o más reciente. Con la API encendida, en otra terminal:

```powershell
cd frontend
npm install
npm run dev
```

Abre http://localhost:5173 e inicia sesión con tu usuario. Si la API no está en `http://localhost:8000`, copia `frontend/.env.example` a `frontend/.env` y cambia `VITE_API_URL`.

| Sección | Qué hace |
|---|---|
| **Tablero** | Indicadores del mes con semáforo (siempre con icono y texto), variación contra el mes y el año anterior, y la tendencia del indicador elegido con sus umbrales. Filtros por área, mes e indicador; quedan en la dirección de la página, así que se pueden compartir |
| **Narrativas** | Solicita el reporte con IA de un área y mes, muestra el avance mientras se redacta, permite aprobarlo o rechazarlo, descargar los aprobados en PDF o presentación, y guarda el historial consultable por área, mes y revisión |
| **Avisos** | Indicadores en rojo, reportes por revisar y reportes aprobados o rechazados de tus áreas. El menú muestra cuántos faltan por leer |
| **Configuración** | Umbrales del semáforo con su bitácora de cambios, y programación mensual. Todos la ven; solo RRHH la cambia |

Cada rol ve solo lo suyo: Dirección no puede cambiar de área, y TI solo ve la configuración, sin poder cambiarla. La API aplica los mismos permisos, así que no dependen de la interfaz. La sesión se guarda solo en la pestaña (`sessionStorage`) y se cierra sola cuando el token vence.

## Inteligencia artificial

La narrativa siempre la redacta un modelo. Hay dos opciones, y se elige en el `.env`:

| Opción | Configuración | Cuándo usarla |
|---|---|---|
| **Ollama local** (por defecto) | Instala [Ollama](https://ollama.com), ejecuta `ollama pull qwen3:8b` y deja `LLM_PROVEEDOR=ollama` | Datos reales: nada sale de tu equipo. En CPU tarda de 2 a 5 minutos por reporte |
| **Groq** (nube, gratis) | Crea una llave en https://console.groq.com/keys y pon `LLM_PROVEEDOR=groq`, `MODO_DATOS=sinteticos` y `GROQ_API_KEY=...` | Para revisar el proyecto rápido: responde en segundos. **Solo con datos sintéticos**; el sistema se niega a usarla si `MODO_DATOS` no es `sinteticos` |

Los reportes se generan en segundo plano: `POST /narrativas` devuelve un id y `GET /narrativas/{id}` muestra el resultado cuando está listo.

### Revisión antes de distribuir

Todo reporte nace **pendiente de revisión**. Una persona de RRHH lo **aprueba** o lo **rechaza** con motivo desde la pantalla del reporte (o con `POST /narrativas/{id}/revision`). Quien lo solicitó no puede aprobarlo: para probar este flujo necesitas **dos usuarios con rol `rrhh`**. La decisión es definitiva y queda registrada con usuario, fecha y comentario. Si se rechaza, se solicita uno nuevo.

### Exportar

Los reportes **aprobados** se descargan desde la pantalla del reporte (o con `GET /narrativas/{id}/exportar?formato=pdf|pptx`):

- **PDF** (tamaño carta): portada con quién aprobó, resumen, indicadores clave con su semáforo, hallazgos, alertas, recomendaciones y un anexo con fórmulas, umbrales y fuentes.
- **Presentación** (PowerPoint 16:9): las mismas secciones, una por diapositiva.

El archivo se arma con la narrativa aprobada tal como quedó guardada: no se recalcula nada, así que se distribuye exactamente lo que se revisó. Los pendientes y rechazados no se pueden exportar, y cada descarga queda registrada (quién, formato y fecha) en la tabla `exportaciones`.

Si ya tenías el entorno instalado, vuelve a correr `pip install -r requirements.txt` para instalar las bibliotecas de exportación.

## Avisos y programación mensual

**Avisos.** Llegan a la sección **Avisos** del tablero:

| Evento | Lo reciben |
|---|---|
| Indicador en rojo del consolidado | Dirección y RRHH |
| Indicador en rojo de un área | El gerente del área y RRHH |
| Reporte listo para revisión | RRHH, menos quien lo pidió |
| Reporte aprobado | Su audiencia y quien lo pidió |
| Reporte rechazado | Quien lo pidió |

**Programación mensual.** En **Configuración**, una persona de RRHH la activa y elige el día. A partir de ese día se generan los reportes del último mes cerrado con datos (el consolidado y cada área), una sola vez por mes. Nacen pendientes de revisión y los puede aprobar cualquier persona de RRHH. Nace **desactivada**: con Ollama en CPU, cada mes son varios reportes de minutos cada uno.

La API revisa al arrancar y cada hora, así que si estuvo apagada el día programado se pone al día al encenderse. Para que funcione aunque la API esté apagada, programa el script en el Programador de tareas de Windows (cambia la ruta):

```powershell
python -m scripts.programar          # revisa y genera lo que falte; espera a que terminen
python -m scripts.programar --ver    # solo muestra la configuración y los meses generados

schtasks /create /tn "Motor RRHH" /sc daily /st 07:00 /tr "cmd /c cd /d C:\ruta\backend && .venv\Scripts\python.exe -m scripts.programar"
```

**Correo (opcional).** Está apagado por defecto. Si llenas `SMTP_HOST` y los demás datos `SMTP_*` en el `.env`, quien tenga correo registrado recibe un correo con "tienes N avisos nuevos" y la liga al sistema. **El correo nunca lleva datos**: ni áreas, ni indicadores, ni cifras. Con Gmail usa `smtp.gmail.com`, puerto `587` y una [contraseña de aplicación](https://myaccount.google.com/apppasswords), nunca tu contraseña normal.

## Usuarios y roles

```powershell
python -m scripts.crear_usuario --usuario dir  --nombre "Dirección"      --rol direccion
python -m scripts.crear_usuario --usuario luis --nombre "Gerente Ventas" --rol gerente --area Ventas
python -m scripts.crear_usuario --usuario ti   --nombre "Soporte TI"     --rol admin_ti
python -m scripts.crear_usuario --listar
python -m scripts.crear_usuario --usuario luis --cambiar-contrasena   # también desbloquea la cuenta
python -m scripts.crear_usuario --usuario luis --cambiar-correo luis@empresa.com   # "" lo quita
```

Al crear un usuario puedes agregar `--correo` para que reciba el correo de avisos.

| Rol | Ve |
|---|---|
| `direccion` | Solo el consolidado corporativo |
| `rrhh` | Todo; aprueba o rechaza los reportes que solicitó otra persona; cambia umbrales y programación |
| `gerente` | Solo su área |
| `admin_ti` | Catálogos y configuración (sin cambiarla), sin datos de colaboradores ni avisos |

## Base de datos compartida en Supabase (opcional)

Sirve para que varias personas usen la misma base sin instalar Docker. Usa **solo datos sintéticos**.

1. Crea una cuenta en https://supabase.com y un proyecto nuevo (plan Free) en cualquier región. Guarda la contraseña de la base; usa **Generate password** o solo letras y números, porque `@ # / : %` rompen la cadena de conexión. Este backend no usa la Data API de Supabase: puedes desactivar **Enable Data API** y **Automatically expose new tables**, y activar **Enable automatic RLS**.
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

```powershell
cd frontend
npm test
```

Las del frontend simulan la API: no necesitan el backend ni la base de datos.

## Estructura

```
backend/
  app/
    main.py          API (endpoints)
    kpis.py          motor analítico: indicadores, tendencias, semáforo
    narrativa.py     motor de narrativa: hechos, prompt, reintentos
    guardrails.py    validación de lo que redacta la IA
    llm.py           proveedores de IA (Ollama, Groq) y candado de datos
    trabajos.py      generación de narrativas en segundo plano, revisión y bitácora
    avisos.py        avisos por persona y correo opcional sin datos
    programacion.py  programación mensual (hilo de la API y script)
    umbrales.py      edición de umbrales con bitácora
    exportar.py      reporte aprobado en PDF y presentación
    seguridad.py     inicio de sesión, contraseñas, tokens y permisos por rol
    database.py      conexión a PostgreSQL (local o Supabase)
  scripts/           seed, crear_usuario, programar, generar_narrativa, evaluar_narrativa
  tests/             pruebas automáticas
  reportes/          resultados de las evaluaciones del modelo de IA
frontend/
  src/
    api.js           cliente de la API (token de sesión y errores)
    sesion.jsx       inicio y cierre de sesión, permisos por rol
    formato.js       cifras, fechas, semáforo y variaciones
    paginas/         Login, Tablero, Narrativas, DetalleNarrativa, Avisos, Configuracion
    componentes/     tarjetas de KPI, gráfica de tendencia, vista del reporte
    pruebas/         pruebas automáticas (Vitest) con una API simulada
db/                  esquema y tablas (SQL)
docs/PRD.md          documento de requerimientos del producto
```
