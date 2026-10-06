-- ============================================================
-- Avisos dentro de la app (paso 10, RF-09)
-- Una fila por persona destinataria. El titulo puede nombrar un
-- area o un indicador, asi que al leerlos la API vuelve a filtrar
-- por las areas que la persona puede ver HOY (si le cambian el rol,
-- deja de ver los avisos que ya no le corresponden).
--
-- El correo (opcional) nunca lleva el titulo: solo "tienes N avisos
-- nuevos" y la liga. correo_enviado_en evita mandar dos veces.
--
-- Es seguro ejecutarlo varias veces: la API lo ejecuta al arrancar.
-- Va despues de usuarios.sql (llave foranea).
-- ============================================================

CREATE TABLE IF NOT EXISTS avisos (
    id                 SERIAL PRIMARY KEY,
    usuario_id         INTEGER NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    tipo               TEXT NOT NULL
                       CHECK (tipo IN ('alerta', 'revision', 'aprobado', 'rechazado', 'error')),
    area_id            INTEGER NOT NULL,          -- 0 = consolidado corporativo
    titulo             TEXT NOT NULL,
    enlace             TEXT NOT NULL,             -- ruta del tablero, sin dominio
    clave              TEXT NOT NULL,             -- el mismo evento no se avisa dos veces
    creado_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    leido_en           TIMESTAMPTZ,
    correo_enviado_en  TIMESTAMPTZ,
    UNIQUE (usuario_id, clave)
);

CREATE INDEX IF NOT EXISTS avisos_usuario ON avisos (usuario_id, leido_en);
