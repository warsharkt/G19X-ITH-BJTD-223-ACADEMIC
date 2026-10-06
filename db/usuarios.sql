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

-- Paso 10: correo opcional para avisar que hay avisos nuevos. El
-- correo nunca lleva datos de RRHH, solo la liga para entrar.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS correo TEXT;

-- Administracion de usuarios desde el panel (RF-11, RF-12).
-- debe_cambiar_contrasena: TI pone una contrasena TEMPORAL y la persona
--   elige la suya al entrar; TI nunca conoce la definitiva.
-- version_sesion: va dentro del token. Al restablecer la contrasena o el
--   MFA sube, y los tokens anteriores dejan de servir.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS debe_cambiar_contrasena BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS version_sesion INTEGER NOT NULL DEFAULT 0;

-- Autenticacion multifactor TOTP (hito 6.1). mfa_secreto existe desde que
-- la persona empieza a configurarlo; mfa_activo, solo cuando confirma con
-- un codigo. mfa_ultimo_paso evita usar dos veces el mismo codigo.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS mfa_secreto TEXT;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS mfa_activo BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS mfa_ultimo_paso BIGINT;

-- Codigos de respaldo de un solo uso (si se pierde el telefono). Solo se
-- guarda su hash; se muestran una sola vez al activar el MFA.
CREATE TABLE IF NOT EXISTS codigos_respaldo (
    id           SERIAL PRIMARY KEY,
    usuario_id   INTEGER NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    codigo_hash  TEXT NOT NULL,
    usado_en     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS codigos_respaldo_usuario ON codigos_respaldo (usuario_id);

-- Bitacora de cuentas (RF-11): quien creo o modifico cada usuario, cuando y
-- que cambio. Sin llave foranea: las cuentas no se borran (se desactivan) y
-- la bitacora no debe perderse. Nunca guarda contrasenas ni secretos.
CREATE TABLE IF NOT EXISTS usuarios_cambios (
    id         SERIAL PRIMARY KEY,
    usuario    TEXT NOT NULL,                  -- cuenta afectada
    accion     TEXT NOT NULL,
    detalle    JSONB NOT NULL DEFAULT '{}',    -- {"campo": [antes, despues]}
    hecho_por  TEXT NOT NULL,                  -- usuario, o "consola:<usuario de Windows>"
    hecho_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS usuarios_cambios_usuario ON usuarios_cambios (usuario);
