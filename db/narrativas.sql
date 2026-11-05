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

-- Paso 8: revision humana antes de distribuir (RF-05) y quien la reviso
-- (bitacora RF-11). Solo se revisan las narrativas en estado 'lista'; la
-- decision es definitiva: si se rechaza, se solicita una nueva.
ALTER TABLE narrativas ADD COLUMN IF NOT EXISTS revision TEXT NOT NULL DEFAULT 'pendiente'
    CHECK (revision IN ('pendiente', 'aprobada', 'rechazada'));
ALTER TABLE narrativas ADD COLUMN IF NOT EXISTS revisada_por TEXT;
ALTER TABLE narrativas ADD COLUMN IF NOT EXISTS revisada_en TIMESTAMPTZ;
ALTER TABLE narrativas ADD COLUMN IF NOT EXISTS comentario_revision TEXT;

-- Paso 9: bitacora de exportaciones (RF-08, RF-11). Solo se exportan las
-- narrativas aprobadas; cada descarga registra quien, en que formato y cuando.
CREATE TABLE IF NOT EXISTS exportaciones (
    id            SERIAL PRIMARY KEY,
    narrativa_id  INTEGER NOT NULL REFERENCES narrativas (id) ON DELETE CASCADE,
    formato       TEXT NOT NULL CHECK (formato IN ('pdf', 'pptx')),
    usuario       TEXT NOT NULL,
    exportada_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS exportaciones_narrativa ON exportaciones (narrativa_id);

-- Paso 10: narrativas que genero la programacion mensual (RF-07). No
-- tienen solicitada_por, asi que las puede revisar cualquier persona
-- de RRHH (seccion 10.3.9).
ALTER TABLE narrativas ADD COLUMN IF NOT EXISTS programada BOOLEAN NOT NULL DEFAULT false;

-- Nota de RRHH: contexto que agrega quien firma al aprobar (p. ej. "la
-- rotacion de Almacen sube por el cierre del turno nocturno, ya planeado").
-- Va aparte y firmada: el texto de la IA nunca se edita.
ALTER TABLE narrativas ADD COLUMN IF NOT EXISTS nota_rrhh TEXT;
-- Con que cargo firmo quien la reviso ("Responsable de RRHH" o "Suplente
-- de ... hasta ..."): el cargo de ese dia, aunque despues cambie.
ALTER TABLE narrativas ADD COLUMN IF NOT EXISTS firmada_como TEXT;

-- Desde donde (IP) se firmo cada reporte y se descargo cada archivo (bitacora).
ALTER TABLE narrativas ADD COLUMN IF NOT EXISTS revisada_desde TEXT;
ALTER TABLE exportaciones ADD COLUMN IF NOT EXISTS origen TEXT;

-- Lo que ya se firmo no cambia, y nadie inserta un reporte ya firmado. El
-- superusuario queda fuera (migraciones, renombrar cuentas de demostracion): la
-- regla es para la cuenta de la API, que no es duena de la tabla y no puede
-- quitar el trigger. Aunque alguien ejecutara codigo en la API, no podria
-- cambiar el texto de un reporte firmado.
CREATE OR REPLACE FUNCTION narrativa_firmada_no_cambia() RETURNS trigger AS $$
BEGIN
    IF current_setting('is_superuser') = 'on' THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.revision <> 'pendiente' OR NEW.revisada_por IS NOT NULL THEN
            RAISE EXCEPTION 'Un reporte nace pendiente de firma';
        END IF;
    ELSIF OLD.revision <> 'pendiente' AND (
        NEW.resultado, NEW.revision, NEW.revisada_por, NEW.revisada_en, NEW.nota_rrhh, NEW.firmada_como,
        NEW.comentario_revision, NEW.solicitada_por, NEW.area_id, NEW.periodo
    ) IS DISTINCT FROM (
        OLD.resultado, OLD.revision, OLD.revisada_por, OLD.revisada_en, OLD.nota_rrhh, OLD.firmada_como,
        OLD.comentario_revision, OLD.solicitada_por, OLD.area_id, OLD.periodo
    ) THEN
        RAISE EXCEPTION 'Un reporte firmado no se puede modificar';
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS narrativa_firmada ON narrativas;
CREATE TRIGGER narrativa_firmada BEFORE INSERT OR UPDATE ON narrativas
    FOR EACH ROW EXECUTE FUNCTION narrativa_firmada_no_cambia();
