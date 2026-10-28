# Talentia Insights

[![Pruebas](https://github.com/warsharkt/G19X-ITH-BJTD-223-ACADEMIC/actions/workflows/pruebas.yml/badge.svg)](https://github.com/warsharkt/G19X-ITH-BJTD-223-ACADEMIC/actions/workflows/pruebas.yml)

**Analítica de Recursos Humanos con IA responsable.** Talentia Insights consolida lo que exportan los sistemas de RRHH (nómina, reclutamiento, desempeño, capacitación, clima laboral y productividad), calcula los indicadores con su semáforo y redacta con IA el reporte ejecutivo de cada área y mes. Una persona de RRHH lo firma antes de que llegue a Dirección.

> **Proyecto académico.** Título asignado: *Motor Inteligente de Reportes Ejecutivos de RRHH*; *Talentia Insights* es el nombre del producto. Viene con los datos de **Nordika Logística**, una empresa ficticia (unas 350 personas, 6 áreas y 24 meses de historia, de septiembre de 2024 a agosto de 2026) generada por `scripts/seed.py`. Ningún dato corresponde a personas reales.

## Contenido

- [Qué hace](#qué-hace)
- [Tecnologías](#tecnologías)
- [Inicio rápido](#inicio-rápido)
- [Cuentas de prueba](#cuentas-de-prueba)
- [Configuración](#configuración)
- [Usarlo con los datos de otra empresa](#usarlo-con-los-datos-de-otra-empresa)
- [Seguridad](#seguridad)
- [Inteligencia artificial](#inteligencia-artificial)
- [Operación](#operación): red de la empresa, avisos y programación, respaldos y cuentas
- [Desarrollo](#desarrollo): instalación local, pruebas y Supabase
- [Problemas comunes](#problemas-comunes)
- [Estructura](#estructura)
- [Documentación](#documentación)

## Qué hace

- **Carga de datos:** la Analista de RRHH sube el Excel o CSV que exporta cada sistema. Se valida completo (todo o nada), se descartan los datos personales, se concilia contra la base y queda en bitácora con la huella del archivo.
- **Motor analítico (sin IA):** calcula los indicadores con SQL y pandas, de forma reproducible y verificada con pruebas.
- **Motor de narrativa (con IA):** el modelo redacta **solo** a partir de los indicadores ya calculados. Unos guardarrailes rechazan cifras inventadas, causas no demostradas y alertas omitidas.
- **Quien prepara no firma:** la Analista carga los datos y genera los reportes; la Responsable de RRHH los firma (con suplente si no está y una Nota de RRHH opcional). Dirección y los gerentes los piden a RRHH, y los firmados se descargan en PDF y presentación.
- **Avisos y programación mensual:** alertas de indicadores en rojo, pedidos y reportes por firmar; los reportes de cada mes completo se pueden generar solos.
- **Seguridad:** verificación en dos pasos, acceso por rol y área, bitácoras de todo y una IA local que no saca los datos del servidor (ver [Seguridad](#seguridad)).

| Sección del tablero | Qué hace |
|---|---|
| **Tablero** | Indicadores del mes con semáforo (siempre con icono y texto), variación contra el mes y el año anterior, y la tendencia con sus umbrales. Los filtros quedan en la dirección de la página, así que se pueden compartir |
| **Reportes** | La Analista prepara el reporte con IA de un área y mes; Dirección y los gerentes se lo piden a RRHH. La Responsable lo aprueba o lo rechaza. Descarga de los aprobados en PDF o presentación |
| **Avisos** | Indicadores en rojo, pedidos, reportes por firmar, aprobados o rechazados. El menú muestra cuántos faltan por leer |
| **Carga de datos** (solo la Analista) | Subir lo que exporta cada sistema, revisar la validación, aplicar y ver la conciliación. Cada fuente dice qué reporte exportar y trae su formato vacío. Bitácora con la huella SHA-256 de cada archivo |
| **Configuración** | Umbrales del semáforo con su bitácora y programación mensual. Los umbrales los cambia solo la Responsable; la programación, cualquiera de RRHH |
| **Usuarios** | TI crea, modifica y desactiva cuentas, y restablece contraseñas o la verificación en dos pasos; RRHH solo consulta |
| **Mi cuenta** | Cambiar tu contraseña y activar la verificación en dos pasos |

Cada rol ve solo lo suyo, y la API aplica los mismos permisos, así que no dependen de la interfaz. La [Guía de funcionamiento](docs/GUIA.md) explica cada pantalla, qué archivos se suben, cómo se calcula cada indicador y por qué.

## Tecnologías

| Parte | Con qué |
|---|---|
| API | Python 3.14, FastAPI, pandas, PyOTP (verificación en dos pasos), openpyxl (Excel), ReportLab (PDF), python-pptx (presentación) |
| Base de datos | PostgreSQL 16 en Docker (Supabase solo para demos con datos sintéticos) |
| IA | Ollama + Qwen3 8B en el propio equipo; Groq en la nube, solo con datos sintéticos |
| Tablero | React, Vite y Recharts, servido por nginx |
| Pruebas | pytest, Vitest y GitHub Actions |

## Inicio rápido

Solo necesitas [Docker Desktop](https://www.docker.com/products/docker-desktop/) y Git; no hace falta instalar Python ni Node. Los comandos son para PowerShell en Windows.

**1. Descarga el proyecto y crea tu configuración:**

```powershell
git clone https://github.com/warsharkt/G19X-ITH-BJTD-223-ACADEMIC.git
cd G19X-ITH-BJTD-223-ACADEMIC
copy .env.example .env
```

**2. Abre el `.env` y cambia estas cuatro líneas.** Las contraseñas las eliges tú; el `.env` nunca se sube a GitHub.

```
POSTGRES_PASSWORD=<una contraseña para la base>
MODO_DATOS=sinteticos
MODO_DEMO=si
DEMO_CONTRASENA=<la contraseña de las cuentas de prueba, mínimo 10 caracteres>
```

**3. Abre Docker Desktop, espera a que diga que está corriendo y levanta todo:**

```powershell
docker compose up -d --build
```

La primera vez tarda unos minutos: arma la API y el tablero y carga los datos de Nordika. Después abre **http://localhost:8080** y entra con una de las [cuentas de prueba](#cuentas-de-prueba).

- **IA para redactar los reportes:** instala [Ollama](https://ollama.com), corre `ollama pull qwen3:8b` y deja la app abierta. Sin Ollama todo funciona menos generar reportes, que quedan en error con el motivo.
- **Apagar y volver a encender:** `docker compose stop` y `docker compose up -d`. Los datos se conservan.
- **Empezar de cero:** `docker compose down -v` borra la base; al volver a levantarlo se cargan otra vez los datos de Nordika.
- **Solo desde este equipo:** el tablero (8080), la API (8000) y la base (5433) solo aceptan conexiones de la misma computadora. Para abrirlo a otras, ve [Red de la empresa](#red-de-la-empresa-https).
- **Documentación de la API:** http://localhost:8000/docs.
- **Si cambias el código:** vuelve a correr `docker compose up -d --build`.

## Cuentas de prueba

Con `MODO_DEMO=si` se crea una cuenta por cada rol del personal de Nordika: Analista de RRHH, Responsable de RRHH, Dirección General, Gerente de Ventas y Soporte TI. Todas usan la contraseña que pusiste en `DEMO_CONTRASENA`. Los usuarios no se publican aquí: aparecen en el registro de arranque.

```powershell
docker compose logs api        # busca "Cuentas de prueba"
```

En modo desarrollo, `python -m scripts.demo` las crea o las deja como nuevas y también las lista.

- **La seguridad funciona igual que en producción.** La pantalla de inicio no muestra cuentas ni contraseñas, y se entra con usuario, contraseña y código de verificación en dos pasos. La primera vez, Dirección, RRHH y TI escanean el QR y guardan sus códigos de respaldo.
- **Teléfono simulado:** para no necesitar un celular, junto al formulario aparece un teléfono que muestra el código. La pantalla aclara que es una simulación de la app que cada persona tendría en su celular. Solo funciona con las cuentas de prueba.
- **Solo con datos de prueba:** el modo demostración se niega a funcionar con `MODO_DATOS=reales` o sin `DEMO_CONTRASENA`.

**Recorrido sugerido** (para cambiar de persona, cierra sesión):

1. Como **Dirección**, en **Reportes**, pide a RRHH el reporte del último mes.
2. Como la **Analista**, sube en **Carga de datos** los seis archivos del mes pendiente (septiembre de 2026; también están en [`datos-de-prueba/`](datos-de-prueba/LEEME.md)). Después, el aviso del pedido abre el formulario con el área y el mes ya elegidos. Genera el reporte.
3. Como la **Responsable**, el aviso "listo para tu firma" lleva al reporte. Apruébalo con una Nota de RRHH, o recházalo con motivo.
4. Otra vez como **Dirección**, descárgalo firmado en PDF o presentación.
5. Como **Soporte TI**, crea una cuenta con contraseña temporal y revisa la bitácora de cuentas.

Para dejar las cuentas como nuevas: `python -m scripts.demo`. Para volver a los datos iniciales: `python -m scripts.seed`.

## Configuración

Todo se configura en el `.env`. [`.env.example`](.env.example) explica cada variable; estas son las principales:

| Variable | Para qué |
|---|---|
| `POSTGRES_PASSWORD` | Contraseña de la base de datos. Si la cambias después de la primera vez, la base conserva la original |
| `MODO_DATOS` | `reales` (por defecto) bloquea cualquier IA en la nube; `sinteticos` solo con los datos de prueba |
| `MODO_DEMO`, `DEMO_CONTRASENA` | Cuentas de prueba y teléfono simulado. Solo con `MODO_DATOS=sinteticos` |
| `EMPRESA_NOMBRE` | Nombre de la empresa en la pantalla de inicio, el menú y los reportes |
| `LLM_PROVEEDOR` | `ollama` (local) o `groq` (nube, solo datos sintéticos) |
| `JWT_SECRETO` | Firma las sesiones. Con Docker, si está vacío se genera uno en cada arranque |
| `MFA_LLAVE` | Cifra el secreto de la verificación en dos pasos. Si está vacía se crea `llaves/mfa.key` |
| `MFA_OBLIGATORIO` | Roles que deben usar verificación en dos pasos (por defecto Dirección, TI y RRHH) |
| `WEB_ESCUCHA`, `WEB_NOMBRE`, `APP_URL` | Abrir el tablero a la red de la empresa con HTTPS |
| `SMTP_*` | Correo opcional de avisos (sin datos) |

## Usarlo con los datos de otra empresa

Nada de Nordika está fijo en el código: el nombre sale de `EMPRESA_NOMBRE`, y las áreas, las personas y los indicadores salen de la base.

1. En el `.env`, pon `EMPRESA_NOMBRE`, `MODO_DATOS=reales` y `MODO_DEMO=no`. Así se apagan las cuentas de prueba, el teléfono simulado y la IA en la nube; los reportes los redacta Ollama en el propio servidor. Fija también `MFA_LLAVE` y guárdala aparte de los respaldos.
2. Parte de una base vacía: `docker compose down -v` y luego `docker compose up -d --build`. Con `MODO_DATOS=reales` no se siembra nada.
3. Crea la primera cuenta de TI con `python -m scripts.crear_usuario` ([Cuentas desde la consola](#cuentas-desde-la-consola)). Desde el tablero, TI crea las demás con contraseña temporal y asigna quién firma.
4. La Analista de RRHH sube desde **Carga de datos** lo que exporta cada sistema: plantilla de personal, vacantes, metas, capacitación, clima y productividad. Cada fuente dice qué reporte exportar y trae su formato vacío.
5. La Responsable de RRHH revisa los umbrales en **Configuración** antes del primer reporte.

## Seguridad

| Medida | Cómo |
|---|---|
| Acceso | Rol y área en cada endpoint de la API; Dirección solo ve el consolidado, cada gerente solo su área y TI no ve datos de colaboradores |
| Contraseñas | Mínimo 10 caracteres, guardadas con scrypt. TI genera temporales que la persona cambia al entrar. Bloqueo tras 5 intentos fallidos |
| Verificación en dos pasos | Código de 6 dígitos (TOTP) obligatorio para Dirección, TI y RRHH, con 10 códigos de respaldo. El secreto se guarda cifrado (AES-256) con una llave que no está en la base |
| Datos personales | La carga descarta nombres, CURP, RFC, correos y demás; el sistema solo conoce códigos de empleado |
| IA | Con `MODO_DATOS=reales` solo se permite el modelo local: ningún dato sale del servidor |
| Red | Por defecto solo acepta conexiones del mismo equipo; abierto a la red, HTTPS se activa solo |
| Bitácoras | Cuentas, umbrales, cargas, reportes, firmas y descargas: quién, qué y cuándo. Nunca guardan contraseñas |
| Sesión | Token en `sessionStorage` de la pestaña, que se cierra solo al vencer |

**Nunca se suben a GitHub** (están en `.gitignore`): el `.env` con contraseñas y llaves, `llaves/` (llave del MFA), `certs/` (certificado HTTPS) y `respaldos/`. Este repositorio no contiene usuarios ni contraseñas: cada instalación pone los suyos en su `.env`. Si alguna vez subes un secreto por error, cámbialo de inmediato; borrarlo del repositorio no basta, porque queda en el historial.

## Inteligencia artificial

La narrativa siempre la redacta un modelo, y se elige en el `.env`:

| Opción | Configuración | Cuándo usarla |
|---|---|---|
| **Ollama local** (por defecto) | Instala [Ollama](https://ollama.com), corre `ollama pull qwen3:8b` y deja `LLM_PROVEEDOR=ollama` | Datos reales: nada sale del equipo. En CPU tarda de 2 a 5 minutos por reporte |
| **Groq** (nube) | Crea una llave en https://console.groq.com/keys y pon `LLM_PROVEEDOR=groq`, `MODO_DATOS=sinteticos` y `GROQ_API_KEY` | Revisar el proyecto rápido: responde en segundos. **Solo con datos sintéticos**: el sistema se niega a usarla con datos reales |

Los reportes se generan en segundo plano: `POST /narrativas` devuelve un id y `GET /narrativas/{id}` muestra el resultado cuando está listo.

**Revisión antes de distribuir.** Todo reporte nace **pendiente de firma** y dice quién lo firmará. La Responsable de RRHH (o su suplente) lo aprueba, con una Nota de RRHH opcional, o lo rechaza con motivo. Nadie firma lo que pidió, y la decisión queda registrada con usuario, fecha y comentario.

**Exportar.** Solo los reportes **aprobados** se descargan (`GET /narrativas/{id}/exportar?formato=pdf|pptx`): PDF tamaño carta o PowerPoint 16:9, con resumen, indicadores, hallazgos, alertas, recomendaciones y un anexo con fórmulas, umbrales y fuentes. Se arma con la narrativa tal como se aprobó, sin recalcular nada, y cada descarga queda registrada.

## Operación

### Red de la empresa (HTTPS)

Para que otras computadoras entren al tablero, pon en el `.env` la dirección del equipo en la red y corre `docker compose up -d --build`:

```
WEB_ESCUCHA=192.168.1.20   # la IP de este equipo en la red de la empresa
WEB_NOMBRE=192.168.1.20    # el nombre o la IP con que lo van a abrir
APP_URL=https://192.168.1.20:8443
```

En cuanto el tablero se abre a la red, **HTTPS se activa solo**: se entra por `https://192.168.1.20:8443` y el puerto 8080 redirige ahí (TLS 1.2 o 1.3). Si alguien pone `WEB_HTTPS=no` con el tablero abierto a la red, el contenedor se niega a arrancar.

- **Certificado:** pon el de la empresa en `certs/talentia.crt` y `certs/talentia.key`. Si no hay, se genera uno autofirmado para `WEB_NOMBRE`; funciona, pero el navegador avisa hasta que TI lo instale como confiable en cada equipo.
- **Solo el tablero se abre:** la API (`API_ESCUCHA`) y la base (`DB_ESCUCHA`) se quedan en `127.0.0.1`; el tablero le pasa a la API todo lo de `/api`.
- `WEB_HTTPS=si` fuerza HTTPS también en este equipo; `WEB_PUERTO_HTTPS` cambia el 8443.

### Avisos y programación mensual

| Aviso | Lo reciben |
|---|---|
| Indicador en rojo del consolidado | Dirección y RRHH |
| Indicador en rojo de un área | El gerente del área y RRHH |
| Reporte listo para revisión | RRHH, menos quien lo pidió |
| Reporte aprobado | Su audiencia y quien lo pidió |
| Reporte rechazado | Quien lo pidió |

**Programación mensual.** En **Configuración**, RRHH la activa y elige el día. Desde ese día se generan los reportes del último mes cerrado (el consolidado y cada área), una sola vez por mes. Si al mes le falta alguna de las cuatro fuentes mensuales (metas, capacitación, clima o productividad), espera a que se suban. Nace **desactivada**, porque con Ollama en CPU cada reporte tarda minutos.

La API revisa al arrancar y cada hora. Para que funcione aunque la API esté apagada, programa el script en el Programador de tareas de Windows (cambia la ruta):

```powershell
python -m scripts.programar          # revisa y genera lo que falte
python -m scripts.programar --ver    # solo muestra la configuración y los meses generados

schtasks /create /tn "Talentia Insights" /sc daily /st 07:00 /tr "cmd /c cd /d C:\ruta\backend && .venv\Scripts\python.exe -m scripts.programar"
```

**Correo (opcional).** Si llenas `SMTP_HOST` y los demás `SMTP_*`, quien tenga correo registrado recibe "tienes N avisos nuevos" con la liga al sistema. **El correo nunca lleva datos.** Con Gmail usa una [contraseña de aplicación](https://myaccount.google.com/apppasswords), nunca tu contraseña normal.

### Respaldos

**Cada respaldo se prueba:** el script lo restaura en una base temporal y compara las filas de cada tabla con la base real. Si no cuadra, termina con error.

```powershell
cd backend
python -m scripts.respaldo                        # respalda la base y prueba restaurarlo
python -m scripts.respaldo --llave E:\Talentia    # además copia la llave del MFA a otra unidad
python -m scripts.respaldo --ver                  # lista los respaldos
python -m scripts.respaldo --restaurar ..\respaldos\<archivo>.dump
```

- Van en `respaldos/` (o en `RESPALDOS_DIR`), cada uno con su huella SHA-256. Se conservan los últimos 30 (`RESPALDOS_CONSERVAR`). Usa el `pg_dump` del contenedor: no hace falta instalar PostgreSQL.
- **La llave del MFA nunca va en el respaldo.** Cópiala con `--llave` a otra unidad; así, quien se lleve un respaldo no puede generar códigos de verificación.
- **Restaurar** reemplaza toda la base. Primero apaga la API (`docker compose stop api`); el script pide confirmar, verifica la huella y guarda antes una copia del estado actual.
- Con datos reales, los respaldos tienen datos de colaboradores: guárdalos en un disco cifrado y con acceso solo para TI.

Para respaldar todos los días a las 2:00 (cambia la ruta):

```powershell
schtasks /create /tn "Talentia Insights respaldo" /sc daily /st 02:00 /tr "cmd /c cd /d C:\ruta\backend && .venv\Scripts\python.exe -m scripts.respaldo"
```

### Cuentas desde la consola

Lo normal es que **TI administre las cuentas desde la sección Usuarios**. Las cuentas no se borran, se desactivan, y cada cambio queda en la bitácora. El script sirve para crear la primera cuenta de TI y como respaldo; **la contraseña siempre se escribe oculta**, nunca en el comando:

```powershell
python -m scripts.crear_usuario --usuario <usuario> --nombre "<Nombre>" --rol admin_ti
python -m scripts.crear_usuario --usuario <usuario> --nombre "<Nombre>" --rol gerente --area Ventas
python -m scripts.crear_usuario --listar
python -m scripts.crear_usuario --usuario <usuario> --cambiar-contrasena   # también desbloquea la cuenta
python -m scripts.crear_usuario --usuario <usuario> --cambiar-correo <correo>   # "" lo quita
python -m scripts.crear_usuario --usuario <usuario> --reiniciar-mfa        # si perdió su teléfono
```

Escribe la contraseña a mano: en la entrada oculta de PowerShell, Ctrl+V no pega el texto sino un carácter invisible.

| Rol | Ve |
|---|---|
| `direccion` | Solo el consolidado corporativo |
| `rrhh` | Todo. La Analista carga y genera; la Responsable (la marca TI) firma, nunca lo que pidió, y es la única que cambia los umbrales |
| `gerente` | Solo su área |
| `admin_ti` | Administra las cuentas; ve la configuración sin cambiarla; sin datos de colaboradores ni avisos |

## Desarrollo

### Instalación local

Para ver los cambios al instante sin reconstruir Docker. Necesitas [Python 3.14](https://www.python.org/downloads/), [Node.js](https://nodejs.org) 20 o más reciente, Docker Desktop y Git.

```powershell
# 1. Configuración: copia el ejemplo, cambia POSTGRES_PASSWORD y genera JWT_SECRETO con
#    python -c "import secrets; print(secrets.token_urlsafe(48))"
copy .env.example .env

# 2. Solo la base en Docker
docker compose stop api web
docker compose up -d db

# 3. API
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m scripts.seed      # datos de Nordika
python -m scripts.demo      # cuentas de prueba (o crea la tuya con scripts.crear_usuario)
python -m uvicorn app.main:app --reload

# 4. Tablero, en otra terminal
cd frontend
npm install
npm run dev
```

| Servicio | Dirección |
|---|---|
| Base de datos | `localhost:5433` (solo desde este equipo) |
| API | http://localhost:8000/docs (`/health` debe decir `{"status":"ok","database":"ok"}`) |
| Tablero | http://localhost:5173 (si la API está en otra dirección, ajusta `VITE_API_URL` en `frontend/.env`) |

### Pruebas

```powershell
cd backend
python -m pytest -q     # PostgreSQL local; no necesita Ollama, Groq ni internet (el modelo se simula)

cd frontend
npm test                # simula la API: no necesita el backend ni la base
```

Las del backend se niegan a correr si `DATABASE_URL` apunta a una base remota, y borran las cuentas de prueba: después corre `python -m scripts.demo`.

**En GitHub** corren solas en cada push a `Main` y en cada pull request (`.github/workflows/pruebas.yml`): el backend contra un PostgreSQL vacío que se llena con `scripts/seed.py`, y el frontend con sus pruebas y la compilación. El resultado aparece en **Actions** y junto a cada commit.

### Base compartida en Supabase (opcional)

Para que varias personas usen la misma base sin Docker. **Solo con datos sintéticos.**

1. Crea un proyecto en https://supabase.com (plan Free). Usa **Generate password** o solo letras y números, porque `@ # / : %` rompen la cadena de conexión. Este backend no usa la Data API: puedes desactivar **Enable Data API** y activar **Enable automatic RLS**.
2. En **Connect**, elige **Session pooler** y copia la cadena de conexión en `DATABASE_URL` de tu `.env`, con tu contraseña en lugar de `[YOUR-PASSWORD]`. El SSL se activa solo.
3. Carga los datos (`python -m scripts.seed`, pide escribir BORRAR) y crea tu usuario.
4. Al arrancar, la API activa *Row Level Security* en todas las tablas: la API pública de Supabase no puede leer nada.

Para volver a la base local, comenta `DATABASE_URL`. El plan gratuito se pausa tras 7 días sin uso y tiene 500 MB; esta base ocupa unos 13 MB.

## Problemas comunes

| Síntoma | Qué hacer |
|---|---|
| `docker compose` no encuentra Docker | Abre Docker Desktop y espera a que diga que está corriendo. |
| El puerto 8000, 8080 o 5433 ya está ocupado | Apaga el modo desarrollo (Ctrl+C) u otro programa que use ese puerto. |
| `docker compose logs api` dice `password authentication failed` | Cambiaste `POSTGRES_PASSWORD` después de la primera vez. Vuelve a la anterior, o empieza de cero con `docker compose down -v` (borra los datos). |
| http://localhost:8080 no abre | Revisa con `docker compose ps` que los tres servicios digan `Up`; si no, mira `docker compose logs api`. |
| El navegador dice que la conexión no es privada | Es el certificado autofirmado. Pon el de la empresa en `certs/` o pide a TI que instale `certs/talentia.crt` como confiable. |
| `rrhh_web` se reinicia y el log dice "lo dejaria sin cifrar" | Abriste el tablero a la red con `WEB_HTTPS=no`. Quita esa línea (o pon `auto`). |
| Una cuenta de prueba dice "Usuario o contraseña incorrectos" | Revisa que el `.env` tenga `MODO_DATOS=sinteticos`, `MODO_DEMO=si` y `DEMO_CONTRASENA`, y corre `docker compose up -d` (o `python -m scripts.demo`). El motivo aparece en `docker compose logs api`. Después de `pytest` también hay que correr `python -m scripts.demo`. |
| "No se pudo leer la verificación en dos pasos de tu cuenta" | Cambió o se perdió la llave del MFA (`MFA_LLAVE` o `llaves/mfa.key`). Vuelve a poner la anterior, entra con un código de respaldo o pide a TI que reinicie la verificación. |
| El reporte queda en **error** porque el modelo no está disponible | Abre Ollama y corre `ollama pull qwen3:8b` (o usa Groq con datos sintéticos) y vuelve a solicitarlo. |
| `/health` o `pytest` no se conectan a PostgreSQL | Corre `docker compose up -d db` y revisa con `docker compose ps` que diga `healthy`. |
| `pytest` dice que apunta a una base **remota** | Comenta `DATABASE_URL` en el `.env`. |
| El tablero dice "No se pudo conectar con la API" | Enciende la API o ajusta `VITE_API_URL` en `frontend/.env`. |
| Con Supabase, la API tarda y falla al conectar | El proyecto se pausó: reactívalo desde el panel de Supabase. |

## Estructura

```
backend/
  app/
    main.py          API (endpoints)
    schemas.py       modelos de entrada y salida de la API
    kpis.py          motor analítico: indicadores, tendencias, semáforo
    narrativa.py     motor de narrativa: hechos, prompt, reintentos
    guardrails.py    validación de lo que redacta la IA
    llm.py           proveedores de IA (Ollama, Groq) y candado de datos
    trabajos.py      generación en segundo plano, revisión y bitácora
    firmas.py        quién firma cada reporte, suplencias
    avisos.py        avisos por persona y correo opcional sin datos
    programacion.py  programación mensual
    umbrales.py      edición de umbrales con bitácora
    exportar.py      reporte aprobado en PDF y presentación
    cargas.py        carga de archivos: validación y conciliación
    seguridad.py     sesión, cuentas, contraseñas, tokens y permisos por rol
    mfa.py           verificación en dos pasos, secreto cifrado y códigos de respaldo
    demo.py          modo demostración: cuentas de prueba y teléfono simulado
    marca.py         nombre del producto y de la empresa
    database.py      conexión a PostgreSQL
  scripts/           seed, arranque (Docker), crear_usuario, demo, programar, respaldo,
                     calcular_kpis, generar_narrativa, evaluar_narrativa
  tests/             pruebas automáticas (pytest)
  reportes/          resultados de las evaluaciones del modelo de IA
  Dockerfile         imagen de la API
frontend/
  src/
    paginas/         Login, Tablero, Narrativas, DetalleNarrativa, Avisos, CargaDatos,
                     Configuracion, Usuarios, Cuenta, Pendiente
    componentes/     tarjetas de KPI, gráfica, vista del reporte, MFA, teléfono simulado
    pruebas/         pruebas automáticas (Vitest) con una API simulada
    api.js           cliente de la API
    sesion.jsx       inicio y cierre de sesión, permisos por rol
  nginx/             sirve el tablero, reenvía /api a la API y elige HTTP o HTTPS
  Dockerfile         imagen del tablero
db/                  esquema y tablas (SQL)
datos-de-prueba/     archivos para probar Carga de datos (ver su LEEME.md)
docs/GUIA.md         guía de funcionamiento para quien usa el sistema
docker-compose.yml   base de datos, API y tablero
.env.example         configuración de ejemplo, sin secretos
.github/workflows/   pruebas automáticas en GitHub
```

Se crean en cada instalación y no se suben a GitHub: `.env`, `llaves/`, `certs/` y `respaldos/`.

## Documentación

- [Guía de funcionamiento](docs/GUIA.md): pantallas, roles, archivos que se suben, cómo se calcula cada indicador y por qué.
- [Datos de prueba](datos-de-prueba/LEEME.md): archivos correctos y con errores para probar la carga, y qué debe pasar con cada uno.
- Documentación de la API: http://localhost:8000/docs con el sistema encendido.
