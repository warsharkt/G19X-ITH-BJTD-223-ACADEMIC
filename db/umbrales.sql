-- ============================================================
-- Umbrales de atencion y criticos por indicador (regla 10.3.3)
-- Los valores iniciales son PLACEHOLDERS: RRHH los debe validar
-- y luego editarlos desde el panel admin (RF-12).
--
-- Es seguro ejecutarlo varias veces: no borra la tabla y no
-- pisa los umbrales que ya hayas modificado (ON CONFLICT DO NOTHING).
-- sentido:
--   mayor_es_peor -> rojo si valor >= critico, amarillo si >= atencion
--   menor_es_peor -> rojo si valor <= critico, amarillo si <= atencion
-- ============================================================

CREATE TABLE IF NOT EXISTS umbrales (
    indicador        TEXT PRIMARY KEY,
    nombre           TEXT NOT NULL,
    unidad           TEXT NOT NULL,
    sentido          TEXT NOT NULL CHECK (sentido IN ('mayor_es_peor', 'menor_es_peor')),
    umbral_atencion  NUMERIC NOT NULL,
    umbral_critico   NUMERIC NOT NULL,
    CHECK (
        (sentido = 'mayor_es_peor' AND umbral_critico >= umbral_atencion) OR
        (sentido = 'menor_es_peor' AND umbral_critico <= umbral_atencion)
    )
);

INSERT INTO umbrales (indicador, nombre, unidad, sentido, umbral_atencion, umbral_critico) VALUES
    ('tiempo_contratacion',    'Tiempo de contratación',            'días',   'mayor_es_peor', 45,    60),
    ('costo_por_contratacion', 'Costo por contratación',            'MXN',    'mayor_es_peor', 20000, 24000),
    ('cumplimiento_metas',     'Cumplimiento de metas',             '%',      'menor_es_peor', 78,    72),
    ('cobertura_capacitacion', 'Cobertura de capacitación',         '%',      'menor_es_peor', 60,    45),
    ('tasa_finalizacion',      'Tasa de finalización de cursos',    '%',      'menor_es_peor', 80,    72),
    ('rotacion_total',         'Tasa de rotación mensual',          '%',      'mayor_es_peor', 2.0,   3.5),
    ('rotacion_voluntaria',    'Rotación voluntaria mensual',       '%',      'mayor_es_peor', 1.5,   3.0),
    ('rotacion_involuntaria',  'Rotación involuntaria mensual',     '%',      'mayor_es_peor', 1.0,   2.0),
    ('enps',                   'eNPS',                              'puntos', 'menor_es_peor', 10,    0),
    ('indice_productividad',   'Índice de productividad',           '%',      'menor_es_peor', 68,    62)
ON CONFLICT (indicador) DO NOTHING;
