-- db/demo/borrar_demo.sql
-- Quita las empresas de demostración (razón social «DEMO · …») y todo lo
-- suyo: tamizaje, autodiagnóstico, respuestas y vínculos. No toca nada más.
--   psql "<conexión>" -f db/demo/borrar_demo.sql
BEGIN;
ALTER TABLE nexus360.empresa           NO FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.ciclo_tamizaje    NO FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.diagnostico       NO FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.respuesta         NO FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.respuesta_materia NO FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.evidencia         NO FORCE ROW LEVEL SECURITY;

CREATE TEMP TABLE demo_empresas ON COMMIT DROP AS
    SELECT empresa_id FROM nexus360.empresa WHERE razon_social LIKE 'DEMO · %';
DELETE FROM nexus360.respuesta_materia WHERE diagnostico_id IN (SELECT diagnostico_id FROM nexus360.diagnostico WHERE empresa_id IN (SELECT empresa_id FROM demo_empresas));
DELETE FROM nexus360.evidencia WHERE respuesta_id IN (SELECT r.respuesta_id FROM nexus360.respuesta r JOIN nexus360.diagnostico d ON d.diagnostico_id = r.diagnostico_id WHERE d.empresa_id IN (SELECT empresa_id FROM demo_empresas));
DELETE FROM nexus360.respuesta WHERE diagnostico_id IN (SELECT diagnostico_id FROM nexus360.diagnostico WHERE empresa_id IN (SELECT empresa_id FROM demo_empresas));
DELETE FROM nexus360.diagnostico WHERE empresa_id IN (SELECT empresa_id FROM demo_empresas);
DELETE FROM nexus360.ciclo_tamizaje WHERE empresa_id IN (SELECT empresa_id FROM demo_empresas);
DELETE FROM nexus360.usuario_empresa WHERE empresa_id IN (SELECT empresa_id FROM demo_empresas);
DELETE FROM nexus360.empresa WHERE empresa_id IN (SELECT empresa_id FROM demo_empresas);

ALTER TABLE nexus360.empresa           FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.ciclo_tamizaje    FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.diagnostico       FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.respuesta         FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.respuesta_materia FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.evidencia         FORCE ROW LEVEL SECURITY;
COMMIT;
