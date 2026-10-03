-- ============================================================
-- Usuarios del sistema y su rol (RF-06, regla 10.3.2)
--   direccion -> solo el consolidado corporativo
--   rrhh      -> consolidado y detalle de todas las areas
--   gerente   -> solo su area (area_id obligatorio)
--   admin_ti  -> configuracion y catalogos; sin datos de colaboradores
--
-- No se guardan contrasenas, solo su hash (scrypt con sal).
-- Sin llave foranea a `areas`: scripts/seed.py borra y recrea esa
-- tabla y se llevaria la restriccion; el area se valida al crear el
-- usuario (scripts/crear_usuario.py).
--
-- Es seguro ejecutarlo varias veces: la API lo ejecuta al arrancar.
-- ============================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id                 SERIAL PRIMARY KEY,
    usuario            TEXT NOT NULL UNIQUE,
    nombre             TEXT NOT NULL,
    rol                TEXT NOT NULL CHECK (rol IN ('direccion', 'rrhh', 'gerente', 'admin_ti')),
    area_id            INTEGER,
    contrasena_hash    TEXT NOT NULL,
    activo             BOOLEAN NOT NULL DEFAULT true,
    intentos_fallidos  INTEGER NOT NULL DEFAULT 0,     -- seguidos; se reinicia al entrar
    bloqueado_hasta    TIMESTAMPTZ,                    -- bloqueo temporal por intentos fallidos
    creado_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultimo_acceso      TIMESTAMPTZ,
    CHECK ((rol = 'gerente') = (area_id IS NOT NULL))
);
