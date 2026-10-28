# Datos de prueba para Carga de datos

Archivos de **septiembre de 2026** de Nordika Logística (datos ficticios) para probar la pantalla **Carga de datos**. Entra con la cuenta de la **Analista de RRHH**: es la única que sube archivos.

Cada archivo se sube con el botón **Importar datos** de la fuente que dice la tabla. El sistema lo valida completo y muestra:

- **Validado:** lista para aplicar. Abajo dice cuántas filas se agregan o actualizan y qué columnas descartó.
- **Con errores:** la lista de errores con fila, columna y motivo. Fila 1 son los encabezados, igual que en Excel. Con un solo error no se puede aplicar nada: **todo o nada**.

Al **Aplicar**, el sistema concilia lo que decía el archivo contra lo que quedó en la base. Todo debe decir que cuadra.

> **Para volver a empezar:** aplicar archivos cambia los datos de Nordika. Para regresar a como estaba, corre `python -m scripts.seed` y después `python -m scripts.demo` en la carpeta `backend`. Con Docker: `docker compose down -v` y `docker compose up -d --build`.

## 1-correctos

El mes completo, como lo exportaría cada sistema. **Súbelos en este orden**, aplicando cada uno antes del siguiente. La plantilla de personal trae las altas del mes, y Metas y Capacitación se refieren a esos códigos nuevos.

| # | Archivo | Fuente | Qué debe pasar |
|---|---|---|---|
| 1 | `1-hris-2026-09.xlsx` | Plantilla de personal | Validado: 370 filas. Descarta `nombre_completo` (avisa que es **dato personal** y no se guarda) y `puesto` (no la usa ningún indicador). |
| 2 | `2-ats-2026-09.xlsx` | Vacantes | Validado: 8 vacantes, una todavía abierta (sin fecha de contratación). |
| 3 | `3-desempeno-2026-09.xlsx` | Metas de desempeño | Validado: 370 evaluaciones. |
| 4 | `4-capacitacion-2026-09.xlsx` | Capacitación | Validado: 376 inscripciones. |
| 5 | `5-ambiente-2026-09.xlsx` | Encuesta de ambiente laboral | Validado: 1,108 respuestas anónimas. |
| 6 | `6-productividad-2026-09.xlsx` | Productividad | Validado: 6 áreas. |

Con los seis aplicados, septiembre aparece en el **Tablero** y ya se puede generar su reporte. El aviso de "Mes pendiente" desaparece, porque octubre todavía no termina.

**Prueba extra:** sube el 3 (Metas) **antes** que el 1. Las altas de septiembre salen con error ("carga primero la plantilla de personal") porque esos empleados aún no existen.

## 2-archivo-que-no-sirve

El sistema rechaza el archivo completo antes de revisar las filas.

| Archivo | Súbelo en | Qué debe decir |
|---|---|---|
| `a-tipo-no-permitido.txt` | Cualquiera | "Solo se aceptan archivos .csv o .xlsx (Excel)". Para verlo en la ventana de elegir archivo, cambia el filtro a **Todos los archivos**. |
| `b-archivo-vacio.csv` | Cualquiera | "El archivo está vacío" |
| `c-solo-encabezados.csv` | Productividad | "El archivo no tiene filas" |
| `d-le-falta-una-columna.xlsx` | Productividad | "Falta esta columna en el archivo": `horas_disponibles` |
| `e-fuente-equivocada.xlsx` | Productividad | Es la encuesta de ambiente laboral subida en el lugar equivocado: faltan `horas_efectivas`, `horas_disponibles`, `entregables_planificados` y `entregables_completados` |
| `f-excel-danado.xlsx` | Cualquiera | "No se pudo leer el archivo…": dice .xlsx pero por dentro es texto |
| `g-demasiado-grande.csv` | Plantilla de personal | "El archivo pesa más de 5 MB" (pesa unos 5.5 MB) |

## 3-errores-en-filas

El archivo se lee bien, pero algunas filas no cumplen las reglas. Ninguno se puede aplicar.

### `hris-con-errores-2026-09.xlsx` → Plantilla de personal (8 errores)

| Fila | Qué tiene mal | Mensaje |
|---|---|---|
| 2 | Área "Marketing" | El área 'Marketing' no existe (y lista las áreas válidas) |
| 3 | Tiene fecha de baja pero no tipo de baja | fecha_baja y tipo_baja van juntas |
| 4 | Se dio de baja antes de ingresar | La fecha de baja es anterior a la de ingreso |
| 5 | Ingreso el 15/03/2027 | Es una fecha futura |
| 6 | Ingreso el 31/02/2026 (no existe) | No es una fecha |
| 7 | Tipo de baja "despido" | Debe ser una de: voluntaria, involuntaria |
| 8 | Sin código de empleado | Está vacía |
| 11 | Repite el código de la fila 10 | Registro repetido en el archivo |

### `ats-con-errores-2026-09.xlsx` → Vacantes (5 errores)

| Fila | Qué tiene mal | Mensaje |
|---|---|---|
| 2 | Se contrató 3 días antes de abrir la vacante | La vacante se cubrió antes de abrirse |
| 3 | Costo -500 | Debe ser al menos 0 |
| 4 | Costo "doce mil" | No es un número |
| 5 | Sin área | Está vacía |
| 10 | Repite el folio de la fila 7 | Registro repetido en el archivo |

### `desempeno-con-errores-2026-09.xlsx` → Metas de desempeño (8 errores)

| Fila | Qué tiene mal | Mensaje |
|---|---|---|
| 2 | 7 metas logradas de 5 asignadas | Hay más metas logradas que asignadas |
| 3 | Calificación 6 | Debe ser como máximo 5 |
| 4 | Empleado E9999 | El empleado no existe: carga primero la plantilla de personal |
| 5 | 0 metas asignadas | Debe ser al menos 1 |
| 6 | Periodo "septiembre" | No es un mes (usa AAAA-MM) |
| 7 | 4.5 metas logradas | Debe ser un número entero |
| 8 | Periodo 2027-01 | Es un mes futuro |
| 372 | Repite empleado y mes de la fila 12 | Registro repetido en el archivo |

### `capacitacion-con-errores-2026-09.xlsx` → Capacitación (5 errores)

| Fila | Qué tiene mal | Mensaje |
|---|---|---|
| 2 | Cursó más horas de las que tiene el programa | Se cursaron más horas de las que tiene el programa |
| 3 | Completado "tal vez" | Debe ser sí o no |
| 4 | Programa de 0 horas | Debe ser al menos 0.5 |
| 5 | Área "Recursos Humanos" | El área no existe |
| 378 | Repite la inscripción de la fila 7 | Registro repetido en el archivo |

### `ambiente-con-errores-2026-09.xlsx` → Encuesta de ambiente laboral (5 errores)

| Fila | Qué tiene mal | Mensaje |
|---|---|---|
| 2 | Dimensión "motivacion" | Debe ser una de: enps, satisfaccion, liderazgo, carga_trabajo |
| 3 | Puntaje 11 | Debe ser como máximo 10 |
| 4 | Puntaje -1 | Debe ser al menos 0 |
| 5 | Sin área | Está vacía |
| 6 | Puntaje 7.5 | Debe ser un número entero |

### `productividad-con-errores-2026-09.xlsx` → Productividad (4 errores)

| Fila | Qué tiene mal | Mensaje |
|---|---|---|
| 2 | Más horas efectivas que disponibles | Hay más horas efectivas que disponibles |
| 3 | Más entregables completados que planificados | Hay más entregables completados que planificados |
| 4 | 0 horas disponibles | Debe ser al menos 1 |
| 8 | Repite el área y mes de la fila 5 | Registro repetido en el archivo |

### `productividad-un-solo-error-2026-09.xlsx` → Productividad (1 error)

Cinco áreas bien y una mal (fila 6: más entregables completados que planificados). Sirve para ver el **todo o nada**: aunque casi todo está bien, no se aplica nada. La versión correcta es `1-correctos/6-productividad-2026-09.xlsx`.

## 4-se-aceptan-con-detalles

Se ven distinto a la plantilla, pero el sistema los entiende y los valida. Traen los mismos datos que `1-correctos`. Si ya aplicaste esos, estos **actualizan** lo que ya estaba en vez de duplicarlo. Metas y Capacitación necesitan antes la plantilla de personal, igual que en `1-correctos`.

| Archivo | Súbelo en | Qué tiene de distinto | Qué debe pasar |
|---|---|---|---|
| `hris-con-curp-rfc-correo-salario-2026-09.xlsx` | Plantilla de personal | Trae CURP, RFC, correo, salario y teléfono (inventados) | Validado. Descarta esas columnas y avisa que son **datos personales**; nunca se guardan ni se muestran. |
| `productividad-csv-punto-y-coma-2026-09.csv` | Productividad | CSV separado por `;`, acentos con la codificación de Windows y encabezados como "Área" o "HORAS DISPONIBLES" | Validado |
| `ats-fechas-dd-mm-aaaa-2026-09.csv` | Vacantes | Fechas como 15/09/2026, y una vacante abierta con la fecha de contratación vacía | Validado |
| `capacitacion-si-no-escrito-distinto-2026-09.xlsx` | Capacitación | "completado" escrito como SI, Sí, x, 1, No, 0, n | Validado |
| `desempeno-columnas-en-otro-orden-2026-09.xlsx` | Metas de desempeño | Columnas en otro orden, encabezados como "Codigo Empleado" y una columna de más (`comentarios_jefe`) | Validado. Descarta `comentarios_jefe` (no la usa ningún indicador). |

Si subes el mismo archivo dos veces, la segunda vez dice cuántas filas **ya existían** y se actualizarían, sin duplicar nada.
