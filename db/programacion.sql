-- ============================================================
-- Programacion mensual de reportes (paso 10, RF-07)
--
-- programacion: una sola fila con la configuracion que edita RRHH
-- desde el panel (RF-12). Nace desactivada: activarla es decision de
-- RRHH, porque cada corrida genera un reporte por area que hay que
-- revisar.
--
-- corridas_programadas: un mes se genera UNA sola vez. La llave
-- primaria hace que, aunque la API y el script del Programador de
-- tareas revisen al mismo tiempo, solo uno gane (INSERT ... ON
-- CONFLICT DO NOTHING).
--
-- Es seguro ejecutarlo varias veces: la API lo ejecuta al arrancar.
-- ============================================================

CREATE TABLE IF NOT EXISTS programacion (
    id              INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    activa          BOOLEAN NOT NULL DEFAULT false,
    dia_del_mes     INTEGER NOT NULL DEFAULT 5 CHECK (dia_del_mes BETWEEN 1 AND 28),
    modificada_por  TEXT,
    modificada_en   TIMESTAMPTZ
);

INSERT INTO programacion (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS corridas_programadas (
    periodo      DATE PRIMARY KEY,                -- mes reportado (primer dia)
    iniciada_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    origen       TEXT NOT NULL CHECK (origen IN ('api', 'script')),
    narrativas   INTEGER NOT NULL DEFAULT 0       -- reportes que se solicitaron
);
