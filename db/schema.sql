-- ============================================================
-- Motor Inteligente de Reportes Ejecutivos de RRHH
-- Esquema de las FUENTES simuladas (Paso 2)
-- Cada tabla existe porque alguna formula de la seccion 10.2
-- del PRD necesita esos campos.
-- Las tablas de usuarios, umbrales, reportes y auditoria se
-- crean en pasos posteriores.
-- ============================================================

DROP TABLE IF EXISTS
    respuestas_clima,
    productividad,
    inscripciones_capacitacion,
    programas_capacitacion,
    metas_desempeno,
    candidatos,
    vacantes,
    empleados,
    areas
CASCADE;

-- Catalogo de areas de la empresa
CREATE TABLE areas (
    id      SERIAL PRIMARY KEY,
    nombre  TEXT NOT NULL UNIQUE
);

-- HRIS / Nomina -> Tasa de rotacion, headcount promedio
-- Solo se guarda un codigo: no hay nombres ni datos personales.
CREATE TABLE empleados (
    id             SERIAL PRIMARY KEY,
    codigo         TEXT NOT NULL UNIQUE,
    area_id        INT  NOT NULL REFERENCES areas(id),
    fecha_ingreso  DATE NOT NULL,
    fecha_baja     DATE,
    tipo_baja      TEXT CHECK (tipo_baja IN ('voluntaria', 'involuntaria')),
    CHECK ((fecha_baja IS NULL) = (tipo_baja IS NULL)),
    CHECK (fecha_baja IS NULL OR fecha_baja >= fecha_ingreso)
);

-- ATS -> Tiempo de contratacion, costo por contratacion
CREATE TABLE vacantes (
    id                  SERIAL PRIMARY KEY,
    area_id             INT NOT NULL REFERENCES areas(id),
    fecha_apertura      DATE NOT NULL,
    fecha_contratacion  DATE,            -- NULL = vacante aun abierta
    costo_proceso       NUMERIC(12, 2) NOT NULL,  -- MXN
    CHECK (fecha_contratacion IS NULL OR fecha_contratacion >= fecha_apertura)
);

-- ATS -> Tasa de conversion de candidatos
CREATE TABLE candidatos (
    id           SERIAL PRIMARY KEY,
    vacante_id   INT NOT NULL REFERENCES vacantes(id),
    etapa_final  TEXT NOT NULL
        CHECK (etapa_final IN ('aplicado', 'entrevista', 'oferta', 'contratado'))
);

-- Sistema de desempeno -> porcentaje de cumplimiento de metas
-- periodo = primer dia del mes evaluado
CREATE TABLE metas_desempeno (
    id               SERIAL PRIMARY KEY,
    empleado_id      INT  NOT NULL REFERENCES empleados(id),
    periodo          DATE NOT NULL,
    metas_asignadas  INT  NOT NULL CHECK (metas_asignadas > 0),
    metas_logradas   INT  NOT NULL CHECK (metas_logradas >= 0),
    calificacion     SMALLINT NOT NULL CHECK (calificacion BETWEEN 1 AND 5),
    UNIQUE (empleado_id, periodo),
    CHECK (metas_logradas <= metas_asignadas)
);

-- LMS -> Cobertura, tasa de finalizacion, horas
-- area_id NULL = programa dirigido a toda la empresa
CREATE TABLE programas_capacitacion (
    id       SERIAL PRIMARY KEY,
    nombre   TEXT NOT NULL,
    horas    NUMERIC(5, 1) NOT NULL,
    periodo  DATE NOT NULL,
    area_id  INT REFERENCES areas(id)
);

CREATE TABLE inscripciones_capacitacion (
    id              SERIAL PRIMARY KEY,
    programa_id     INT NOT NULL REFERENCES programas_capacitacion(id),
    empleado_id     INT NOT NULL REFERENCES empleados(id),
    completado      BOOLEAN NOT NULL,
    horas_cursadas  NUMERIC(5, 1) NOT NULL,
    UNIQUE (programa_id, empleado_id)
);

-- Encuestas de clima (CSV) -> eNPS, satisfaccion por dimension
-- Respuestas ANONIMAS: sin empleado_id, solo area y periodo.
-- eNPS usa dimension = 'enps' (9-10 promotor, 7-8 pasivo, 0-6 detractor).
CREATE TABLE respuestas_clima (
    id         SERIAL PRIMARY KEY,
    area_id    INT  NOT NULL REFERENCES areas(id),
    periodo    DATE NOT NULL,
    dimension  TEXT NOT NULL
        CHECK (dimension IN ('enps', 'satisfaccion', 'liderazgo', 'carga_trabajo')),
    puntaje    SMALLINT NOT NULL CHECK (puntaje BETWEEN 0 AND 10)
);

-- Sistemas de proyectos/tickets -> Indice de productividad
CREATE TABLE productividad (
    id                        SERIAL PRIMARY KEY,
    area_id                   INT  NOT NULL REFERENCES areas(id),
    periodo                   DATE NOT NULL,
    horas_efectivas           NUMERIC(10, 1) NOT NULL,
    horas_disponibles         NUMERIC(10, 1) NOT NULL,
    entregables_planificados  INT NOT NULL,
    entregables_completados   INT NOT NULL,
    UNIQUE (area_id, periodo),
    CHECK (entregables_completados <= entregables_planificados)
);

-- Indices para las consultas del motor analitico
CREATE INDEX idx_empleados_area      ON empleados (area_id);
CREATE INDEX idx_empleados_baja      ON empleados (fecha_baja);
CREATE INDEX idx_vacantes_area       ON vacantes (area_id, fecha_apertura);
CREATE INDEX idx_metas_periodo       ON metas_desempeno (periodo);
CREATE INDEX idx_clima_area_periodo  ON respuestas_clima (area_id, periodo);
