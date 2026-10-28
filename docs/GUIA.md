# Guía de funcionamiento — Talentia Insights

**Cómo funciona Talentia Insights en Nordika Logística:** para qué sirve cada parte, qué archivos se suben, qué se analiza y por qué cada indicador se calcula como se calcula.

| | |
|---|---|
| Empresa | Nordika Logística (operador logístico en Guadalajara, ~350 personas, seis áreas) |
| Versión de la guía | 2.0 · 27 de octubre de 2026 |
| Reemplaza a | *Guía de funcionamiento - Talentia Insights.pdf* (octubre de 2026), que todavía describía las cuentas `demo_*` |

> Nordika y sus datos son ficticios: no corresponden a personas reales. El sistema se usa como si fuera la instalación de la empresa; para otra empresa se cambian el nombre y todos los datos sin tocar el código (README, sección *Usarlo con los datos de otra empresa*).

## Contenido

1. [Para qué sirve](#1-para-qué-sirve)
2. [Cómo funciona, de principio a fin](#2-cómo-funciona-de-principio-a-fin)
3. [Quién lo usa y qué ve cada quien](#3-quién-lo-usa-y-qué-ve-cada-quien)
4. [Las pantallas, una por una](#4-las-pantallas-una-por-una)
5. [Qué archivos se suben](#5-qué-archivos-se-suben)
6. [Qué se analiza: los 10 indicadores](#6-qué-se-analiza-los-10-indicadores)
7. [El semáforo y las reglas de cálculo](#7-el-semáforo-y-las-reglas-de-cálculo)
8. [Cómo redacta la IA (y qué no puede hacer)](#8-cómo-redacta-la-ia-y-qué-no-puede-hacer)
9. [Preparación, firma y descarga](#9-preparación-firma-y-descarga)
10. [Avisos y reportes automáticos](#10-avisos-y-reportes-automáticos)
11. [Seguridad, privacidad y respaldos](#11-seguridad-privacidad-y-respaldos)
12. [Glosario](#12-glosario)

---

## 1. Para qué sirve

Talentia Insights junta en un solo lugar lo que exportan los sistemas de Recursos Humanos, calcula los indicadores de cada área y cada mes, y redacta con inteligencia artificial el reporte ejecutivo para la dirección. La Analista de RRHH lo prepara y la Responsable de RRHH lo firma antes de que llegue a nadie.

### El problema que resuelve

En casi todas las empresas la información de personas vive en sistemas separados: reclutamiento, nómina, desempeño, capacitación, encuestas de clima y productividad. Para armar un reporte mensual alguien de RRHH exporta cada sistema, lo pega en hojas de cálculo, hace las cuentas y escribe el resumen. Eso provoca:

- Reportes que tardan días y dependen de quién esté disponible.
- El mismo indicador calculado de forma distinta cada mes, según quién lo hizo.
- Señales que se pierden: por ejemplo, que el clima laboral y la rotación empeoraron al mismo tiempo en un área.

### La idea central: dos motores separados

| Motor | Qué hace | Por qué así |
|---|---|---|
| **Motor analítico** (sin IA) | Calcula los 10 indicadores, sus variaciones y el semáforo con fórmulas fijas en la base de datos. | Las cifras deben ser exactas y siempre iguales con los mismos datos. Una IA puede equivocarse en una suma; una fórmula no. |
| **Motor de narrativa** (con IA) | Redacta el resumen, los hallazgos y las recomendaciones usando solo los indicadores ya calculados. | Escribir un buen resumen ejecutivo es lo que más tiempo consume. La IA lo hace en minutos, pero nunca inventa ni calcula cifras: unas reglas automáticas revisan cada respuesta. |

### Lo que el sistema no hace

- No toma decisiones sobre personas (contrataciones, despidos, ascensos o sanciones). Sugiere; RRHH decide.
- No reemplaza los sistemas de nómina, reclutamiento o capacitación: lee lo que exportan.
- No guarda nombres, CURP, RFC, correos ni salarios. Solo conoce códigos de empleado.
- No distribuye nada que la Responsable de RRHH no haya firmado.

### Los datos de Nordika

El sistema arranca con 24 meses de historia de Nordika (septiembre de 2024 a agosto de 2026) en seis áreas: Operaciones, Ventas, Transporte, Finanzas, Almacén y Jurídico. Cada mes nuevo entra como en cualquier empresa: la Analista sube lo que exporta cada sistema. Hoy el mes pendiente es **septiembre de 2026**.

## 2. Cómo funciona, de principio a fin

Cada mes la información recorre el mismo camino, desde el archivo que exporta un sistema hasta el PDF que recibe la dirección. Los pasos 1 a 5 son de preparación y análisis; 6 a 8, de control y distribución.

| # | Paso | Qué pasa |
|---|---|---|
| 1 | **Carga** | La Analista de RRHH sube el Excel o CSV que exporta cada sistema (nómina, reclutamiento, desempeño, etc.). |
| 2 | **Validación** | Se revisa cada fila. Si hay un solo error, el archivo no entra. Se descartan los datos personales. |
| 3 | **Cálculo** | El motor analítico calcula los 10 indicadores por área y mes, y sus variaciones. |
| 4 | **Semáforo** | Cada indicador se compara contra los umbrales: rojo, amarillo, verde o por vigilar. |
| 5 | **Redacción con IA** | La Analista prepara el reporte (por iniciativa propia, porque Dirección o un gerente se lo pidió, o porque llegó el día de la programación mensual). La IA lo redacta a partir de los indicadores y unas reglas automáticas lo verifican. |
| 6 | **Firma** | La Responsable de RRHH (o su suplente) lo lee y lo aprueba o lo rechaza. Nunca firma quien lo preparó. |
| 7 | **Aviso** | Cuando se aprueba, la dirección o el gerente del área reciben un aviso en el sistema. |
| 8 | **Descarga** | El reporte firmado se descarga en PDF o presentación. Cada descarga queda registrada. |

### Qué pasa en cada momento

| Momento | Qué ocurre | Qué queda registrado |
|---|---|---|
| Al subir un archivo | Se valida completo y se muestra una vista previa: cuántas filas se agregan, cuántas se actualizan y qué columnas se descartan. Todavía no cambia nada. | Quién lo subió, cuándo, nombre y huella digital del archivo. |
| Al aplicar la carga | Los datos entran a la base en una sola operación, se recalculan los indicadores y se revisa si algo quedó en rojo. | Quién lo aplicó y la conciliación (si lo del archivo cuadra con la base). |
| Al preparar un reporte | Se genera en segundo plano (la pantalla no se bloquea) y desde el inicio dice quién lo firmará. Con la IA local tarda de 2 a 5 minutos; con la IA en la nube, segundos. | Quién lo preparó, los datos exactos que recibió la IA, el modelo y la versión de las instrucciones. |
| Al firmar | Se aprueba tal como está, con una Nota de RRHH opcional, o se rechaza con un motivo. El texto de la IA no se edita. | Quién firmó, con qué cargo, cuándo y su comentario. |
| Al descargar | Se arma el PDF o la presentación con lo aprobado, sin recalcular nada. | Quién descargó, en qué formato y cuándo. |

## 3. Quién lo usa y qué ve cada quien

Cada persona entra con su propia cuenta y solo ve lo que le corresponde por su puesto. Estas restricciones las aplica el servidor, no solo la pantalla: aunque alguien intente pedir datos de otra área por fuera de la interfaz, el sistema se los niega.

| Rol | Para qué lo usa | Qué datos ve | Qué puede hacer |
|---|---|---|---|
| **Dirección General** | Recibir el panorama de la empresa y los reportes firmados. | Solo el consolidado de toda la empresa, nunca el detalle por área. | Ver el tablero, pedir reportes del consolidado a RRHH y descargar los firmados. |
| **Analista de RRHH** | Operar el sistema cada mes. | Todas las áreas y el consolidado. | Cargar los archivos, preparar los reportes, atender los pedidos y cambiar la programación mensual. No firma reportes ni cambia umbrales. |
| **Responsable de RRHH** | Controlar lo que sale de RRHH. | Todas las áreas y el consolidado. | Firmar (aprobar o rechazar) los reportes, designar suplente y cambiar los umbrales del semáforo. No prepara reportes. |
| **Gerente de área** | Seguir los indicadores de su propio equipo. | Solo su área. | Ver el tablero, pedir reportes de su área a RRHH y descargar los firmados. |
| **Soporte TI** | Administrar cuentas y accesos. | Ningún dato de colaboradores: solo la configuración y las cuentas. | Crear cuentas, desactivarlas, restablecer contraseñas y la verificación en dos pasos, y marcar quién es la Responsable. |

> **Por qué se calcula así**
> - **Mínimo privilegio:** cada quien ve lo indispensable para su trabajo. Un gerente no necesita ver la rotación de otra área, y TI no necesita ver datos de personas para administrar cuentas.
> - **Quien prepara no firma:** la Analista prepara y la Responsable firma, así que cada reporte pasa por dos personas. Por la misma razón, solo la Responsable cambia los umbrales: un umbral decide qué sale en rojo en los reportes que prepara la Analista.
> - **Quien administra cuentas no aprueba contenido:** TI no firma reportes. Así nadie puede crearse una segunda cuenta para aprobarse a sí mismo.

### Cuentas de prueba

Con datos de prueba, el sistema trae una cuenta por cada rol del personal de Nordika: Analista de RRHH, Responsable de RRHH, Dirección General, Gerente de Ventas y Soporte TI. La pantalla de inicio es la de producción: no muestra cuentas ni contraseñas, y esta guía tampoco. Quien instala el sistema elige la contraseña (`DEMO_CONTRASENA`) y entrega los usuarios a quien lo va a probar; también aparecen en el registro de arranque (`docker compose logs api`).

| Cuenta | Para qué sirve |
|---|---|
| Analista de RRHH | Cargar los datos del mes, preparar los reportes y atender los pedidos |
| Responsable de RRHH | Firmar los reportes con una Nota de RRHH, designar suplente y ajustar los umbrales |
| Dirección General | Solo el consolidado; pedir reportes y descargar los firmados |
| Gerente de Ventas | Solo su área; la verificación en dos pasos es opcional |
| Soporte TI | Administrar cuentas sin ver datos de colaboradores |

**Recorrido sugerido:** entra como Dirección o como el Gerente y pide un reporte; luego como la Analista, sube los archivos de septiembre de 2026 y prepara el reporte; por último como la Responsable, fírmalo. Para cambiar de persona se cierra sesión.

La primera vez, Dirección, RRHH y TI configuran la verificación en dos pasos. Para no necesitar un celular, en pantalla aparece un **teléfono simulado** con el código (sección 11).

## 4. Las pantallas, una por una

El menú de la izquierda solo muestra las secciones que el rol puede usar. Arriba a la derecha está el nombre de la persona (que lleva a Mi cuenta) y el botón para cambiar entre el diseño claro y el oscuro.

| Pantalla | Quién la ve | Para qué sirve |
|---|---|---|
| **Tablero** | Todos menos TI | Muestra los 10 indicadores del mes con su semáforo, cuánto cambiaron contra el mes anterior y contra el mismo mes del año pasado, y una gráfica de los últimos 24 meses del indicador elegido con sus umbrales. Se filtra por área, mes e indicador; los filtros quedan en la dirección de la página, así que se puede compartir el enlace a una vista exacta. La Analista prepara desde aquí el reporte con **Generar reporte con IA**; Dirección y los gerentes usan **Pedir este reporte a RRHH**. |
| **Reportes** | Todos menos TI | El historial de reportes con su estado (en proceso, listo, con error), su firma (pendiente, aprobado, rechazado) y quién lo firmará. Al abrir uno se ve el resumen, los hallazgos, las alertas y las recomendaciones, cada uno con los datos que lo respaldan y su nivel de confianza. Aquí la Responsable lo aprueba con **Aprobar y firmar** o lo rechaza, y aquí se descarga en PDF o presentación. Dirección y los gerentes también piden reportes desde aquí. |
| **Avisos** | Todos menos TI | La bandeja de avisos: indicadores en rojo, pedidos, reportes por firmar, aprobados o rechazados. El menú muestra cuántos faltan por leer. Cada aviso lleva directo a donde se atiende. |
| **Carga de datos** | Solo la Analista | Subir los archivos de cada sistema, ver la validación fila por fila y lo que se descarta, aplicar la carga y ver la conciliación. Cada tarjeta dice qué reporte exportar de su sistema. Incluye el **Formato vacío** de cada fuente (Excel con las columnas), los archivos del mes pendiente y la bitácora de todas las cargas. |
| **Configuración** | Todos | Quién firma los reportes y la suplencia; los umbrales del semáforo, con la bitácora de quién los cambió y de qué valor a qué valor; y la programación mensual. Los umbrales los cambia solo la Responsable; la programación, cualquiera de RRHH. |
| **Usuarios** | TI administra, RRHH consulta | Las cuentas y su bitácora. TI crea cuentas con contraseña temporal, cambia rol o área, marca a la Responsable, desactiva y reinicia la verificación en dos pasos. RRHH puede consultar todo para auditar a TI. |
| **Mi cuenta** | Todos | Cambiar la propia contraseña y activar la verificación en dos pasos. |

> **Accesibilidad.** El color del semáforo nunca va solo: siempre lo acompañan un icono y un texto (Crítico, Atención, En rango, Por vigilar), para que lo entiendan también personas con daltonismo o en una impresión en blanco y negro. Cada gráfica tiene además una vista de tabla.

## 5. Qué archivos se suben

La Analista de RRHH sube el archivo que ya exporta cada sistema, en Excel (.xlsx) o CSV, de hasta 5 MB. Los nombres de columna no distinguen mayúsculas, acentos ni espacios: "Fecha de Ingreso" se lee igual que "fecha_de_ingreso". Solo la Analista carga datos: TI no ve información de colaboradores, y la Responsable firma lo que se prepara con esos datos.

### Las seis fuentes y el orden de carga

| # | Archivo | Sistema que lo exporta | Qué contiene | Indicadores que alimenta |
|---|---|---|---|---|
| 1 | Plantilla de personal | HRIS / Nómina | Altas y bajas de cada colaborador. | Rotación (3), cobertura de capacitación y tamaño de cada equipo |
| 2 | Vacantes | ATS (reclutamiento) | Vacantes abiertas y cubiertas, con su costo. | Tiempo y costo de contratación |
| 3 | Metas de desempeño | Sistema de desempeño | Metas asignadas y logradas por persona y mes. | Cumplimiento de metas |
| 4 | Capacitación | LMS | Inscripciones a programas y si se completaron. | Cobertura y tasa de finalización |
| 5 | Encuesta de clima | Encuestas | Respuestas anónimas por área y mes. | eNPS |
| 6 | Productividad | Proyectos y tickets | Horas efectivas y disponibles por área y mes. | Índice de productividad |

La plantilla de personal va primero porque las demás fuentes se refieren a sus códigos de empleado: una meta de desempeño de un código que no existe se rechaza.

### Columnas de cada archivo

Las columnas marcadas como *opcional* pueden ir vacías. Cualquier otra columna que traiga el archivo se descarta (ver más abajo).

**1. Plantilla de personal (HRIS / Nómina)**

| Columna | Qué es |
|---|---|
| `codigo` | Código de empleado. Nunca el nombre. |
| `area` | Área a la que pertenece (debe existir en el catálogo). |
| `fecha_ingreso` | Fecha de alta. |
| `fecha_baja` (opcional) | Vacía si sigue activo. Una baja no borra a nadie: la persona deja de contar en la plantilla desde esa fecha y sigue en el historial (rotación, reportes pasados). Quien no viene en el archivo se queda como estaba, así que exporta la plantilla completa, con las bajas. |
| `tipo_baja` (opcional) | `voluntaria` o `involuntaria`. Va junto con `fecha_baja`: las dos llenas o las dos vacías. |

**2. Vacantes (ATS)**

| Columna | Qué es |
|---|---|
| `folio` | Identificador de la vacante. Evita duplicarla si se vuelve a cargar. |
| `area` | Área que abrió la vacante. |
| `fecha_apertura` | Cuándo se abrió. |
| `fecha_contratacion` (opcional) | Cuándo se cubrió. Vacía si sigue abierta. |
| `costo_proceso` | Costo total del proceso en MXN (anuncios, agencias, evaluaciones). |

**3. Metas de desempeño**

| Columna | Qué es |
|---|---|
| `codigo_empleado` | Debe existir en la plantilla de personal. |
| `periodo` | Mes, en formato AAAA-MM. |
| `metas_asignadas` | Entero, al menos 1. |
| `metas_logradas` | Entero. No puede ser mayor que las asignadas. |
| `calificacion` | Del 1 al 5. |

**4. Capacitación (LMS)**

| Columna | Qué es |
|---|---|
| `programa` | Nombre del curso o programa. |
| `periodo` | Mes del programa (AAAA-MM). |
| `horas_programa` | Duración del programa en horas. |
| `area_programa` (opcional) | Vacía si el programa es para toda la empresa. |
| `codigo_empleado` | Quién se inscribió. |
| `completado` | Sí o no. |
| `horas_cursadas` | No puede superar las horas del programa. |

**5. Encuesta de clima**

| Columna | Qué es |
|---|---|
| `area` | Área de quien respondió. No lleva código de empleado: las respuestas son anónimas. |
| `periodo` | Mes de la encuesta (AAAA-MM). |
| `dimension` | `enps`, `satisfaccion`, `liderazgo` o `carga_trabajo`. |
| `puntaje` | Del 0 al 10. |

**6. Productividad**

| Columna | Qué es |
|---|---|
| `area` / `periodo` | Un registro por área y mes. |
| `horas_efectivas` | Horas dedicadas a trabajo productivo. No pueden superar las disponibles. |
| `horas_disponibles` | Horas laborables del equipo en el mes. |
| `entregables_planificados` / `entregables_completados` | Los completados no pueden superar los planificados. |

### Qué se revisa al subir un archivo

- **Tipos y formatos:** que las fechas sean fechas, los números sean números y los meses tengan formato AAAA-MM.
- **Fechas razonables:** ni futuras ni absurdas (por ejemplo, un ingreso en 1900).
- **Que exista lo que se menciona:** áreas del catálogo y códigos de empleado de la plantilla.
- **Reglas de sentido común:** no más metas logradas que asignadas, ni bajas antes del ingreso, ni vacantes cubiertas antes de abrirse, ni más horas efectivas que disponibles.
- **Repetidos:** el mismo folio, el mismo empleado en el mismo mes, etc.

Si hay errores, la pantalla dice la fila, la columna y el motivo (por ejemplo: *fila 14, metas_logradas: hay más metas logradas que asignadas*).

> **Por qué se calcula así**
> - **Todo o nada.** Un archivo con un solo error no se puede aplicar. Si entrara a medias, los indicadores mezclarían datos completos con incompletos y el reporte diría algo falso sin que nadie lo notara. Es mejor corregir el archivo y subirlo de nuevo.
> - **Validar y luego aplicar.** Primero se ve la vista previa y lo que se descarta; nada cambia hasta pulsar *Aplicar*. Así la Analista confirma que subió el archivo correcto del mes correcto.

### Qué se descarta y por qué

Solo se guardan las columnas que usa algún indicador. Todo lo demás se descarta sin guardarse ni mostrarse. Si una columna descartada parece un dato personal (nombre, apellidos, CURP, RFC, NSS, correo, teléfono, domicilio, fecha de nacimiento, sexo, salario, cuenta bancaria…) la pantalla lo señala.

> **Por qué se calcula así.** Los sistemas suelen exportar mucho más de lo necesario. La Ley Federal de Protección de Datos Personales pide tratar solo los datos indispensables para el fin (principio de minimización). Para calcular la rotación basta un código de empleado y sus fechas: el nombre no aporta nada y solo agrega riesgo.

### Conciliación, bitácora y mes pendiente

- **Conciliación:** después de aplicar, el sistema compara el archivo contra lo que quedó en la base (conteos y sumas) y muestra si cuadra. Es la prueba de que no se perdió ni se duplicó nada.
- **Volver a cargar no duplica:** las vacantes se identifican por folio, las metas por empleado y mes, y la encuesta de clima de un mes reemplaza a la anterior de ese mes.
- **Bitácora de cargas:** quién subió qué archivo, cuándo, su huella SHA-256 (una especie de huella digital que cambia si se modifica un solo carácter), cuántas filas, qué columnas se descartaron y quién lo aplicó.
- **Archivos del mes pendiente:** mientras haya un mes cerrado sin cargar (hoy, septiembre de 2026), la pantalla ofrece los seis archivos de ese mes como los exportaría cada sistema de Nordika, con el botón **Archivo del mes** de cada fuente. Traen columnas de más (incluso nombres) que el sistema descarta. Cuando ya están cargados todos los meses cerrados, solo queda el **Formato vacío**. Estos archivos son de prueba: **con datos reales no aparecen**, porque serían datos inventados mezclados con los de la empresa; ahí la pantalla solo dice qué mes falta subir.
- **Mes completo:** un mes está completo cuando tiene sus cuatro fuentes mensuales (metas, capacitación, clima y productividad). Si la Analista elige en **Reportes** un mes al que le falta alguna, la pantalla lo avisa antes de generar: el reporte saldría sin esos indicadores. Los reportes automáticos esperan a que el mes esté completo.
- **Plantilla y vacantes:** no cuentan para que el mes esté completo, porque un mes sin altas, bajas ni contrataciones es normal. Pero si nadie las subió después de que cerró el mes, el sistema no distingue un mes tranquilo de uno olvidado. Por eso **Reportes** avisa ("Nadie ha subido la plantilla de personal desde que cerró septiembre…") sin impedir que se genere. Solo se revisan los meses que pasaron por Carga de datos, no la historia que ya estaba en la base.

## 6. Qué se analiza: los 10 indicadores

Cada indicador se calcula para cada área y para el consolidado de la empresa, mes por mes. Los umbrales de esta tabla son los valores iniciales; la Responsable de RRHH los ajusta desde Configuración según la realidad de la empresa.

| Proceso | Indicador | Unidad | Es peor si… | Atención | Crítico |
|---|---|---|---|---|---|
| Reclutamiento | Tiempo de contratación | días | sube | 45 | 60 |
| Reclutamiento | Costo por contratación | MXN | sube | 20,000 | 24,000 |
| Desempeño | Cumplimiento de metas | % | baja | 78 | 72 |
| Capacitación | Cobertura de capacitación | % | baja | 60 | 45 |
| Capacitación | Tasa de finalización | % | baja | 80 | 72 |
| Rotación | Rotación total | % | sube | 2.0 | 3.5 |
| Rotación | Rotación voluntaria | % | sube | 1.5 | 3.0 |
| Rotación | Rotación involuntaria | % | sube | 1.0 | 2.0 |
| Clima laboral | eNPS | puntos | baja | 10 | 0 |
| Productividad | Índice de productividad | % | baja | 68 | 62 |

A continuación, cada indicador con su fórmula, de dónde sale y por qué se calcula así.

### Tiempo de contratación
*Reclutamiento · Vacantes (ATS)*

**Fórmula:** promedio de días entre la fecha de apertura y la fecha de contratación, de las vacantes cubiertas en el mes.

> **Por qué se calcula así.** Mide qué tan rápido se cubren los puestos. Se cuenta en el mes en que se cubre la vacante porque hasta entonces se conoce su duración completa; una vacante abierta todavía no tiene tiempo final. Se usa el promedio porque es como lo reporta la mayoría de las empresas y es fácil de comparar.

### Costo por contratación
*Reclutamiento · Vacantes (ATS)*

**Fórmula:** suma del costo de los procesos de las vacantes cubiertas en el mes ÷ número de vacantes cubiertas.

> **Por qué se calcula así.** Indica cuánto cuesta en promedio traer a una persona. Se divide entre las vacantes cubiertas (no las abiertas) porque el costo de un proceso solo se conoce completo cuando termina.

### Cumplimiento de metas
*Desempeño · Metas de desempeño*

**Fórmula:** total de metas logradas ÷ total de metas asignadas × 100, sumando a todas las personas del área.

> **Por qué se calcula así.** Se suman primero las metas y luego se divide (en lugar de promediar el porcentaje de cada persona) para que alguien con 10 metas pese más que alguien con 1. Así el indicador refleja el trabajo total del área y una sola persona con pocas metas no lo distorsiona.

### Cobertura de capacitación
*Capacitación · Plantilla de personal + LMS*

**Fórmula:** personas activas inscritas en al menos un programa del mes ÷ personas activas en el mes × 100.

> **Por qué se calcula así.** Responde "¿a qué parte del equipo estamos capacitando?". Se cuenta a cada persona una sola vez aunque tome tres cursos, porque lo que interesa es el alcance, no el volumen. Se divide entre el personal activo de ese mes (quien ya se fue no cuenta). La definición de "capacitado" se confirma con RRHH de cada empresa.

### Tasa de finalización
*Capacitación · LMS*

**Fórmula:** inscripciones completadas ÷ total de inscripciones del mes × 100.

> **Por qué se calcula así.** Mide si la capacitación se aprovecha: inscribirse no sirve si no se termina. Junto al porcentaje se muestra el conteo ("62 de 80 inscritos completaron; 18 no") para que se entienda el tamaño real.

### Rotación total, voluntaria e involuntaria
*Rotación · Plantilla de personal*

**Fórmula:** bajas del mes ÷ plantilla promedio × 100. Plantilla promedio = (personas al inicio del mes + personas al inicio del mes siguiente) ÷ 2. La voluntaria y la involuntaria usan solo las bajas de ese tipo.

> **Por qué se calcula así.** Se divide entre el promedio y no entre la plantilla del inicio porque en un mes con muchas altas o bajas el número de personas cambia; el promedio representa mejor a cuántas personas había. Se separa en voluntaria (renuncias) e involuntaria (despidos) porque piden acciones muy distintas: la primera habla de retención y clima; la segunda, de selección o desempeño.

### eNPS (Employee Net Promoter Score)
*Clima laboral · Encuesta de clima*

**Fórmula:** % de promotores (puntaje 9 o 10) − % de detractores (puntaje 0 a 6), en la pregunta "¿recomendarías trabajar aquí?". Va de −100 a +100.

> **Por qué se calcula así.** Es la métrica de lealtad más usada en el mundo, así que se puede comparar con otras empresas. Los puntajes 7 y 8 (pasivos) no suman ni restan. Como su cero es arbitrario, sus cambios se reportan solo en puntos y nunca en porcentaje: pasar de +20 a −50 no es "−350 %", son 70 puntos menos.

### Índice de productividad
*Productividad · Proyectos y tickets*

**Fórmula:** horas efectivas ÷ horas disponibles × 100.

> **Por qué se calcula así.** Muestra qué parte del tiempo disponible se dedica a trabajo productivo. Se suman las horas del área antes de dividir, igual que en metas. Para medir el tamaño del grupo se convierten las horas en personas de tiempo completo (160 horas al mes = 1 persona).

### Comparaciones contra otros meses

- **Contra el mes anterior:** muestra la tendencia inmediata.
- **Contra el mismo mes del año anterior:** elimina la estacionalidad. En logística, por ejemplo, la rotación sube cada diciembre; compararla con noviembre exageraría el problema, compararla con el diciembre anterior dice si este año fue mejor o peor.
- Cada cambio se da en unidades del indicador ("+0.8 pts", "+5 días") y, cuando tiene sentido, también en porcentaje. El porcentaje solo se calcula sobre una base positiva, y nunca para el eNPS.
- Si el cambio es una mejora o un deterioro lo decide el sistema según el sentido del indicador (en rotación, subir es malo; en metas, subir es bueno), no la IA.

## 7. El semáforo y las reglas de cálculo

Cada indicador de cada área y mes recibe un estado. El estado decide qué se pinta de rojo, qué genera un aviso y qué debe mencionar obligatoriamente el reporte.

| Estado | Cuándo |
|---|---|
| **Crítico** (rojo) | El valor cruzó el umbral crítico. Genera un aviso y el reporte debe incluir una recomendación para él. |
| **Atención** (amarillo) | Cruzó el umbral de atención, pero no el crítico. |
| **En rango** (verde) | No cruzó ningún umbral. |
| **Por vigilar** | Está en verde, pero empeoró contra el mes anterior y además está a menos de 10 % del umbral de atención o se deterioró 10 % o más. Es una alerta temprana. |
| **Muestra insuficiente** | Se muestra el valor, pero sin color (ver la regla de muestra mínima). |

> **Por qué se calcula así.** Los umbrales los decide la Responsable de RRHH, no TI ni el sistema, porque definir qué es "grave" es una decisión de negocio. La Analista no los cambia: si pudiera mover un umbral, cambiaría lo que sus propios reportes marcan como alerta. Cada cambio queda en la bitácora con quién lo hizo y los valores de antes y después, y el sistema rechaza umbrales sin sentido (por ejemplo, un crítico más suave que el de atención o un porcentaje mayor a 100).

### Regla de grupo mínimo (privacidad)

Si un área tiene menos de 5 personas, no se muestran su eNPS, su cumplimiento de metas ni sus tres tasas de rotación. El consolidado de la empresa siempre se muestra.

> **Por qué se calcula así.** En un equipo de 4 personas, "rotación involuntaria 25 %" equivale a decir que despidieron a una persona concreta, y un eNPS de ese equipo deja adivinar quién respondió qué. Ocultar esos valores protege a las personas. El tamaño se mide de forma conservadora: se toma el menor entre las personas detrás del dato y el tamaño real del equipo. Los valores ocultos nunca llegan a la IA ni a los reportes.

### Regla de muestra mínima (capacitación)

En la cobertura y la tasa de finalización, si hay menos de 5 personas detrás del dato, el valor se muestra con su conteo, pero sin color de semáforo: no genera alerta y la IA lo menciona solo como "sin evaluar".

> **Por qué se calcula así.** Con una sola persona inscrita, el indicador salta de 100 % a 0 % según si terminó o no su curso, y eso marcaba toda un área en rojo. Una sola persona no representa la situación del área; su seguimiento se hace en el sistema de capacitación. Reclutamiento no entra en esta regla porque cada vacante es un hecho real, no una muestra.

### Nivel de confianza

Cada hallazgo y recomendación lleva un nivel de confianza calculado con reglas fijas (nunca por la IA):

| Confianza | Cuándo |
|---|---|
| Baja | Muestra menor a 10 personas o casos, o menos de 3 meses de historia. |
| Media | Muestra menor a 30, menos de 6 meses de historia o sin dato del mes anterior. |
| Alta | En cualquier otro caso. |

> **Por qué se calcula así.** Un cambio de 2 puntos en un área de 300 personas es una señal; en un área de 8 puede ser casualidad. La confianza le dice a quien lee el reporte cuánto peso darle a cada hallazgo. Con confianza baja tampoco se marca "Por vigilar", para no generar alarmas por ruido.

## 8. Cómo redacta la IA (y qué no puede hacer)

La IA convierte los indicadores ya calculados en un texto ejecutivo. Recibe una lista cerrada de hechos y solo puede hablar de ellos.

### Qué contiene cada reporte

| Sección | Contenido |
|---|---|
| Resumen ejecutivo | Máximo 3 oraciones: cuántos indicadores están en rojo y amarillo, y los más graves con su valor. |
| Hallazgos | De 3 a 5 (menos si el mes tiene pocos hechos). Cada uno cita los datos que lo respaldan, su confianza y su fuente. |
| Alertas y riesgos | Los indicadores que cruzaron un umbral y los que conviene vigilar. |
| Recomendaciones | De 1 a 3, a partir de una acción base definida para cada indicador. Siempre con su fuente y confianza. |
| Nota de RRHH | Opcional: contexto que agrega quien firma (por ejemplo, una causa ya conocida). Va firmada con su nombre y aparte del texto de la IA. |
| Anexo de metodología | Fórmulas, umbrales, fuentes y fecha de corte (en el PDF). |

En un mes sin alertas, la IA redacta un resumen de estabilidad con los indicadores más relevantes y su valor, para que la dirección sepa que se revisó y todo está en orden.

### Qué recibe la IA y qué no

| Recibe | Nunca recibe |
|---|---|
| Nombre de cada indicador, su valor y sus cambios (ya calculados y redondeados). | Nombres, códigos de empleado ni registros individuales. |
| El estado (rojo, amarillo, verde, por vigilar) y una frase neutra sobre los umbrales. | Los valores ocultos por la regla de grupo mínimo. |
| El tamaño de la muestra y una acción base sugerida por indicador. | Los umbrales numéricos, para que no haga comparaciones por su cuenta. |
| Las coincidencias que detecta el sistema ("eNPS y rotación están ambos en alerta"). | El nombre del área, cuando la IA está en la nube (se sustituye por "un área de la empresa"). |

### Las reglas que revisan cada respuesta (guardarrailes)

Antes de mostrarse, el código revisa la respuesta de la IA y la rechaza si:

- Contiene una cifra que no está en los datos que cita (cifras inventadas).
- Cita un dato que no se le entregó.
- Atribuye causas ("causó", "debido a", "se debe a"). Puede decir que dos cosas coinciden, pero no que una provocó la otra, porque los datos no lo demuestran.
- Omite algún indicador en alerta o por vigilar, o deja un indicador en rojo sin recomendación.
- Compara cifras contra los umbrales por su cuenta en lugar de usar la frase que le da el sistema.
- Habla del nivel de confianza (lo calcula y lo muestra el sistema).
- Es demasiado largo, o un hallazgo no incluye el valor de los datos que cita.

Además, la IA nunca propone acciones sobre personas concretas (despidos, sanciones).

### Si la IA se equivoca

Se le devuelven los errores para que corrija (hasta 3 intentos). Si no lo logra, empieza de cero (hasta 2 rondas). Si aun así falla, el reporte queda en **error** con el motivo y se puede preparar de nuevo. Nunca se rellena con un texto de plantilla.

> **Por qué se calcula así.** Un reporte de plantilla que parezca escrito para ese mes sería engañoso. Es preferible que el sistema diga "no pude" a que entregue algo que nadie redactó con los datos reales.

### Dónde corre la IA

| Opción | Dónde | Cuándo se usa |
|---|---|---|
| Ollama (Qwen3 8B) | En el propio servidor de la empresa. | Con datos reales es la única permitida: la información no sale de la empresa. Tarda de 2 a 5 minutos por reporte. |
| Groq | En la nube. | Solo con los datos ficticios de Nordika: responde en segundos. El sistema se niega a usarla si los datos son reales. |

## 9. Preparación, firma y descarga

Ningún reporte llega a la dirección sin que la Responsable de RRHH lo haya leído y firmado.

- **Quién prepara:** solo la Analista de RRHH, por iniciativa propia o porque Dirección o un gerente se lo pidió con **Pedir este reporte a RRHH** (el pedido le llega como aviso con el área y el mes ya elegidos). Dirección y los gerentes no generan reportes.
- **Quién firma:** la Responsable de RRHH, o su suplente mientras no está. Nunca firma quien preparó el reporte. Cada reporte dice desde el principio quién lo firmará.
- **Suplencia:** desde Configuración, la Responsable designa a una Analista que firma en su lugar hasta una fecha (máximo 90 días, una a la vez). Si la suplente preparó un reporte, lo firma la Responsable.
- **Aprobar:** con **Aprobar y firmar**, y una Nota de RRHH opcional (máximo 600 caracteres) que se publica firmada y aparte del texto de la IA.
- **Rechazar:** exige un motivo (al menos 10 caracteres). Si se rechaza, se prepara uno nuevo.
- La decisión es definitiva y el texto de la IA no se edita. Si dos personas firman a la vez, solo cuenta la primera decisión.

> **Por qué se calcula así.** Si el texto se pudiera editar, la bitácora mezclaría lo que escribió la IA con lo que escribió una persona, y ya no se sabría qué validaron las reglas automáticas. Aprobar o rechazar completo mantiene clara la responsabilidad de cada parte; el contexto humano va en la Nota de RRHH, separado y con nombre.

### Formatos de descarga

| Formato | Contenido |
|---|---|
| PDF (tamaño carta) | Portada con área, mes y quién firmó; resumen con el conteo por semáforo; indicadores con sus variaciones; hallazgos, alertas y recomendaciones; la Nota de RRHH si la hay; y un anexo con fórmulas, umbrales, fuentes y bitácora. Cada página dice "Confidencial" y el número de reporte. |
| Presentación (PowerPoint 16:9) | Las mismas secciones, una por diapositiva, lista para una junta de dirección. |

- Solo se descargan los reportes aprobados. Cada rol descarga solo lo que puede ver.
- El archivo se arma con lo aprobado tal como quedó guardado: no se recalcula nada, así que se distribuye exactamente lo que se revisó.
- Cada descarga queda registrada: quién, en qué formato y cuándo. Si no se puede registrar, no se entrega el archivo.

## 10. Avisos y reportes automáticos

### Avisos

| Qué pasa | A quién le llega el aviso |
|---|---|
| Un indicador del consolidado queda en rojo | Dirección y RRHH |
| Un indicador de un área queda en rojo | El gerente de esa área y RRHH |
| Dirección o un gerente pide un reporte | Las Analistas de RRHH |
| Un reporte está listo para firmar | La Responsable de RRHH y su suplente vigente, salvo quien lo preparó |
| Un reporte se aprueba | Su audiencia (Dirección si es el consolidado, el gerente si es su área; así le llega a quien lo pidió) y la Analista que lo preparó |
| Un reporte se rechaza | Quien lo preparó |
| Un reporte automático no se pudo generar | RRHH |

- TI no recibe avisos, porque todos hablan de datos de colaboradores.
- Un mismo evento no se avisa dos veces. Si otro indicador del mismo mes se pone en rojo, llega un aviso nuevo con la lista completa.
- **Correo opcional y sin datos:** si se activa, solo dice "tienes N avisos nuevos" con la liga al sistema. Nunca lleva áreas, nombres ni cifras, así que ningún dato de RRHH sale por correo.

### Programación mensual

RRHH la activa en Configuración y elige el día del mes (1 a 28). A partir de ese día se generan solos los reportes del último mes cerrado: el consolidado y uno por cada área. Solo se generan cuando el mes está **completo**, con las cuatro fuentes mensuales cargadas (metas, capacitación, clima y productividad); si falta alguna, el sistema espera y los genera en cuanto se aplica la última. Cada mes se genera una sola vez, aunque el servidor se reinicie. Si el servidor estuvo apagado el día programado, se pone al día al volver. Los reportes automáticos también los firma la Responsable o su suplente.

> **Por qué se calcula así.** Un mes en curso nunca se reporta, aunque ya tenga datos parciales: un reporte del 15 de octubre diría que la rotación de octubre es la mitad de la real.

## 11. Seguridad, privacidad y respaldos

Todas las medidas funcionan igual con los datos de Nordika que con los de cualquier empresa: nada se apaga.

| Medida | Cómo funciona |
|---|---|
| Verificación en dos pasos | Además de la contraseña, un código de 6 dígitos de una app de autenticación (Google o Microsoft Authenticator). Obligatoria para Dirección, RRHH y TI; opcional para gerentes. Al activarla se entregan 10 códigos de respaldo de un solo uso. |
| Secreto del código cifrado | El secreto de la app de cada cuenta se guarda cifrado (AES-256) con una llave que no está en la base. Quien obtenga una copia de la base no puede generar códigos, y copiar el secreto de una cuenta a otra no sirve. |
| Contraseñas | Mínimo 10 caracteres. Se guardan solo cifradas de forma irreversible (scrypt con sal): nadie, ni TI, puede leerlas. |
| Bloqueo por intentos | Tras 5 intentos fallidos seguidos (de contraseña o de código), la cuenta se bloquea unos minutos. |
| Contraseña temporal | Cuando TI crea una cuenta o restablece una contraseña, el sistema genera una temporal. Al entrar, la persona elige la suya antes de hacer cualquier otra cosa: TI nunca conoce la definitiva. |
| Sesiones | Caducan solas (60 minutos por defecto) y se guardan solo en la pestaña del navegador. Desactivar una cuenta o cambiarle el rol surte efecto de inmediato. |
| Cuentas personales | Nunca compartidas. No se borran, se desactivan, para que las bitácoras siempre digan de quién se trata. |
| Bitácoras | De cuentas, umbrales, cargas, reportes, firmas y descargas: quién, qué y cuándo, con valores de antes y después. Nunca guardan contraseñas. |
| Datos mínimos | Solo códigos de empleado; nombres y datos personales se descartan al cargar. |
| IA local | Con datos reales la IA corre en el servidor propio. Un candado impide usar la IA en la nube si los datos son reales. |
| Base de datos protegida | Solo acepta conexiones del mismo equipo, y todas las tablas tienen seguridad por fila: nadie puede leerlas desde fuera aunque conozca la dirección de la base. |

> **El teléfono simulado.** Para que cualquiera pueda recorrer el sistema sin instalar una app en su celular, junto al formulario aparece un teléfono con la app de autenticación y el código vigente. La pantalla aclara que **no es parte del sistema**: es una simulación de la app que cada persona tendría en su propio celular. La verificación es real: el código se pide, se valida y cuenta como intento. El teléfono simulado solo funciona con los datos ficticios de Nordika y con sus cinco cuentas; con datos reales se apaga y el código aparece únicamente en el celular de cada persona.

### Respaldos

TI respalda la base todos los días con un script (`python -m scripts.respaldo`, programado en el Programador de tareas de Windows):

- **Cada respaldo se prueba:** se restaura en una base temporal y se comparan las filas de cada tabla con la base real. Si no cuadra, el respaldo se marca como fallido.
- Cada respaldo lleva su huella SHA-256; al restaurar se verifica, para no usar un archivo dañado o cambiado.
- **La llave del MFA se guarda aparte**, en otra unidad o una USB, nunca junto a los respaldos. Si se pierde, solo sirven los códigos de respaldo y TI tiene que reiniciar la verificación de cada cuenta.
- Restaurar exige apagar la API y escribir el nombre de la base para confirmar, y antes se guarda una copia del estado actual.

### Cumplimiento

El diseño sigue la Ley Federal de Protección de Datos Personales en Posesión de los Particulares: se tratan solo los datos indispensables, los datos reales no salen de la infraestructura de la empresa, el acceso es por rol y cada operación queda registrada.

## 12. Glosario

| Término | Definición |
|---|---|
| Analista de RRHH | Quien carga los datos de cada mes y prepara los reportes. No los firma. |
| ATS | Sistema de seguimiento de candidatos: donde se administran las vacantes y el reclutamiento. |
| Bitácora | Registro permanente de quién hizo qué y cuándo; desde el sistema no se puede editar ni borrar. |
| Conciliación | Comparar lo que decía el archivo contra lo que quedó en la base para confirmar que cuadra. |
| Consolidado | El indicador de toda la empresa, sumando todas las áreas. |
| eNPS | *Employee Net Promoter Score*: % de promotores menos % de detractores en la pregunta "¿recomendarías trabajar aquí?". |
| Guardarrailes | Reglas automáticas que revisan cada texto de la IA antes de mostrarlo. |
| HRIS | Sistema de información de RRHH o nómina: altas, bajas y datos de cada colaborador. |
| Huella SHA-256 | Código que identifica un archivo; cambia por completo si se modifica un solo carácter. |
| LMS | Plataforma de capacitación: cursos, inscripciones y avance. |
| Mes pendiente | El primer mes cerrado que todavía no tiene sus archivos cargados (hoy, septiembre de 2026). |
| Nota de RRHH | Contexto opcional que agrega quien firma un reporte; va con su nombre y aparte del texto de la IA. |
| Pedido | Solicitud de un reporte que Dirección o un gerente hacen a RRHH. |
| Plantilla promedio | Promedio de personas entre el inicio del mes y el inicio del mes siguiente. |
| Respaldo | Copia completa de la base, probada y con su huella, para recuperarla si algo falla. |
| Responsable de RRHH | Quien firma (aprueba o rechaza) los reportes y cambia los umbrales. No los prepara. |
| Suplencia | Periodo en que una Analista firma en lugar de la Responsable (máximo 90 días). |
| Umbral | Valor a partir del cual un indicador pasa a amarillo (atención) o a rojo (crítico). |
| Verificación en dos pasos | Pedir, además de la contraseña, un código temporal del celular (estándar TOTP). |
