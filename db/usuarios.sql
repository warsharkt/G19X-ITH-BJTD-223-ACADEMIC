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

-- Firma de reportes (regla 10.3.9): dentro de RRHH, la Analista prepara
-- (carga los datos y genera los reportes) y la Responsable los firma
-- (aprueba o rechaza). firma_reportes = true marca a la Responsable.
-- Solo una cuenta de RRHH puede tenerlo, y solo lo da o lo quita una
-- Responsable (o la consola del servidor): TI, nunca (app/seguridad.py).
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS firma_reportes BOOLEAN NOT NULL DEFAULT false;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'usuarios_firma_solo_rrhh') THEN
        ALTER TABLE usuarios ADD CONSTRAINT usuarios_firma_solo_rrhh CHECK (NOT firma_reportes OR rol = 'rrhh');
    END IF;
END $$;

-- Aprobacion de accesos (regla 10.3.2): TI no ve datos de colaboradores. Si
-- TI crea una cuenta con datos, le cambia rol o area, o restablece su acceso,
-- la cuenta queda en espera hasta que una Responsable de RRHH la apruebe: asi
-- TI no puede abrirse la puerta a si misma. Lo que se hace desde la consola
-- del servidor no pasa por aqui.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS acceso_aprobado BOOLEAN NOT NULL DEFAULT true;

-- Hasta cuando sirve una contrasena temporal (NULL si no es temporal).
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS temporal_vence TIMESTAMPTZ;

-- Bitacora de accesos: cada entrada y cada intento fallido, con su IP. Los
-- nombres que no existen no se guardan: a veces la gente escribe su contrasena
-- en el campo de usuario. Se purga despues de un ano.
CREATE TABLE IF NOT EXISTS accesos (
    id       BIGSERIAL PRIMARY KEY,
    usuario  TEXT NOT NULL,
    evento   TEXT NOT NULL CHECK (evento IN ('entrada', 'fallo')),
    origen   TEXT,
    momento  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS accesos_momento ON accesos (momento);

-- Suplencias: mientras la Responsable no esta, designa a una Analista que
-- firma en su lugar hasta una fecha. Nunca se borran: cancelar deja quien
-- y cuando (bitacora RF-11).
CREATE TABLE IF NOT EXISTS suplencias (
    id            SERIAL PRIMARY KEY,
    suplente      TEXT NOT NULL,              -- usuario que firma en su lugar
    titular       TEXT NOT NULL,              -- Responsable que la designa
    desde         DATE NOT NULL,
    hasta         DATE NOT NULL,
    motivo        TEXT,
    creada_en     TIMESTAMPTZ NOT NULL DEFAULT now(),
    cancelada_por TEXT,
    cancelada_en  TIMESTAMPTZ,
    CHECK (hasta >= desde)
);

-- Pedidos de reporte: Direccion o un gerente pide a RRHH un reporte fuera
-- del calendario. No genera nada: avisa a las Analistas de RRHH.
CREATE TABLE IF NOT EXISTS pedidos_reporte (
    id          SERIAL PRIMARY KEY,
    area_id     INTEGER NOT NULL,             -- 0 = consolidado corporativo
    periodo     DATE NOT NULL,
    comentario  TEXT,
    pedido_por  TEXT NOT NULL,
    pedido_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bloqueo por intentos fallidos, por nombre de usuario Y por origen (IP).
-- Antes el bloqueo era de toda la cuenta: cualquiera podia dejar bloqueada a
-- la Responsable para siempre con un intento cada 15 minutos. Ahora quien se
-- equivoca solo bloquea su propio equipo; si se bloquean varios origenes a
-- la vez (ataque desde varios equipos), se bloquea el usuario completo.
-- Va por el nombre escrito, exista o no la cuenta: asi un usuario inventado
-- se bloquea igual que uno real y el 429 no revela que cuentas existen.
-- Se borra al entrar bien desde ese origen; las filas viejas se purgan.
DO $$
BEGIN
    -- la primera version (noviembre de 2026) iba por usuario_id: sus filas son
    -- temporales, se puede recrear sin perder nada
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'bloqueos_acceso' AND column_name = 'usuario_id'
    ) THEN
        DROP TABLE bloqueos_acceso;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS bloqueos_acceso (
    usuario          TEXT NOT NULL,              -- como se escribio, en minusculas
    origen           TEXT NOT NULL,
    intentos         INTEGER NOT NULL DEFAULT 0,
    bloqueado_hasta  TIMESTAMPTZ,
    actualizado_en   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (usuario, origen)
);

-- Desde donde (IP) se hizo cada cambio de cuenta. NULL: consola o arranque.
ALTER TABLE usuarios_cambios ADD COLUMN IF NOT EXISTS origen TEXT;
