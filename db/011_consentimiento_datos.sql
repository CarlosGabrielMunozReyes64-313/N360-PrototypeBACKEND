-- 011_consentimiento_datos.sql
-- =====================================================================
-- Autorización para el tratamiento de datos personales (Ley 1581 de 2012)
-- =====================================================================
--
-- La Ley 1581 exige una autorización previa, expresa e informada del
-- titular, y el Decreto 1377 de 2013 (compilado en el Decreto 1074 de 2015)
-- obliga al responsable a conservar prueba de ella. Esta tabla guarda esa
-- prueba: quién aceptó, qué versión de la Política de Tratamiento de Datos
-- Personales, cuándo, desde qué IP y con qué navegador.
--
-- El backend la escribe en la MISMA transacción que crea la cuenta
-- (POST /api/auth/register): si no se puede guardar la autorización, la
-- cuenta tampoco se crea.
--
-- Es evidencia: el rol de aplicación puede insertar y leer, pero no
-- modificar ni borrar. Si una cuenta se borra físicamente (admin, cuenta
-- sin datos), su autorización se borra con ella.
--
-- Es idempotente. Aplicar con el rol dueño del esquema (NO nexus360_app):
--   psql "<conexión>" -f db/011_consentimiento_datos.sql
-- =====================================================================

BEGIN;
SET search_path TO nexus360;

CREATE TABLE IF NOT EXISTS nexus360.consentimiento_datos (
    consentimiento_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id        UUID NOT NULL REFERENCES nexus360.usuario(usuario_id) ON DELETE CASCADE,
    politica_version  TEXT NOT NULL CHECK (char_length(politica_version) BETWEEN 1 AND 40),
    aceptado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip_origen         INET,
    user_agent        TEXT CHECK (user_agent IS NULL OR char_length(user_agent) <= 500),
    CONSTRAINT uq_consentimiento_version UNIQUE (usuario_id, politica_version)
);

COMMENT ON TABLE nexus360.consentimiento_datos IS
    'Prueba de la autorización de tratamiento de datos personales (Ley 1581 de 2012) por versión de la política.';

CREATE INDEX IF NOT EXISTS idx_consentimiento_usuario ON nexus360.consentimiento_datos (usuario_id);

ALTER TABLE nexus360.consentimiento_datos ENABLE ROW LEVEL SECURITY;
ALTER TABLE nexus360.consentimiento_datos FORCE ROW LEVEL SECURITY;

-- Cada quien ve su propia autorización; el admin, todas.
DROP POLICY IF EXISTS consentimiento_select_pol ON nexus360.consentimiento_datos;
CREATE POLICY consentimiento_select_pol ON nexus360.consentimiento_datos
    FOR SELECT
    USING (
        usuario_id = nexus360.current_usuario_id()
        OR nexus360.rol_usuario_actual() = 'admin'
    );

-- Solo se puede registrar la autorización propia.
DROP POLICY IF EXISTS consentimiento_insert_pol ON nexus360.consentimiento_datos;
CREATE POLICY consentimiento_insert_pol ON nexus360.consentimiento_datos
    FOR INSERT
    WITH CHECK (usuario_id = nexus360.current_usuario_id());

GRANT SELECT, INSERT ON nexus360.consentimiento_datos TO nexus360_app;

COMMIT;
