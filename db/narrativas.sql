-- ============================================================
-- Narrativas generadas por la IA (RF-07, RF-10, RF-11)
-- Cada fila es una solicitud: se crea "en_proceso", el modelo la
-- redacta en segundo plano y termina "lista" o "error".
-- Guarda que proveedor y modelo la generaron (bitacora/auditoria).
--
-- Es seguro ejecutarlo varias veces (CREATE ... IF NOT EXISTS):
-- la API lo ejecuta al arrancar.
-- ============================================================

CREATE TABLE IF NOT EXISTS narrativas (
    id              SERIAL PRIMARY KEY,
    area_id         INTEGER NOT NULL,          -- 0 = consolidado corporativo
    periodo         DATE NOT NULL,             -- primer dia del mes
    estado          TEXT NOT NULL DEFAULT 'en_proceso'
                    CHECK (estado IN ('en_proceso', 'lista', 'error')),
    solicitada_en   TIMESTAMPTZ NOT NULL DEFAULT now(),
    terminada_en    TIMESTAMPTZ,
    proveedor       TEXT,
    modelo          TEXT,
    version_prompt  TEXT,
    rondas          INTEGER NOT NULL DEFAULT 0, -- veces que se pidio al modelo desde cero
    resultado       JSONB,                      -- narrativa completa (estado 'lista')
    error           TEXT,                       -- motivo (estado 'error')
    detalle_error   JSONB                       -- errores de validacion de cada intento
);

CREATE INDEX IF NOT EXISTS narrativas_area_periodo ON narrativas (area_id, periodo);

-- Paso 6: quien la solicito (bitacora RF-11). ADD COLUMN IF NOT EXISTS para
-- que funcione tambien en bases creadas antes de este paso.
ALTER TABLE narrativas ADD COLUMN IF NOT EXISTS solicitada_por TEXT;
