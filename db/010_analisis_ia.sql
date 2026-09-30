-- 010_analisis_ia.sql
-- =====================================================================
-- Análisis inteligente del autodiagnóstico (Gemini)
-- =====================================================================
--
-- Guarda la interpretación que Gemini hace de los resultados del
-- autodiagnóstico RSE Express: un análisis vigente por diagnóstico.
--
--   contenido       JSON validado en el backend (app/ia/schemas.py::AnalisisIA):
--                   resumen, fortalezas, areas_oportunidad, prioridades,
--                   recomendaciones, acciones_corto_plazo,
--                   acciones_mediano_plazo y conclusion. Sin puntajes.
--   huella          SHA-256 de lo que se le envió a Gemini + versión del
--                   prompt. Si los resultados no cambian, el análisis se
--                   reutiliza y no se vuelve a llamar a Gemini.
--   modelo          modelo de Gemini que lo generó.
--   version_prompt  versión del prompt (app/ia/prompts.py::VERSION_PROMPT).
--
-- Los puntajes, niveles y prioridades NO viven aquí: siguen siendo los que
-- calcula el motor del diagnóstico. Esta tabla solo guarda la interpretación.
--
-- Es idempotente. Aplicar con el rol dueño del esquema (NO nexus360_app),
-- DESPUÉS de 009:
--   psql "<conexión>" -f db/010_analisis_ia.sql
--
-- Sin esta migración la aplicación sigue funcionando; solo el análisis
-- inteligente responde «no disponible» (y el log dice qué aplicar).
-- =====================================================================

BEGIN;
SET search_path TO nexus360;

CREATE TABLE IF NOT EXISTS nexus360.diagnostico_analisis_ia (
    diagnostico_id  UUID PRIMARY KEY
                        REFERENCES nexus360.diagnostico(diagnostico_id) ON DELETE CASCADE,
    contenido       JSONB NOT NULL CHECK (jsonb_typeof(contenido) = 'object'),
    huella          CHAR(64) NOT NULL,
    modelo          TEXT NOT NULL CHECK (char_length(modelo) BETWEEN 1 AND 100),
    version_prompt  TEXT NOT NULL CHECK (char_length(version_prompt) BETWEEN 1 AND 50),
    generado_en     TIMESTAMPTZ NOT NULL DEFAULT now(),
    generado_por    UUID REFERENCES nexus360.usuario(usuario_id) ON DELETE SET NULL
);

COMMENT ON TABLE nexus360.diagnostico_analisis_ia IS
    'Interpretación con IA (Gemini) de los resultados del autodiagnóstico. No contiene puntajes: esos los calcula el motor.';
COMMENT ON COLUMN nexus360.diagnostico_analisis_ia.huella IS
    'SHA-256 del contexto enviado a Gemini + versión del prompt; si coincide, el análisis se reutiliza.';

-- Mismo criterio que respuesta_materia: la ve y la escribe quien puede ver
-- la empresa del diagnóstico (su propia cuenta o un admin).
ALTER TABLE nexus360.diagnostico_analisis_ia ENABLE ROW LEVEL SECURITY;
ALTER TABLE nexus360.diagnostico_analisis_ia FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS diagnostico_analisis_ia_visible_pol ON nexus360.diagnostico_analisis_ia;
CREATE POLICY diagnostico_analisis_ia_visible_pol ON nexus360.diagnostico_analisis_ia
    USING (EXISTS (
        SELECT 1 FROM nexus360.diagnostico d
         WHERE d.diagnostico_id = diagnostico_analisis_ia.diagnostico_id
           AND nexus360.empresa_visible(d.empresa_id)
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM nexus360.diagnostico d
         WHERE d.diagnostico_id = diagnostico_analisis_ia.diagnostico_id
           AND nexus360.empresa_visible(d.empresa_id)
    ));

GRANT SELECT, INSERT, UPDATE, DELETE ON nexus360.diagnostico_analisis_ia TO nexus360_app;

COMMIT;
