-- ============================================================
-- Carga de datos desde los sistemas fuente (hito 11, RF-01)
-- RRHH sube el archivo que exporta cada sistema (CSV o Excel). Se valida
-- completo y, si no tiene errores, se aplica. Cada carga queda aqui:
-- quien, cuando, que archivo (con su huella SHA-256), cuantas filas,
-- que columnas se descartaron y el resultado de la conciliacion.
--
-- Es seguro ejecutarlo varias veces: la API lo ejecuta al arrancar.
-- ============================================================

CREATE TABLE IF NOT EXISTS cargas (
    id            SERIAL PRIMARY KEY,
    fuente        TEXT NOT NULL,
    archivo       TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    bytes         INTEGER NOT NULL,
    filas         INTEGER NOT NULL DEFAULT 0,
    estado        TEXT NOT NULL CHECK (estado IN ('validada', 'con_errores', 'aplicada', 'descartada')),
    errores       JSONB NOT NULL DEFAULT '[]',   -- [{fila, columna, mensaje}]
    descartadas   JSONB NOT NULL DEFAULT '[]',   -- columnas que no se guardan (p. ej. datos personales)
    periodos      JSONB NOT NULL DEFAULT '[]',   -- meses que abarca el archivo
    datos         JSONB,                         -- filas listas para aplicar; se borran al aplicar o descartar
    resultado     JSONB,                         -- nuevas, actualizadas y conciliacion
    subida_por    TEXT NOT NULL,
    subida_en     TIMESTAMPTZ NOT NULL DEFAULT now(),
    aplicada_por  TEXT,
    aplicada_en   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS cargas_fuente ON cargas (fuente, subida_en);

-- El ATS identifica cada vacante con un folio: permite volver a cargar el
-- mismo archivo sin duplicar vacantes. Las vacantes del seed no tienen folio.
ALTER TABLE vacantes ADD COLUMN IF NOT EXISTS folio TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS vacantes_folio ON vacantes (folio);
