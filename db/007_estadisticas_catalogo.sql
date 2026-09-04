-- 007_estadisticas_catalogo.sql
-- Permisos de lectura sobre el catálogo normativo, para el panel de
-- estadísticas.
--
-- 001_schema.sql nunca le dio SELECT a nexus360_app sobre sector,
-- dimension, seccion ni pregunta (solo sobre usuario, usuario_empresa,
-- y las tablas de negocio: empresa, ciclo_tamizaje, diagnostico,
-- respuesta, evidencia). 006 ya corrigió el mismo olvido para `formato`.
-- Estas cuatro faltaban porque hasta ahora nada las consultaba desde el
-- backend: el catálogo normativo (ISO 26000 / Ley 2173) vive hoy en el
-- frontend (src/data/*.ts), no en la base.
--
-- Son tablas de referencia sin RLS y sin datos de ninguna persona
-- (preguntas, secciones, dimensiones, sectores): darles SELECT no
-- expone nada que no sea ya público en el propio frontend.
--
-- Aplicar UNA vez, con el rol dueño del esquema (NO nexus360_app):
--   psql "<conexión>" -f db/007_estadisticas_catalogo.sql

BEGIN;
SET search_path TO nexus360;

GRANT SELECT ON nexus360.sector    TO nexus360_app;
GRANT SELECT ON nexus360.dimension TO nexus360_app;
GRANT SELECT ON nexus360.seccion   TO nexus360_app;
GRANT SELECT ON nexus360.pregunta  TO nexus360_app;

COMMIT;
