# Talentia Insights

[![Pruebas](https://github.com/warsharkt/G19X-ITH-BJTD-223-ACADEMIC/actions/workflows/pruebas.yml/badge.svg)](https://github.com/warsharkt/G19X-ITH-BJTD-223-ACADEMIC/actions/workflows/pruebas.yml)

**Analítica de Recursos Humanos con IA responsable.** Talentia Insights consolida lo que exportan los sistemas de RRHH (nómina, reclutamiento, desempeño, capacitación, ambiente laboral y productividad), calcula los indicadores con su semáforo y redacta con IA el reporte ejecutivo de cada área y mes. Una persona de RRHH lo firma antes de que llegue a Dirección.

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
- [Uso de IA en el desarrollo](#uso-de-ia-en-el-desarrollo)
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
- **Documentación de la API:** http://localhost:8000/docs, solo desde este equipo (el tablero no la publica en la red).
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

> **Los pasos 2 a 4 necesitan la IA.** El reporte lo redacta siempre un modelo: antes de empezar, abre Ollama con `qwen3:8b` ([Inteligencia artificial](#inteligencia-artificial)) o configura Groq (solo con datos sintéticos). Sin ninguno de los dos, el reporte del paso 2 termina en **error** con el motivo, y en los pasos 3 y 4 no hay nada que firmar ni descargar. Con Ollama en CPU, cada reporte tarda de 2 a 5 minutos; Groq responde en segundos. Los pasos 1 y 5, y la carga de datos del paso 2, funcionan sin IA.

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
3. Crea con `python -m scripts.crear_usuario` ([Cuentas desde la consola](#cuentas-desde-la-consola)) la primera cuenta de TI y la de la Responsable de RRHH (con `--firma`). Desde el tablero, TI crea las demás con contraseña temporal; quién más firma lo decide la Responsable, no TI.
4. La Analista de RRHH sube desde **Carga de datos** lo que exporta cada sistema: plantilla de personal, vacantes, metas, capacitación, ambiente laboral y productividad. Cada fuente dice qué reporte exportar y trae su formato vacío.
5. La Responsable de RRHH revisa los umbrales en **Configuración** antes del primer reporte.

## Seguridad

| Medida | Cómo |
|---|---|
| Acceso | Rol y área en cada endpoint de la API; Dirección solo ve el consolidado, cada gerente solo su área y TI no ve datos de colaboradores. Dirección y los gerentes leen un reporte solo cuando RRHH ya lo firmó |
| Firma | El permiso de firmar lo da una Responsable de RRHH, nunca TI. Si TI restablece la contraseña o la verificación de quien firma, el permiso se suspende. La suplente también debe haber entrado con su propia contraseña y su verificación. Todo lo que TI hace con una cuenta de RRHH, Dirección o gerencia le llega como aviso a RRHH y a la persona |
| Contraseñas | Mínimo 10 caracteres, guardadas con scrypt. TI genera temporales que la persona cambia al entrar. Tras 5 intentos fallidos (al entrar o al escribir la contraseña actual en Mi cuenta) se bloquea ese equipo para ese usuario (no la cuenta entera, para que nadie pueda dejar fuera a otra persona). Un usuario inventado se bloquea igual que uno real, así que el bloqueo no revela qué cuentas existen; nginx además limita los intentos por IP |
| Verificación en dos pasos | Código de 6 dígitos (TOTP) obligatorio para Dirección, TI y RRHH, con 10 códigos de respaldo. El secreto se guarda cifrado (AES-256) con una llave que no está en la base |
| Datos personales | La carga descarta nombres, CURP, RFC, correos y demás; el sistema solo conoce códigos de empleado. Una carga validada que nadie aplica vence a los 7 días y sus filas se borran |
| IA | Con `MODO_DATOS=reales` solo se permite el modelo local: ningún dato sale del servidor |
| Red | Por defecto solo acepta conexiones del mismo equipo; abierto a la red, HTTPS se activa solo |
| Bitácoras | Cuentas, umbrales, cargas, reportes, firmas y descargas: quién, qué, cuándo y desde qué IP. Nunca guardan contraseñas |
| Navegador | Las respuestas de la API llevan `Cache-Control: no-store`: los datos de RRHH no quedan guardados en un equipo compartido. El tablero no carga nada de otros sitios, ni la fuente |
| Dependencias | La imagen de la API solo instala lo que usa (`requirements.txt`); las de las pruebas van aparte (`requirements-dev.txt`). Los Excel se leen con `defusedxml` |
| Sesión | Token en `sessionStorage` de la pestaña, que vence solo; **Cerrar sesión** lo invalida en el servidor. El tablero envía una Content-Security-Policy que solo deja correr su propio código |
| Base de datos | En Docker, la API se conecta con la cuenta `talentia_api`, sin privilegios de superusuario y con una contraseña nueva en cada arranque (`scripts/arranque.py`). El proceso de la API ya no conserva la contraseña del superusuario |
| Contenedores | Sin capacidades de Linux salvo las necesarias, sin escalar privilegios y con el sistema de archivos de solo lectura. Imágenes y acciones de GitHub fijadas por digest y SHA; Dependabot propone las actualizaciones |

**Nunca se suben a GitHub** (están en `.gitignore`): el `.env` con contraseñas y llaves, `llaves/` (llave del MFA), `certs/` (certificado HTTPS) y `respaldos/`. Este repositorio no contiene usuarios ni contraseñas: cada instalación pone los suyos en su `.env`. Si alguna vez subes un secreto por error, cámbialo de inmediato; borrarlo del repositorio no basta, porque queda en el historial.

## Inteligencia artificial

La narrativa siempre la redacta un modelo, y se elige en el `.env`:

| Opción | Configuración | Cuándo usarla |
|---|---|---|
| **Ollama local** (por defecto) | Instala [Ollama](https://ollama.com), corre `ollama pull qwen3:8b` y deja `LLM_PROVEEDOR=ollama` | Datos reales: nada sale del equipo. En CPU tarda de 2 a 5 minutos por reporte |
| **Groq** (nube) | Crea una llave en https://console.groq.com/keys y pon `LLM_PROVEEDOR=groq`, `MODO_DATOS=sinteticos` y `GROQ_API_KEY` | Revisar el proyecto rápido: responde en segundos. **Solo con datos sintéticos**: el sistema se niega a usarla con datos reales |

Los reportes se generan en segundo plano: `POST /narrativas` devuelve un id y `GET /narrativas/{id}` muestra el resultado cuando está listo.

**Revisión antes de distribuir.** Todo reporte nace **pendiente de firma** y dice quién lo firmará. La Responsable de RRHH (o su suplente) lo aprueba, con una Nota de RRHH opcional, o lo rechaza con motivo. Nadie firma lo que pidió, y la decisión queda registrada con usuario, fecha y comentario. Bajo la portada, el apartado **Lo que el sistema rechazó** le muestra qué respuestas del modelo no pasaron los guardarrailes antes de esta versión y por qué (una cifra que no está en los datos, una causa, un "mejoró" donde el sistema calculó que empeoró…), para que sepa qué se corrigió y no solo cuántos intentos hubo.

**Evaluación con el modelo real.** [`docs/evidencias/`](docs/evidencias/LEEME.md) tiene una corrida completa de `scripts/evaluar_narrativa.py` con Qwen3 8B en Ollama: cuántos casos salieron a la primera, cuántos tras corregir, cuánto tardó cada uno, los textos que se aceptaron y lo que se rechazó.

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

**Programación mensual.** En **Configuración**, RRHH la activa y elige el día. Desde ese día se generan los reportes del último mes cerrado (el consolidado y cada área), una sola vez por mes. Si al mes le falta alguna de las cuatro fuentes mensuales (metas, capacitación, ambiente laboral o productividad), espera a que se suban. Nace **desactivada**, porque con Ollama en CPU cada reporte tarda minutos.

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
python -m scripts.crear_usuario --usuario <usuario> --nombre "<Nombre>" --rol rrhh --firma   # la primera Responsable
python -m scripts.crear_usuario --usuario <usuario> --dar-firma            # o --quitar-firma, si no queda ninguna Responsable
```

Escribe la contraseña a mano: en la entrada oculta de PowerShell, Ctrl+V no pega el texto sino un carácter invisible.

| Rol | Ve |
|---|---|
| `direccion` | Solo el consolidado corporativo |
| `rrhh` | Todo. La Analista carga y genera; la Responsable firma, nunca lo que pidió, es la única que cambia los umbrales y decide quién más firma (TI no puede) |
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
pip install -r requirements-dev.txt   # la API y lo que usan las pruebas
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

Las del backend no necesitan Ollama, Groq ni internet (el modelo se simula), pero **cambian la base en la que corren**: cargan un mes, vuelven a sembrar los datos de Nordika y crean y borran cuentas. Por eso conviene darles su propia base, `rrhh_pruebas`, en el mismo contenedor: así tu base de trabajo y las cuentas de prueba quedan como estaban. Se niegan a correr si `DATABASE_URL` apunta a una base remota.

**Con Python** (después de la [instalación local](#instalación-local)):

```powershell
docker compose up -d db
docker compose exec db sh -c 'createdb -U $POSTGRES_USER rrhh_pruebas'   # solo la primera vez
cd backend
.venv\Scripts\Activate.ps1
$env:POSTGRES_DB = "rrhh_pruebas"   # solo en esta terminal
python -m scripts.seed              # la primera vez, o si una corrida se interrumpió a la mitad
python -m pytest -q
```

**Solo con Docker**, sin instalar Python: la imagen de la API no lleva `backend/tests` (`.dockerignore` lo deja fuera para no meter pruebas en la imagen de producción), así que la carpeta se monta al correrlas. Desde la raíz del proyecto:

```powershell
docker compose build api            # la imagen con el código actual
docker compose exec db sh -c 'createdb -U $POSTGRES_USER rrhh_pruebas'   # solo la primera vez
docker compose run --rm --no-deps -e POSTGRES_DB=rrhh_pruebas api python -m scripts.seed
docker compose run --rm --no-deps -e POSTGRES_DB=rrhh_pruebas -v "${PWD}/backend/tests:/app/backend/tests:ro" api sh -c "pip install --user -q -r requirements-dev.txt && python -m pytest -q -p no:cacheprovider"
```

La imagen de la API no trae pytest (solo lo que usa la API), así que el último comando lo instala en ese contenedor de un solo uso: necesita internet. Dentro del contenedor se salta una prueba, la del respaldo, porque necesita el comando `docker`. Si corres las pruebas sin `POSTGRES_DB`, usan tu base de trabajo: sus datos vuelven a los de Nordika y se borran las cuentas de prueba. Después corre `python -m scripts.demo`.

Las del frontend simulan la API, así que no necesitan el backend ni la base:

```powershell
cd frontend
npm test
```

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
| Una cuenta de prueba dice "Usuario o contraseña incorrectos" | Revisa que el `.env` tenga `MODO_DATOS=sinteticos`, `MODO_DEMO=si` y `DEMO_CONTRASENA`, y corre `docker compose up -d` (o `python -m scripts.demo`). El motivo aparece en `docker compose logs api`. Si corriste `pytest` sin `POSTGRES_DB=rrhh_pruebas`, también hay que correr `python -m scripts.demo`. |
| "Cuenta bloqueada en este equipo" o un error 429 al entrar | Hubo 5 intentos fallidos desde ese equipo, o más de 10 por minuto. Espera 15 minutos o entra desde otro equipo; TI la desbloquea al restablecer la contraseña. |
| Una Responsable ya no aparece como quien firma | TI le restableció la contraseña o la verificación en dos pasos, y el permiso se suspendió a propósito. Otra Responsable se lo devuelve en **Usuarios** (**Dar firma**); si no hay otra, `python -m scripts.crear_usuario --usuario <usuario> --dar-firma`. |
| `pytest` dice que no hay datos | Siembra la base de pruebas: `python -m scripts.seed` con `POSTGRES_DB=rrhh_pruebas` ([Pruebas](#pruebas)). |
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
    main.py          arma la API: arranque, CORS y los routers
    rutas/           endpoints, un archivo por tema (sesion, kpis, narrativas, cargas,
                     cuentas, firmas, avisos, configuracion, catalogos, demostracion)
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
                     (las dependencias solo_rrhh, solo_responsable, solo_ti, ti_o_rrhh...)
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
docs/evidencias/     corridas de evaluación con el modelo real (Qwen3 8B)
docker-compose.yml   base de datos, API y tablero
.env.example         configuración de ejemplo, sin secretos
.github/workflows/   pruebas automáticas en GitHub
```

Se crean en cada instalación y no se suben a GitHub: `.env`, `llaves/`, `certs/` y `respaldos/`.

## Uso de IA en el desarrollo

Este proyecto se programó con un asistente de IA. Esta sección dice qué hizo la herramienta y qué hice yo, para que se pueda evaluar el trabajo propio. No hay que confundirla con la IA del producto (Ollama con Qwen3, o Groq), que redacta los reportes.

**Herramienta:** [Claude Code](https://claude.com/claude-code), el asistente de programación de Anthropic (modelo Claude Opus), en la terminal y sobre este repositorio. Los commits en los que participó llevan la línea `Co-Authored-By: Claude` (27 de los primeros 33).

| Parte | Lo que hizo Claude Code | Lo que hice yo |
|---|---|---|
| Requerimientos y alcance | Comentarios y preguntas sobre huecos | Definí el problema, los requerimientos (PRD) y el alcance del MVP, que son documentos internos y no están en el repositorio, y el orden de los pasos |
| Decisiones de diseño | Propuso opciones cuando había más de un camino | Las elegí antes de que se programaran (ver abajo) |
| Código del backend y del tablero | Escribió la mayor parte: API, indicadores, motor de narrativa y guardarrailes, seguridad y MFA, carga de datos, exportación, tablero en React, scripts, Docker y GitHub Actions | Revisé lo que hacía, pedí cambios y aprobé cada commit y cada push |
| Pruebas | Escribió las pruebas (pytest y Vitest) y las corrió antes de cada commit | Pedí qué comprobar y revisé los resultados |
| Documentación | Redactó los borradores del README, la guía y los LEEME | Los revisé y corregí |
| Datos | Generó los datos ficticios de Nordika (`scripts/seed.py`) | Definí la empresa ficticia y los escenarios que debían contener. Nunca se usaron datos de personas reales |

**Decisiones que tomé yo**, entre otras:

- Que fuera una demostración de venta completa: la empresa ficticia Nordika Logística, el nombre Talentia Insights y el teléfono simulado, para que cualquiera pudiera probar la seguridad sin celular.
- Quien prepara no firma: la Analista carga y genera, la Responsable firma, con suplente; solo la Responsable cambia los umbrales.
- Verificación en dos pasos obligatoria para Dirección, TI y RRHH, con códigos de respaldo; solo TI administra cuentas, y estas se desactivan, no se borran.
- IA local por defecto y Groq solo con datos sintéticos; el correo de avisos nunca lleva datos; la programación mensual nace apagada.
- Que el PRD sea un documento interno y no se publique.

**Revisión del código (noviembre de 2026).** Otra persona revisó el proyecto y encontró, entre otras cosas, una prueba que dependía de la fecha, huecos en los guardarrailes (causas con "porque" o "por eso", un "mejoró" cuando el sistema calculó "empeoró", y cifras como "2031" tomadas por años), un desbordamiento del tablero en celular y un `main.py` demasiado grande. Claude Code hizo los arreglos y corrió la evaluación con Qwen3 real que está en [`docs/evidencias/`](docs/evidencias/LEEME.md); yo decidí qué arreglar y reviso los cambios antes de subirlos.

## Documentación

- [Guía de funcionamiento](docs/GUIA.md): pantallas, roles, archivos que se suben, cómo se calcula cada indicador y por qué.
- [Datos de prueba](datos-de-prueba/LEEME.md): archivos correctos y con errores para probar la carga, y qué debe pasar con cada uno.
- [Evidencias](docs/evidencias/LEEME.md): evaluación del modelo de IA real, caso por caso.
- Documentación de la API: http://localhost:8000/docs con el sistema encendido, desde el propio servidor.
