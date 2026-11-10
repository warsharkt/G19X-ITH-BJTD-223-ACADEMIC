# Instalación desde cero: 10 de noviembre de 2026

Qué se probó: que alguien nuevo instala y usa el sistema solo con el [README](../../README.md), después de lo que cambió en el arranque con las auditorías del 4 y 5 de noviembre: contenedores de solo lectura con `cap_drop`, la cuenta `talentia_api` que crea `scripts/arranque.py` y el esquema que ya no crea la API.

| Dato | Valor |
|---|---|
| Fecha | 10 de noviembre de 2026, de 13:32 a 13:54 (hora del equipo, UTC−7) |
| Commit | `8c59caf2025e80c93425f5f2a4035e1dec133300` (rama `Main`, 5 de noviembre de 2026: "Octava auditoria: los reportes del mes ya no se pierden en silencio") |
| Equipo | Laptop con Intel Core i7-9750H (6 núcleos, 12 hilos) y 16 GB de RAM, Windows 11 Home (10.0.26200): el hardware de referencia del PRD (8.3). Docker Desktop con Docker 29.8.0 y Compose v5.5.1 (8 GB para Docker); Git 2.55 |
| IA | Ollama 0.40.16 con `qwen3:8b` en el mismo equipo, solo en CPU: la única gráfica es la integrada (Intel UHD 630) y Ollama la descarta |
| Carpeta | Nueva y vacía, aparte de la instalación de trabajo |
| Quién | Claude Code (ver [Uso de IA](../../README.md#uso-de-ia-en-el-desarrollo)), en el equipo de desarrollo y a pedido del autor. El recorrido se hizo en el tablero con un navegador automatizado (Playwright con Chromium) que entra con usuario, contraseña y el código del teléfono simulado, como una persona |

## 1. Instalación

Los pasos del [Inicio rápido](../../README.md#inicio-rápido), en PowerShell:

```powershell
git clone https://github.com/warsharkt/G19X-ITH-BJTD-223-ACADEMIC.git
cd G19X-ITH-BJTD-223-ACADEMIC
copy .env.example .env
# En el .env, solo las cuatro líneas del README (los valores elegidos no se anotan aquí):
#   POSTGRES_PASSWORD   MODO_DATOS=sinteticos   MODO_DEMO=si   DEMO_CONTRASENA
docker compose down -v
docker compose build --no-cache --pull   # extra: que nada salga de compilaciones anteriores de este equipo
docker compose up -d --build
```

| Paso | Resultado | Tiempo |
|---|---|---|
| `git clone` | Commit `8c59caf` | 2 s |
| `.env` | Cuatro líneas cambiadas (20, 26, 37 y 40) y nada más. Saltos de línea de Windows (CRLF) y sin BOM, como lo deja el Bloc de notas | — |
| `docker compose down -v` | Nada que borrar: carpeta nueva | 1 s |
| `docker compose build --no-cache --pull` | API y tablero compilados sin errores (solo el aviso de pip por instalar como root dentro de la imagen) | 75 s |
| `docker compose up -d --build` | Volumen y redes nuevos; `rrhh_db` y `rrhh_api` *healthy*, `rrhh_web` arriba | 30 s |
| `GET /health` | `{"status":"ok","database":"ok"}` | — |
| http://localhost:8080 | HTTP 200 | — |

Lo que dijo el arranque de la API (`docker compose logs api`), en orden:

1. `Se genero la llave del MFA en /app/llaves/mfa.key. Respaldala aparte de la base de datos.`
2. `Base vacia: cargando los datos ficticios de Nordika...`
3. Creó las cinco cuentas de prueba y las listó con su cargo: Analista de RRHH, Responsable de RRHH, Dirección General, Gerente de Ventas y Soporte TI. Los usuarios y la contraseña no se anotan aquí.
4. `La API se conecta como 'talentia_api' (sin privilegios y sin ser duena de las tablas).`
5. `JWT_SECRETO no configurado: se genero uno temporal para esta ejecucion.`
6. Uvicorn en el puerto 8000.

**Para repetirla en un equipo donde ya corre Talentia:** los contenedores tienen nombre fijo (`rrhh_db`, `rrhh_api`, `rrhh_web`) y usan los mismos puertos, así que primero se apaga la otra instalación con `docker compose down`, **sin** `-v`, y al final se vuelve a encender con `docker compose up -d`. Y no se clona en una carpeta con el mismo nombre que la de trabajo: Compose nombra el volumen de la base con el nombre de la carpeta, y ahí `docker compose down -v` borraría sus datos.

## 2. Lo que cambió en el arranque, comprobado

### Contenedores de solo lectura con `cap_drop`

`docker inspect` de los tres contenedores:

| Contenedor | Solo lectura | `cap_drop` | Capacidades que conserva | `no-new-privileges` | Usuario | Memoria / procesos | Redes |
|---|---|---|---|---|---|---|---|
| `rrhh_db` | sí | ALL | CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID | sí | el de la imagen (PostgreSQL deja de ser root al arrancar) | 1 GB / 200 | interna |
| `rrhh_api` | sí | ALL | ninguna | sí | `talentia` (uid 10001) | 2 GB / 256 | interna y pública |
| `rrhh_web` | sí | ALL | CHOWN, DAC_OVERRIDE, NET_BIND_SERVICE, SETGID, SETUID | sí | el de la imagen (nginx) | 256 MB / 100 | pública |

- Escribir fuera de los volúmenes falla en los tres: `Read-only file system`.
- El tablero no alcanza la base: dentro de `rrhh_web`, el nombre `db` ni siquiera se resuelve. La API sí, porque está en las dos redes.
- La llave del MFA sí se pudo escribir: `llaves/` es un volumen.

### La cuenta `talentia_api` que crea `scripts/arranque.py`

| Cuenta de PostgreSQL | Superusuario | Crea roles | Crea bases | Entra |
|---|---|---|---|---|
| La de `POSTGRES_USER` (administración) | sí | sí | sí | sí |
| `talentia_api` | no | no | no | sí |

Con la API en marcha, `pg_stat_activity` mostró una sola cuenta conectada a la base: `talentia_api`.

### El esquema ya no lo crea la API

- Las 24 tablas son de la cuenta de administración; ninguna de `talentia_api`.
- `talentia_api` no puede crear tablas en el esquema `public` ni esquemas en la base (`has_schema_privilege` y `has_database_privilege`: falso).
- En las bitácoras solo puede agregar y leer (`INSERT` y `SELECT`): `accesos`, `exportaciones`, `umbrales_cambios` y `usuarios_cambios`. En `narrativas`, `cargas`, `usuarios` y `suplencias` no tiene `DELETE`.

## 3. Recorrido sugerido

El del README ([Cuentas de prueba](../../README.md#cuentas-de-prueba)). Cada persona entra con su usuario, la contraseña de `DEMO_CONTRASENA` y el código del teléfono simulado, y cierra sesión al terminar.

| # | Quién | Qué hizo | Resultado |
|---|---|---|---|
| 1 | Dirección General | Primera entrada: el sistema exigió configurar la verificación en dos pasos (QR, código del teléfono simulado y 10 códigos de respaldo). En **Reportes > Pedir un reporte a RRHH**, con lo que trae por defecto: Corporativo, agosto 2026. | «Listo: Recursos Humanos recibió tu pedido. Te avisaremos cuando el reporte esté firmado.» |
| 2 | Analista de RRHH | Primera entrada, con verificación en dos pasos. **Carga de datos** decía «Mes pendiente: septiembre 2026». Subió en orden los seis archivos de `datos-de-prueba/1-correctos/` y aplicó cada uno. Después abrió el aviso del pedido y generó el reporte con IA. | Los seis quedaron «Lista para aplicar» (0.2 a 0.3 s cada uno) y, al aplicarlos, su conciliación cuadró (2 de 2 conceptos en cada uno). La plantilla: 370 filas (7 nuevas y 363 actualizadas); descartó `nombre_completo` («dato personal: no se guarda») y `puesto`. Al final, «Mes pendiente: octubre 2026». El aviso del pedido abrió «Nuevo reporte» con Corporativo y agosto 2026 ya elegidos, sin advertencias de datos faltantes, y dijo a quién se enviaría para su firma. |
| 3 | Responsable de RRHH | Primera entrada, con verificación en dos pasos. El aviso «Reporte de Corporativo, agosto 2026 listo para tu firma» llevó al reporte; lo aprobó con un comentario y una Nota de RRHH. | «Firmado por … (Responsable de RRHH) el 10 nov 2026, 1:53 p.m.». La Nota de RRHH aparece aparte y firmada, separada del texto de la IA. |
| 4 | Dirección General | Entró con contraseña y el código del teléfono. El aviso «Reporte de Corporativo, agosto 2026 aprobado: ya se puede descargar» llevó al reporte; descargó el PDF y la presentación. | PDF de 3 páginas (51 KB) y PowerPoint de 9 diapositivas (44 KB): portada firmada, Nota de RRHH, resumen, indicadores, hallazgos en dos diapositivas, alertas, recomendaciones y metodología, todas con «Confidencial: uso interno». Las dos descargas quedaron en la tabla `exportaciones`. |
| 5 | Soporte TI | Primera entrada, con verificación en dos pasos; su menú solo tiene Configuración y Usuarios. Creó una cuenta de gerente de Finanzas. | La contraseña temporal se mostró una sola vez. La cuenta quedó «Activa · Contraseña temporal · Espera aprobación»: TI no le puede dar acceso a datos sin la Responsable de RRHH. La Bitácora de cuentas registró «Cuenta creada» con rol, área, «firma reportes: no», quién la creó y desde qué IP. |

**El reporte de la IA (#1, Corporativo, agosto 2026).** Lo redactó `qwen3:8b` en este equipo, con el prompt v7, en **11 min 46 s**: 3 intentos en una sola ronda. Los guardarrailes rechazaron dos respuestas antes de aceptar la tercera, y el reporte lo muestra bajo la portada («Lo que el sistema rechazó: 2 respuestas del modelo»):

1. «hallazgo 3 (texto): no incluye el valor de Rotación voluntaria mensual (H08), que es 1.1 %; escríbelo tal cual…»
2. «hallazgo 3 (texto): demasiado largo (maximo 3 oraciones); acórtalo y, si cita varios hechos, repártelos en hallazgos separados…»

El mes tenía 0 indicadores en rojo, 0 en amarillo, 10 en rango y 5 por vigilar. El texto aceptado trae el resumen con el conteo, 5 hallazgos (cada uno con su valor, su respaldo y su fuente), las alertas «por vigilar» y 3 recomendaciones, más el anexo con los 10 indicadores.

**El tiempo rebasó la meta.** 11 min 46 s es más que los 10 minutos por reporte que pide el PRD: cada intento tardó unos 4 minutos y los dos reintentos sumaron el resto. En la [evaluación del 4 de noviembre](LEEME.md) el mismo caso salió a la primera en 387 s. La meta se mide en el equipo del piloto (MVP, criterio 8.2).

## 4. Comprobaciones extra

### Permisos, contra la API real

Con el tablero de lado, pidiendo directo a la API (por nginx, en `/api`) con la sesión de cada cuenta:

| Quién | Qué pidió | Esperado | Respondió |
|---|---|---|---|
| Analista de RRHH | Firmar el reporte que ella preparó | `403` | `403`: «No puedes revisar una narrativa que tú solicitaste: debe hacerlo otra persona de RRHH» |
| Dirección | Abrir el reporte #1 antes de la firma | `200` sin el texto de la IA | `200`, sin el texto |
| Dirección | Descargar el PDF antes de la firma | `409` | `409`: «Solo se pueden exportar reportes aprobados por RRHH; este está pendiente» |
| Dirección | Indicadores de Finanzas (solo ve Corporativo) | `403` | `403` |
| Gerente de Ventas | Indicadores de su área (solo ve Ventas) | `200` | `200` |
| Gerente de Ventas | El consolidado corporativo | `403` | `403` |
| Gerente de Ventas | Indicadores de Operaciones | `403` | `403` |
| Gerente de Ventas | El reporte #1 (consolidado) | `403` | `403` |
| Soporte TI | Indicadores | `403` | `403` |
| Soporte TI | Historial de reportes | `403` | `403` |
| Soporte TI | Cuentas | `200` | `200` |

### Archivos que no se deben cargar

Como la Analista, con los archivos de `datos-de-prueba/`:

- `3-errores-en-filas/hris-con-errores-2026-09.xlsx` en Plantilla de personal: «Con errores», 8 errores con fila, columna y motivo, y sin botón para aplicar. Se descartó.

  | Fila | Columna | Motivo |
  |---|---|---|
  | 2 | area | 'Marketing' el área 'Marketing' no existe… |
  | 3 | — | fecha_baja y tipo_baja van juntas: las dos llenas o las dos vacías |
  | 4 | — | La fecha de baja es anterior a la de ingreso |
  | 5 | fecha_ingreso | '2027-03-15' es una fecha futura |
  | 6 | fecha_ingreso | '31/02/2026' no es una fecha (usa AAAA-MM-DD o DD/MM/AAAA) |
  | 7 | tipo_baja | 'despido' debe ser una de: voluntaria, involuntaria |
  | 8 | codigo | está vacía |
  | 11 | — | Registro repetido en el archivo (codigo) |

- `2-archivo-que-no-sirve/f-excel-danado.xlsx` en Productividad: rechazado completo, «El archivo no es un Excel (.xlsx) válido».

### Lo que quedó en la base

| Tabla | Registros |
|---|---|
| `narrativas` | El #1: `lista` y `aprobada`, firmada por una persona distinta de quien lo preparó, con Nota de RRHH, «firmada como Responsable de RRHH», con proveedor `ollama`, modelo `qwen3:8b` y prompt `v7` |
| `exportaciones` | 1 PDF y 1 PPTX |
| `cargas` | 6 aplicadas, 1 descartada (la de errores) y 1 validada sin aplicar (ver Incidentes) |
| `usuarios_cambios` | 6 «crear» (las cinco cuentas de prueba y la del gerente) y 4 «activar_mfa» |

## 5. Pruebas automáticas

- **GitHub Actions con `8c59caf`:** la [corrida 42020244787](https://github.com/warsharkt/G19X-ITH-BJTD-223-ACADEMIC/actions/runs/42020244787) salió en verde: Backend (pytest, 510 pruebas) y Frontend (Vitest, 79 pruebas, y la compilación del tablero).
- **En este equipo, con los cambios de esta revisión** (regla 16 de `guardrails.py`): contra una base aparte (`rrhh_pruebas`, sembrada con `scripts.seed`) y con las mismas variables que el CI. Backend: 517 correctas y 1 omitida (`test_respaldo.py`: los permisos de Unix no aplican en Windows), en 1 min 54 s. Frontend: 79 correctas, en 50 s.
- **Antes y después del arreglo:** las 6 frases nuevas de `test_rechaza_causalidad` («atribuible a» y las cinco con «al» o «del») fallan con el `guardrails.py` de `8c59caf` (6 fallidas y 12 correctas) y pasan con el arreglo.

## 6. Resultado

La instalación desde cero funciona con `8c59caf` siguiendo solo el README: los tres contenedores arrancan endurecidos, la API se conecta como `talentia_api` y el esquema lo prepara `scripts/arranque.py`. El recorrido sugerido se completó con los cinco roles y las comprobaciones extra dieron lo esperado. No apareció ningún error del sistema.

Observaciones:

- **Tiempo de la IA:** el reporte tardó 11 min 46 s por dos reintentos, más que la meta de 10 minutos del PRD (sección 3).
- **Mes del recorrido:** Dirección pide por defecto agosto, el último mes con datos, y la Analista carga septiembre antes de generar. El reporte sale de agosto, que es lo que se pidió; septiembre queda en el tablero.
- **Otra instalación en el mismo equipo:** los contenedores tienen nombre y puertos fijos, así que hay que apagarla antes de repetir la prueba (sección 1).

### Incidentes de la prueba (no del sistema)

El script del navegador falló cinco veces por errores propios: leer el contador del teléfono (es un SVG), la consola de Windows con el símbolo «●» y tres selectores que encontraban dos elementos a la vez. Las fases interrumpidas antes de su acción principal se repitieron desde el inicio de sesión; las que ya la habían hecho (generar el reporte y crear la cuenta) se terminaron con una entrada aparte que solo leyó la pantalla, sin generar otro reporte ni crear otra cuenta. El único rastro en el sistema es una carga de la plantilla que quedó validada sin aplicar; el sistema la vence a los 7 días.
