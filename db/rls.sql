-- ============================================================
-- Row Level Security (RLS) en TODAS las tablas del esquema public
--
-- Por que: Supabase publica automaticamente cada tabla de "public" en
-- su Data API, accesible con la llave publica (anon/publishable). Una
-- tabla sin RLS queda legible y modificable por cualquiera en internet.
-- Con RLS activo y sin politicas, esa API no puede leer ni escribir nada.
--
-- El backend NO se ve afectado: se conecta como dueno de las tablas, y
-- el dueno no esta sujeto a RLS (no se usa FORCE ROW LEVEL SECURITY).
-- En PostgreSQL local (Docker) no cambia nada.
--
-- Recorre las tablas existentes, asi cubre tambien las que se agreguen
-- despues. Es seguro ejecutarlo varias veces: la API lo ejecuta al
-- arrancar y scripts/seed.py al terminar de cargar los datos.
-- ============================================================

DO $$
DECLARE
    t record;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
    END LOOP;
END $$;
