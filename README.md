# Talentia Insights

**Analítica de Recursos Humanos con IA responsable.** Talentia Insights consolida lo que exportan los sistemas de RRHH (reclutamiento, nómina, desempeño, capacitación, clima laboral y productividad), calcula los indicadores con su semáforo y redacta con IA el reporte ejecutivo de cada área y mes, que una persona de RRHH aprueba antes de distribuirse.

La demostración corre con **Nordika Logística**, una empresa ficticia: operador logístico en Guadalajara con unas 350 personas en Operaciones, Ventas, Transporte, Finanzas, Almacén y Jurídico, y 24 meses de historia.

- **Carga de datos:** RRHH sube el Excel o CSV que exporta cada sistema. Se valida completo (todo o nada), se descartan los datos personales, se concilia contra la base y queda en bitácora con la huella del archivo.
- **Motor analítico (sin IA):** calcula los indicadores con SQL y pandas, de forma reproducible y verificada con pruebas.
- **Motor de narrativa (con IA):** el modelo redacta **solo** a partir de los indicadores ya calculados. Unos guardarrailes rechazan cifras inventadas, causas no demostradas y alertas omitidas.
- **Seguridad:** verificación en dos pasos obligatoria para Dirección, TI y RRHH; acceso por rol y área; contraseñas temporales; bloqueo por intentos; bitácoras de cuentas, umbrales, reportes y cargas; IA local que no saca los datos del servidor.
- **Revisión humana y distribución:** nadie aprueba lo que pidió; los aprobados se descargan en PDF y presentación.
- **Avisos y programación mensual:** alertas de indicadores en rojo y de reportes por revisar; los reportes del mes se pueden generar solos.

> Todos los datos son **ficticios** (generados por `scripts/seed.py`). No contienen información de personas reales.

## Demostración

La demostración recorre el sistema completo como en producción. Ninguna medida de seguridad se apaga: se pide la verificación en dos pasos, cuentan los intentos fallidos y todo queda en las bitácoras. Para que se pueda probar sin celular, un **teléfono simulado en pantalla** muestra la app de autenticación con el código vigente, con la leyenda de que en producción solo aparece en el celular de cada persona.

1. Haz la instalación local (abajo) y, en tu `.env`, pon:
   ```
   MODO_DATOS=sinteticos
   MODO_DEMO=si
   ```
2. Crea las cuentas de prueba (con la API apagada o encendida):
   ```powershell
   python -m scripts.demo
   ```
3. Abre el tablero. La pantalla de inicio muestra las cuentas y su contraseña (`Demo-RRHH-2026`). Pulsa **Usar** junto a una cuenta y luego **Entrar**.

| Cuenta | Persona | Para mostrar |
|---|---|---|
| `demo_rrhh` | Ana Ríos, Gerente de RRHH | Carga de datos, tablero de todas las áreas, solicitar reportes, umbrales y programación |
| `demo_rrhh2` | Eva Muñoz, Analista de RRHH | Aprobar o rechazar los reportes que pidió Ana (nadie aprueba lo que pidió) |
| `demo_direccion` | Andrea Salinas, Dirección General | Solo el consolidado de la empresa; recibe los reportes aprobados |
| `demo_gerente` | Luis Ortega, Gerente de Ventas | Solo su área; la verificación en dos pasos es opcional |
| `demo_ti` | Carlos Peña, Soporte TI | Administrar cuentas (contraseña temporal, desactivar, reiniciar MFA) sin ver datos de colaboradores |

**Un recorrido sugerido:**
1. Entra como **Ana**: configura la verificación en dos pasos con el QR y el teléfono simulado, y guarda los códigos de respaldo.
2. En **Carga de datos**, descarga los archivos de ejemplo de septiembre de 2026 y súbelos en orden. Vienen como los exporta cada sistema, con nombres de personas incluidos: el sistema los descarta, valida cada fila y, al aplicar, concilia archivo contra base.
3. En el **Tablero** aparece septiembre. Revisa los **Avisos** de indicadores en rojo y **genera el reporte con IA**.
4. Entra como **Eva** para aprobarlo, y como **Andrea** para verlo aprobado y descargarlo en PDF o presentación.
5. Entra como **Carlos** (TI) para crear una cuenta con contraseña temporal y revisar la bitácora de cuentas.

Para dejar las cuentas como nuevas después de una demostración, vuelve a correr `python -m scripts.demo`. Para volver a los datos originales de Nordika, corre `python -m scripts.seed`.

El modo demostración **se niega a funcionar con `MODO_DATOS=reales`**, y nunca muestra el código de una cuenta que no sea `demo_`. Con `MODO_DATOS=sinteticos` también puedes usar Groq para que los reportes salgan en segundos (sección Inteligencia artificial).

## Tecnologías

Python 3.14 · FastAPI · PyOTP (verificación en dos pasos) · openpyxl (Excel) · PostgreSQL 16 (Docker local o Supabase) · pandas · Ollama + Qwen3 8B (IA local) o Groq (IA en la nube, solo con datos sintéticos) · ReportLab (PDF) y python-pptx (presentación) · React + Vite + Recharts · pytest y Vitest

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

# 4. Datos de Nordika Logística (ficticios: 24 meses, 6 áreas)
python -m scripts.seed

# 5. Tu usuario (la contraseña se escribe oculta; mínimo 10 caracteres)
python -m scripts.crear_usuario --usuario admin --nombre "Tu Nombre" --rol rrhh
#    y una cuenta de TI para administrar las demás desde el tablero
python -m scripts.crear_usuario --usuario ti --nombre "Soporte TI" --rol admin_ti

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
| **Carga de datos** (solo RRHH) | Subir el Excel o CSV de cada sistema, revisar la validación y lo que se descarta, aplicar y ver la conciliación. Plantillas y archivos de ejemplo del mes siguiente. Bitácora de cargas con la huella SHA-256 de cada archivo |
| **Configuración** | Umbrales del semáforo con su bitácora de cambios, y programación mensual. Todos la ven; solo RRHH la cambia |
| **Usuarios** | Cuentas y su bitácora. TI las crea, modifica, desactiva y les restablece la contraseña o la verificación en dos pasos; RRHH solo las consulta |
| **Mi cuenta** (tu nombre, arriba a la derecha) | Cambiar tu contraseña y activar la verificación en dos pasos |

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

schtasks /create /tn "Talentia Insights" /sc daily /st 07:00 /tr "cmd /c cd /d C:\ruta\backend && .venv\Scripts\python.exe -m scripts.programar"
```

**Correo (opcional).** Está apagado por defecto. Si llenas `SMTP_HOST` y los demás datos `SMTP_*` en el `.env`, quien tenga correo registrado recibe un correo con "tienes N avisos nuevos" y la liga al sistema. **El correo nunca lleva datos**: ni áreas, ni indicadores, ni cifras. Con Gmail usa `smtp.gmail.com`, puerto `587` y una [contraseña de aplicación](https://myaccount.google.com/apppasswords), nunca tu contraseña normal.

## Usuarios y roles

Lo normal es que **TI administre las cuentas desde la sección Usuarios** del tablero. Al crear una cuenta o restablecer una contraseña, el sistema genera una **contraseña temporal** que se muestra una sola vez; la persona la cambia al entrar. Las cuentas no se borran, se desactivan, y cada cambio queda en la bitácora de cuentas.

**Verificación en dos pasos.** Dirección, TI y RRHH la configuran la primera vez que entran: escanean un QR con una app como Google Authenticator o Microsoft Authenticator y, desde entonces, después de la contraseña escriben el código de 6 dígitos de la app. Al activarla reciben 10 códigos de respaldo de un solo uso. Si alguien pierde el teléfono, TI la reinicia desde Usuarios. Los roles obligados se cambian con `MFA_OBLIGATORIO` en el `.env`.

El script sirve para crear la primera cuenta de TI y como respaldo desde la consola:

```powershell
python -m scripts.crear_usuario --usuario dir  --nombre "Dirección"      --rol direccion
python -m scripts.crear_usuario --usuario luis --nombre "Gerente Ventas" --rol gerente --area Ventas
python -m scripts.crear_usuario --usuario ti   --nombre "Soporte TI"     --rol admin_ti
python -m scripts.crear_usuario --listar
python -m scripts.crear_usuario --usuario luis --cambiar-contrasena   # también desbloquea la cuenta
python -m scripts.crear_usuario --usuario luis --cambiar-correo luis@empresa.com   # "" lo quita
python -m scripts.crear_usuario --usuario ti --reiniciar-mfa          # si TI perdió su teléfono
```

Al crear un usuario puedes agregar `--correo` para que reciba el correo de avisos.

| Rol | Ve |
|---|---|
| `direccion` | Solo el consolidado corporativo |
| `rrhh` | Todo; aprueba o rechaza los reportes que solicitó otra persona; cambia umbrales y programación |
| `gerente` | Solo su área |
| `admin_ti` | Administra las cuentas; ve la configuración sin cambiarla; sin datos de colaboradores ni avisos |

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
    seguridad.py     inicio de sesión, cuentas con bitácora, contraseñas, tokens y permisos por rol
    mfa.py           verificación en dos pasos (TOTP) y códigos de respaldo
    demo.py          modo demostración: cuentas de prueba y teléfono simulado
    cargas.py        carga de archivos de los sistemas fuente: validación y conciliación
    marca.py         nombre del producto y de la empresa
    database.py      conexión a PostgreSQL (local o Supabase)
  scripts/           seed, crear_usuario, demo, programar, generar_narrativa, evaluar_narrativa
  tests/             pruebas automáticas
  reportes/          resultados de las evaluaciones del modelo de IA
frontend/
  src/
    api.js           cliente de la API (token de sesión y errores)
    sesion.jsx       inicio y cierre de sesión, permisos por rol
    formato.js       cifras, fechas, semáforo y variaciones
    paginas/         Login, Tablero, Narrativas, DetalleNarrativa, Avisos, CargaDatos, Configuracion, Usuarios, Cuenta, Pendiente
    componentes/     tarjetas de KPI, gráfica de tendencia, vista del reporte
    pruebas/         pruebas automáticas (Vitest) con una API simulada
db/                  esquema y tablas (SQL)
```
