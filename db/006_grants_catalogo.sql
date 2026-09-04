-- 006_grants_catalogo.sql
-- Las tablas del catálogo normativo (sector, arquetipo, nivel_escala, ancla,
-- formato, dimension, seccion, pregunta, peso_sector_materia) son datos de
-- referencia globales, sin RLS (no son por-empresa) — pero nunca se les dio
-- GRANT SELECT a nexus360_app en 001_schema.sql, porque hasta ahora nada
-- las consultaba. El endpoint de guardar respuestas de diagnóstico necesita
-- leer `pregunta` (para resolver pregunta_id a partir del código) y, en el
-- futuro, un catálogo editable necesitaría lo mismo sobre el resto.
--
-- Aplicar UNA vez, con el rol dueño del esquema:
--   psql "<conexión>" -f db/006_grants_catalogo.sql

BEGIN;
SET search_path TO nexus360;

GRANT SELECT ON sector, arquetipo, nivel_escala, ancla,
                 formato, dimension, seccion, pregunta, peso_sector_materia
    TO nexus360_app;

COMMIT;
