# Talentia Insights

[![Pruebas](https://github.com/warsharkt/G19X-ITH-BJTD-223-ACADEMIC/actions/workflows/pruebas.yml/badge.svg)](https://github.com/warsharkt/G19X-ITH-BJTD-223-ACADEMIC/actions/workflows/pruebas.yml)

**Título asignado del proyecto:** Motor Inteligente de Reportes Ejecutivos de RRHH. *Talentia Insights* es el nombre del producto.

**Analítica de Recursos Humanos con IA responsable.** Talentia Insights consolida lo que exportan los sistemas de RRHH (reclutamiento, nómina, desempeño, capacitación, clima laboral y productividad), calcula los indicadores con su semáforo y redacta con IA el reporte ejecutivo de cada área y mes, que una persona de RRHH aprueba antes de distribuirse.

El sistema viene instalado para **Nordika Logística**, operador logístico en Guadalajara con unas 350 personas en Operaciones, Ventas, Transporte, Finanzas, Almacén y Jurídico. Arranca con 24 meses de historia (septiembre de 2024 a agosto de 2026), y la Analista de RRHH carga cada mes nuevo desde **Carga de datos**.

- **Carga de datos:** la Analista de RRHH sube el Excel o CSV que exporta cada sistema. Se valida completo (todo o nada), se descartan los datos personales, se concilia contra la base y queda en bitácora con la huella del archivo.
- **Motor analítico (sin IA):** calcula los indicadores con SQL y pandas, de forma reproducible y verificada con pruebas.
- **Motor de narrativa (con IA):** el modelo redacta **solo** a partir de los indicadores ya calculados. Unos guardarrailes rechazan cifras inventadas, causas no demostradas y alertas omitidas.
- **Seguridad:** verificación en dos pasos obligatoria para Dirección, TI y RRHH; acceso por rol y área; contraseñas temporales; bloqueo por intentos; bitácoras de cuentas, umbrales, reportes y cargas; IA local que no saca los datos del servidor.
- **Quien prepara no firma:** la Analista de RRHH carga los datos y genera los reportes; la Responsable de RRHH los firma (con suplente si no está y una Nota de RRHH opcional). Dirección y los gerentes los piden a RRHH. Cada reporte dice quién lo firmará, y los firmados se descargan en PDF y presentación.
- **Avisos y programación mensual:** alertas de indicadores en rojo, pedidos y reportes por firmar; los reportes del mes se pueden generar solos.

> Nordika Logística y sus datos son ficticios (`scripts/seed.py`) y no corresponden a personas reales. Dentro del sistema se tratan como los datos de la empresa: para usarlo en otra, se cambian todos (ver [Usarlo con los datos de otra empresa](#usarlo-con-los-datos-de-otra-empresa)).

**Para quien lo usa:** la [Guía de funcionamiento](docs/GUIA.md) explica cada pantalla, qué archivos se suben, cómo se calcula cada indicador y por qué, y quién prepara y firma los reportes.

## Cuentas de Nordika

La pantalla de inicio es la de producción: no muestra cuentas ni contraseñas. Estas son las cuentas del personal de Nordika. Todas usan la contraseña inicial **`Nordika-2026`**, que se cambia con `DEMO_CONTRASENA` en el `.env`.

| Usuario | Persona | Qué hace |
|---|---|---|
| `eva.munoz` | Eva Muñoz, Analista de RRHH | Carga los datos de cada mes y genera los reportes con IA; ve a quién se le enviarán para su firma |
| `ana.rios` | Ana Ríos, Responsable de RRHH | Firma (aprueba o rechaza) los reportes con una Nota de RRHH; designa suplente; umbrales y programación |
| `andrea.salinas` | Andrea Salinas, Dirección General | Solo el consolidado; recibe los reportes firmados y puede pedir uno a RRHH |
| `luis.ortega` | Luis Ortega, Gerente de Ventas | Solo su área; recibe su reporte firmado y puede pedir uno a RRHH |
| `carlos.pena` | Carlos Peña, Soporte TI | Administra las cuentas y asigna quién firma, sin ver datos de colaboradores |

Se entra como en producción: usuario, contraseña y código de verificación en dos pasos. Ninguna medida de seguridad se apaga. La primera vez, Dirección, RRHH y TI configuran la verificación (escanean el QR) y guardan sus códigos de respaldo. Para no necesitar un celular, un **teléfono simulado** junto al formulario muestra el código. La pantalla aclara que no es parte del sistema: es una simulación de la app que cada persona tendría en su propio celular.

Las cuentas se crean solas al arrancar con Docker (en modo desarrollo: `python -m scripts.demo`). Para eso se necesita `MODO_DATOS=sinteticos` y `MODO_DEMO=si` en el `.env`. El modo **se niega a funcionar con `MODO_DATOS=reales`** y nunca muestra el código de otra cuenta. Si tu base tiene las cuentas `demo_*` de una versión anterior, el script las renombra y conserva su historial.

**Un recorrido sugerido** (para cambiar de persona, cierra sesión y entra con la siguiente cuenta):

1. Entra como **Andrea** (Dirección) y, en **Reportes**, pide a RRHH el reporte del último mes.
2. Entra como **Eva** (Analista). Antes de generar, sube en **Carga de datos** los seis archivos de septiembre de 2026, el mes pendiente: el sistema valida cada fila, descarta las columnas con datos personales (como nombres) y concilia el archivo contra la base. Después, el aviso del pedido abre el formulario con el área y el mes ya elegidos. Genera el reporte; la pantalla dice que se enviará a Ana para su firma.
3. Entra como **Ana** (Responsable): el aviso "listo para tu firma" lleva al reporte. Apruébalo con una Nota de RRHH, o recházalo con motivo.
4. Vuelve a entrar como **Andrea** para verlo firmado y descargarlo en PDF o presentación, con la Nota de RRHH.
5. Entra como **Carlos** (TI) para crear una cuenta con contraseña temporal y revisar la bitácora de cuentas.

Para dejar las cuentas como nuevas, vuelve a correr `python -m scripts.demo`. Para volver a los datos iniciales de Nordika, corre `python -m scripts.seed`. Con `MODO_DATOS=sinteticos` también puedes usar Groq para que los reportes salgan en segundos (sección [Inteligencia artificial](#inteligencia-artificial)).

## Usarlo con los datos de otra empresa

Nada de Nordika está fijo en el código: el nombre sale de `EMPRESA_NOMBRE`, y las áreas, las personas y los indicadores salen de la base. Para instalarlo en una empresa real:

1. En el `.env`, pon `EMPRESA_NOMBRE` con el nombre de la empresa, `MODO_DATOS=reales` y `MODO_DEMO=no`. Así se apagan las cuentas de Nordika, el teléfono simulado y la IA en la nube; los reportes los redacta Ollama en el propio servidor. Fija también `MFA_LLAVE` (cómo generarla viene en `.env.example`) y guárdala aparte de los respaldos de la base.
2. Parte de una base vacía: `docker compose down -v` y luego `docker compose up -d --build`. Con `MODO_DATOS=reales` no se siembra nada.
3. Crea la primera cuenta de TI con `python -m scripts.crear_usuario` (sección [Usuarios y roles](#usuarios-y-roles)). Desde el tablero, TI crea las cuentas del personal con contraseña temporal y asigna quién firma.
4. La Analista de RRHH sube desde **Carga de datos** lo que exporta cada sistema: plantilla de personal, vacantes, metas, capacitación, clima y productividad. Las plantillas de columnas están en la misma pantalla.
5. La Responsable de RRHH revisa los umbrales en **Configuración** antes del primer reporte.

## Tecnologías

Python 3.14 · FastAPI · PyOTP (verificación en dos pasos) · openpyxl (Excel) · PostgreSQL 16 (Docker local o Supabase) · pandas · Ollama + Qwen3 8B (IA local) o Groq (IA en la nube, solo con datos sintéticos) · ReportLab (PDF) y python-pptx (presentación) · React + Vite + Recharts · pytest y Vitest

## Cómo levantarlo

Solo necesitas [Docker Desktop](https://www.docker.com/products/docker-desktop/) y Git. No hace falta instalar Python ni Node. Los comandos son para PowerShell en Windows.

**1. Descarga el proyecto y crea tu configuración:**

```powershell
git clone https://github.com/warsharkt/G19X-ITH-BJTD-223-ACADEMIC.git
cd G19X-ITH-BJTD-223-ACADEMIC
copy .env.example .env
```

**2. Abre el `.env` y cambia estas tres líneas:**

```
POSTGRES_PASSWORD=una-contraseña-tuya
MODO_DATOS=sinteticos
MODO_DEMO=si
```

**3. Abre Docker Desktop, espera a que diga que está corriendo y levanta todo:**

```powershell
docker compose up -d --build
```

La primera vez tarda unos minutos: descarga lo necesario, arma la API y el tablero y carga los datos iniciales de Nordika. Después abre **http://localhost:8080** y entra con una de las [cuentas de Nordika](#cuentas-de-nordika).

- **IA para redactar los reportes:** instala [Ollama](https://ollama.com), corre `ollama pull qwen3:8b` y deja la app abierta. Sin Ollama todo funciona menos generar reportes, que quedan en error con el motivo. Con datos sintéticos también puedes usar Groq (sección [Inteligencia artificial](#inteligencia-artificial)).
- **Apagar y volver a encender:** `docker compose stop` y `docker compose up -d`. Los datos se conservan.
- **Empezar de cero:** `docker compose down -v` borra la base; al volver a levantarlo se cargan otra vez los datos de Nordika.
- **Solo desde este equipo:** el tablero (8080), la API (8000) y la base (5433) solo aceptan conexiones de la misma computadora. Para usar el tablero desde otras computadoras de la empresa, mira [Abrirlo a la red de la empresa](#abrirlo-a-la-red-de-la-empresa-https).
- **Documentación de la API:** http://localhost:8000/docs.
- **Si cambias el código:** vuelve a correr `docker compose up -d --build`.

### Abrirlo a la red de la empresa (HTTPS)

Para que otras computadoras entren al tablero, pon en el `.env` la dirección del equipo en la red:

```
WEB_ESCUCHA=192.168.1.20   # la IP de este equipo en la red de la empresa
WEB_NOMBRE=192.168.1.20    # el nombre o la IP con que lo van a abrir
APP_URL=https://192.168.1.20:8443
```

y corre `docker compose up -d --build`. En cuanto el tablero se abre a la red, **HTTPS se activa solo**: se entra por **https://192.168.1.20:8443** y el puerto 8080 redirige ahí, así que contraseñas, códigos y datos viajan cifrados (TLS 1.2 o 1.3). Si alguien pone `WEB_HTTPS=no` con el tablero abierto a la red, el contenedor se niega a arrancar.

- **Certificado:** pon el de la empresa en `certs/talentia.crt` y `certs/talentia.key`. Si no hay, se genera uno autofirmado para `WEB_NOMBRE`; funciona, pero el navegador avisa que no lo reconoce hasta que TI lo instale como confiable en cada equipo. `certs/` nunca se sube a GitHub.
- **Solo el tablero:** la API (`API_ESCUCHA`) y la base (`DB_ESCUCHA`) se quedan en `127.0.0.1`. El tablero ya le pasa a la API todo lo de `/api`, y por HTTPS.
- `WEB_HTTPS=si` fuerza HTTPS también en este equipo; `WEB_PUERTO_HTTPS` cambia el 8443.

### Modo desarrollo (para programar)

Para ver los cambios al instante, primero haz la [instalación local](#instalación-local) y el [tablero web](#tablero-web-frontend). Luego deja en Docker solo la base y abre tres terminales de PowerShell en la raíz del proyecto:

| Terminal | Comando | Queda en |
|---|---|---|
| 1. Base de datos | `docker compose stop api web` (si estaban encendidos) y `docker compose up -d db` | `localhost:5433` (solo desde este equipo) |
| 2. API | `cd backend; .venv\Scripts\Activate.ps1; python -m uvicorn app.main:app --reload` | http://localhost:8000/docs |
| 3. Tablero | `cd frontend; npm run dev` | http://localhost:5173 |

- **Comprueba que todo responde:** http://localhost:8000/health debe decir `{"status":"ok","database":"ok"}`.
- **Base de datos:** PostgreSQL en Docker, como lo instalaría la empresa en su propio servidor. Supabase (`DATABASE_URL`) queda solo para publicar una demo en línea con datos sintéticos; nunca para datos reales.
- **Para apagar:** Ctrl+C en las terminales 2 y 3, y `docker compose stop` para la base.

### Problemas comunes

| Síntoma | Qué hacer |
|---|---|
| `docker compose` dice que no encuentra Docker | Abre Docker Desktop y espera a que diga que está corriendo. |
| `docker compose up` dice que el puerto 8000, 8080 o 5433 ya está ocupado | Apaga la API o el tablero del modo desarrollo (Ctrl+C) u otro programa que use ese puerto, y vuelve a intentarlo. |
| La API no arranca y `docker compose logs api` dice `password authentication failed` | Cambiaste `POSTGRES_PASSWORD` después de la primera vez: la base guarda la contraseña original. Vuelve a la anterior, o empieza de cero con `docker compose down -v` (borra los datos). |
| El navegador dice que la conexión no es privada | Es el certificado autofirmado. Pon el de la empresa en `certs/` y corre `docker compose up -d --build`, o pide a TI que instale `certs/talentia.crt` como confiable. |
| `rrhh_web` se reinicia y `docker compose logs web` dice "lo dejaria sin cifrar" | Abriste el tablero a la red con `WEB_HTTPS=no`. Quita esa línea del `.env` (o pon `auto`) para que use HTTPS. |
| La página http://localhost:8080 no abre | Revisa con `docker compose ps` que los tres servicios digan `Up`; si no, mira el motivo con `docker compose logs api`. |
| `/health` o `pytest` dicen que no se pudo conectar a PostgreSQL | Abre Docker Desktop, corre `docker compose up -d db` y revisa con `docker compose ps` que el estado sea `healthy`. |
| `pytest` dice que las pruebas apuntan a una base **remota** | Comenta `DATABASE_URL` en el `.env`: las pruebas solo corren contra el PostgreSQL local. |
| Con Supabase, la API tarda y falla al conectar | El proyecto gratuito se pausa tras 7 días sin uso: reactívalo desde el panel de Supabase. |
| El tablero dice "No se pudo conectar con la API" | Enciende la API (terminal 2). Si corre en otra dirección, ajusta `VITE_API_URL` en `frontend/.env`. |
| El reporte queda en **error** porque el modelo no está disponible | Abre Ollama y corre `ollama pull qwen3:8b`, o usa Groq con `MODO_DATOS=sinteticos`. Luego vuelve a solicitar el reporte. |
| Al escribir el código dice "No se pudo leer la verificación en dos pasos de tu cuenta" | Cambió o se perdió la llave del MFA (`MFA_LLAVE` o `llaves/mfa.key`). Vuelve a poner la anterior. Si no la tienes, entra con un código de respaldo o pide a TI que reinicie la verificación; con las cuentas de Nordika basta `python -m scripts.demo`. |
| `eva.munoz` (u otra cuenta de Nordika) dice "Usuario o contraseña incorrectos" | Pon `MODO_DATOS=sinteticos` y `MODO_DEMO=si` en el `.env` y corre `docker compose up -d` (con Docker se crean al arrancar). En modo desarrollo: `python -m scripts.demo`. Después de correr `pytest`, vuelve a correr `python -m scripts.demo`: las pruebas borran esas cuentas. |

## Instalación local

Solo para el [modo desarrollo](#modo-desarrollo-para-programar); para usar el sistema basta con Docker ([Cómo levantarlo](#cómo-levantarlo)). Necesitas [Python 3.14](https://www.python.org/downloads/), [Docker Desktop](https://www.docker.com/products/docker-desktop/) y Git.

```powershell
git clone https://github.com/warsharkt/G19X-ITH-BJTD-223-ACADEMIC.git
cd G19X-ITH-BJTD-223-ACADEMIC

# 1. Configuración: copia el ejemplo y edítalo
copy .env.example .env
#    - cambia POSTGRES_PASSWORD
#    - genera JWT_SECRETO con:  python -c "import secrets; print(secrets.token_urlsafe(48))"

# 2. Base de datos (solo PostgreSQL en Docker)
docker compose up -d db

# 3. Entorno de Python
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 4. Datos iniciales de Nordika Logística (24 meses, 6 áreas)
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
| **Reportes** | La Analista prepara el reporte con IA de un área y mes y ve el avance mientras se redacta; Dirección y los gerentes se lo piden a RRHH. La Responsable lo aprueba (con Nota de RRHH opcional) o lo rechaza. Descarga de los aprobados en PDF o presentación e historial consultable por área, mes y firma |
| **Avisos** | Indicadores en rojo, pedidos de reportes, reportes por firmar y reportes aprobados o rechazados de tus áreas. El menú muestra cuántos faltan por leer |
| **Carga de datos** (solo la Analista de RRHH) | Subir el Excel o CSV de cada sistema, revisar la validación y lo que se descarta, aplicar y ver la conciliación. Plantillas y archivos del mes pendiente (hoy, septiembre 2026). Bitácora de cargas con la huella SHA-256 de cada archivo |
| **Configuración** | Umbrales del semáforo con su bitácora de cambios, y programación mensual. Todos la ven. Los umbrales los cambia solo la Responsable de RRHH; la programación, cualquiera de RRHH |
| **Usuarios** | Cuentas y su bitácora. TI las crea, modifica, desactiva y les restablece la contraseña o la verificación en dos pasos; RRHH solo las consulta |
| **Mi cuenta** (tu nombre, arriba a la derecha) | Cambiar tu contraseña y activar la verificación en dos pasos |

Cada rol ve solo lo suyo: Dirección no puede cambiar de área, y TI solo ve la configuración, sin poder cambiarla. La API aplica los mismos permisos, así que no dependen de la interfaz. La sesión se guarda solo en la pestaña (`sessionStorage`) y se cierra sola cuando el token vence.

**Diseño claro u oscuro.** El botón de sol o luna, arriba a la derecha y en la pantalla de inicio, cambia entre el diseño claro (blanco) y el oscuro. La primera vez sigue al sistema operativo; después se recuerda lo que elegiste en ese navegador. Lo único que se guarda en `localStorage` es esa preferencia visual, nunca datos ni el token de sesión.

## Inteligencia artificial

La narrativa siempre la redacta un modelo. Hay dos opciones, y se elige en el `.env`:

| Opción | Configuración | Cuándo usarla |
|---|---|---|
| **Ollama local** (por defecto) | Instala [Ollama](https://ollama.com), ejecuta `ollama pull qwen3:8b` y deja `LLM_PROVEEDOR=ollama` | Datos reales: nada sale de tu equipo. En CPU tarda de 2 a 5 minutos por reporte |
| **Groq** (nube, gratis) | Crea una llave en https://console.groq.com/keys y pon `LLM_PROVEEDOR=groq`, `MODO_DATOS=sinteticos` y `GROQ_API_KEY=...` | Para revisar el proyecto rápido: responde en segundos. **Solo con datos sintéticos**; el sistema se niega a usarla si `MODO_DATOS` no es `sinteticos` |

Los reportes se generan en segundo plano: `POST /narrativas` devuelve un id y `GET /narrativas/{id}` muestra el resultado cuando está listo.

### Revisión antes de distribuir

Todo reporte nace **pendiente de firma** y dice quién lo firmará. La Responsable de RRHH (o su suplente) lo **aprueba**, con una Nota de RRHH opcional, o lo **rechaza** con motivo desde la pantalla del reporte (o con `POST /narrativas/{id}/revision`). Nadie firma lo que pidió. La decisión es definitiva y queda registrada con usuario, fecha y comentario. Si se rechaza, se solicita uno nuevo.

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

## Respaldos

Un respaldo que nunca se probó no sirve, así que **cada respaldo se prueba**: el script lo restaura en una base temporal y compara las filas de cada tabla con la base real. Si no cuadra, termina con error.

```powershell
cd backend
python -m scripts.respaldo                        # respalda la base y prueba restaurarlo
python -m scripts.respaldo --llave E:\Talentia    # además copia la llave del MFA a otra unidad
python -m scripts.respaldo --ver                  # lista los respaldos
python -m scripts.respaldo --restaurar ..\respaldos\talentia-20261027-020000.dump
```

- Los respaldos van en `respaldos/` (o en `RESPALDOS_DIR`), cada uno con su huella SHA-256. Se conservan los últimos 30 (`RESPALDOS_CONSERVAR`).
- Usa el `pg_dump` de adentro del contenedor `rrhh_db`: no hace falta instalar PostgreSQL en el equipo.
- **La llave del MFA nunca va en el respaldo.** Cópiala con `--llave` a otra unidad o a una USB; el script se niega a guardarla junto a los respaldos. Así, quien se lleve un respaldo no puede generar códigos de verificación.
- **Restaurar** reemplaza toda la base. Primero apaga la API (`docker compose stop api`), escribe el nombre de la base para confirmar y el script guarda antes una copia del estado actual (`antes-de-restaurar-…`). Verifica la huella antes de tocar nada.
- Con datos reales, los respaldos tienen datos de colaboradores: guárdalos en un disco cifrado y con acceso solo para TI.

Para respaldar todos los días a las 2:00 con el Programador de tareas de Windows (cambia la ruta):

```powershell
schtasks /create /tn "Talentia Insights respaldo" /sc daily /st 02:00 /tr "cmd /c cd /d C:\ruta\backend && .venv\Scripts\python.exe -m scripts.respaldo"
```

## Usuarios y roles

Lo normal es que **TI administre las cuentas desde la sección Usuarios** del tablero. Al crear una cuenta o restablecer una contraseña, el sistema genera una **contraseña temporal** que se muestra una sola vez; la persona la cambia al entrar. Las cuentas no se borran, se desactivan, y cada cambio queda en la bitácora de cuentas.

**Verificación en dos pasos.** Dirección, TI y RRHH la configuran la primera vez que entran: escanean un QR con una app como Google Authenticator o Microsoft Authenticator y, desde entonces, después de la contraseña escriben el código de 6 dígitos de la app. Al activarla reciben 10 códigos de respaldo de un solo uso. Si alguien pierde el teléfono, TI la reinicia desde Usuarios. Los roles obligados se cambian con `MFA_OBLIGATORIO` en el `.env`.

El secreto de la app de cada cuenta se guarda **cifrado** (AES-256) con una llave que no está en la base: `MFA_LLAVE` en el `.env` o, si no la pones, el archivo `llaves/mfa.key`, que se crea solo la primera vez (Docker y el modo desarrollo usan el mismo). Así, quien obtenga una copia de la base no puede generar códigos. **Respalda la llave aparte de la base**: si se pierde, solo sirven los códigos de respaldo y TI tiene que reiniciar la verificación de cada cuenta.

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
| `rrhh` | Todo. La Analista carga los datos y genera los reportes; la Responsable (la marca TI) los firma, nunca los que pidió, y es la única que cambia los umbrales. Cualquiera de RRHH cambia la programación |
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

**En GitHub** corren solas en cada push a `Main` y en cada pull request (`.github/workflows/pruebas.yml`): el backend contra un PostgreSQL vacío que se llena con `scripts/seed.py`, y el frontend con sus pruebas y la compilación del tablero. El resultado aparece en la pestaña **Actions** y junto a cada commit (✓ o ✗).

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
    mfa.py           verificación en dos pasos (TOTP), secreto cifrado y códigos de respaldo
    demo.py          modo demostración: cuentas del personal de Nordika y teléfono simulado
    cargas.py        carga de archivos de los sistemas fuente: validación y conciliación
    marca.py         nombre del producto y de la empresa
    database.py      conexión a PostgreSQL (local o Supabase)
    firmas.py        quién firma cada reporte, suplencias
  scripts/           seed, arranque (Docker), crear_usuario, demo, programar, respaldo, generar_narrativa, evaluar_narrativa
  Dockerfile         imagen de la API
  tests/             pruebas automáticas
  reportes/          resultados de las evaluaciones del modelo de IA
frontend/
  src/
    api.js           cliente de la API (token de sesión y errores)
    sesion.jsx       inicio y cierre de sesión, permisos por rol
    formato.js       cifras, fechas, semáforo y variaciones
    tema.js          diseño claro u oscuro (preferencia del navegador)
    paginas/         Login, Tablero, Narrativas, DetalleNarrativa, Avisos, CargaDatos, Configuracion, Usuarios, Cuenta, Pendiente
    componentes/     tarjetas de KPI, gráfica de tendencia, vista del reporte, botón de diseño
    pruebas/         pruebas automáticas (Vitest) con una API simulada
  Dockerfile         imagen del tablero (compilado y servido por nginx)
  nginx/             sirve el tablero, reenvía /api a la API y elige HTTP o HTTPS al arrancar
db/                  esquema y tablas (SQL)
docs/GUIA.md         guía de funcionamiento para quien usa el sistema
llaves/              llave que cifra los secretos del MFA (se crea sola; no se sube a GitHub)
respaldos/           respaldos de la base (python -m scripts.respaldo; no se suben a GitHub)
docker-compose.yml   base de datos, API y tablero
.github/workflows/   pruebas automáticas en GitHub (integración continua)
```
