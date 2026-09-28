-- 009_rse_express.sql
-- =====================================================================
-- NEXUS RSE Express: nuevo autodiagnóstico y nuevo tamizaje
-- (Protocolo de Validación NEXUS RSE Express + RSE por Retos, v2,
--  septiembre de 2026 · Anexo 1)
-- =====================================================================
--
-- Qué hace, en este orden:
--
--  1. RESPALDA y REINICIA los datos de diagnóstico. Copia a un esquema
--     aparte (nexus360_respaldo) los tamizajes, diagnósticos, respuestas y
--     evidencias del instrumento anterior, y los borra de las tablas vivas.
--     Se CONSERVA todo lo que es de la cuenta: usuarios (nombre, correo,
--     contraseña, rol, foto, sesiones) y empresas (razón social, NIT, DV,
--     sector, municipio, departamento, extranjera) con sus vínculos.
--     Al volver a entrar, cada empresa responde el tamizaje nuevo.
--
--  2. Cambia ciclo_tamizaje a las cuatro preguntas del tamizaje nuevo
--     («Conozcamos su empresa»): T1 tamaño (sin UVT) + rango de ingresos
--     opcional, T2 personas y vinculación, T5 territorio y vecinos,
--     T6 tipo de clientes. T3 y T4 (Ley 2173) se retiran.
--
--  3. Retira del catálogo el Formato 01 (ISO 26000, 21 preguntas) y el
--     Formato 02 (Ley 2173, 26 preguntas): quedan archivados, no borrados,
--     para que el respaldo siga siendo legible. Siembra el formato
--     'rse_express': 7 materias, 21 preguntas abiertas con ejemplos
--     orientadores y una pregunta de cierre por materia.
--
--  4. La respuesta pasa a ser abierta: texto libre, ejemplos marcados,
--     «Hacemos algo diferente: ___» y la etapa («¿En qué punto está?»).
--     La etapa se guarda con la lectura interna 0–4 de la sección 6.3:
--        0 Aún no lo hemos abordado          3 Lo aplicamos y vemos resultados
--        1 Comenzando / informal             4 Lo revisamos y mejoramos
--        2 Organizado (con o sin papel)      es_na        -> No aplica
--                                            es_diferente -> Hacemos algo diferente
--     «Hacemos algo diferente» no tiene valor hasta que NEXUS lo clasifica
--     (valor_clasificado); solo un admin puede escribir esa columna.
--
--  5. Agrega el cierre por materia («¿Qué le gustaría fortalecer?»), la
--     pregunta abierta final y la matriz de priorización del diagnóstico.
--
-- Es idempotente: si el tamizaje ya tiene la estructura nueva, el paso 1
-- no hace nada (no vuelve a borrar datos nuevos) y el resto usa
-- IF NOT EXISTS / ON CONFLICT.
--
-- Aplicar UNA vez, con el rol dueño del esquema (NO nexus360_app), DESPUÉS
-- de 008 y ANTES de desplegar esta versión del backend:
--   psql "<conexión>" -f db/009_rse_express.sql
--
-- Para verificar el respaldo:
--   SELECT count(*) FROM nexus360_respaldo.respuesta_v1;
-- Para borrar el respaldo cuando ya no se necesite:
--   DROP SCHEMA nexus360_respaldo CASCADE;
-- =====================================================================

BEGIN;
SET search_path TO nexus360;

-- =====================================================================
-- 1 y 2. Respaldo, reinicio y estructura nueva del tamizaje
-- =====================================================================
DO $migracion$
DECLARE
    v_estructura_antigua BOOLEAN;
    v_ciclos INT; v_diagnosticos INT; v_respuestas INT;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'nexus360' AND table_name = 'ciclo_tamizaje'
           AND column_name = 'areas_de_vida'
    ) INTO v_estructura_antigua;

    IF NOT v_estructura_antigua THEN
        RAISE NOTICE '009: el tamizaje ya tiene la estructura RSE Express; no se respalda ni se borra nada.';
        RETURN;
    END IF;

    -- Las tablas de negocio tienen FORCE ROW LEVEL SECURITY: ni siquiera el
    -- dueño las lee sin una sesión de usuario, así que el respaldo saldría
    -- vacío. Se levanta el FORCE solo dentro de esta transacción y se
    -- vuelve a poner al final de este bloque.
    ALTER TABLE nexus360.ciclo_tamizaje NO FORCE ROW LEVEL SECURITY;
    ALTER TABLE nexus360.diagnostico    NO FORCE ROW LEVEL SECURITY;
    ALTER TABLE nexus360.respuesta      NO FORCE ROW LEVEL SECURITY;
    ALTER TABLE nexus360.evidencia      NO FORCE ROW LEVEL SECURITY;

    CREATE SCHEMA IF NOT EXISTS nexus360_respaldo;
    REVOKE ALL ON SCHEMA nexus360_respaldo FROM PUBLIC;
    COMMENT ON SCHEMA nexus360_respaldo IS
        'Respaldo del instrumento anterior (tamizaje T1-T6, Formato 01 ISO 26000 y Formato 02 Ley 2173), '
        'tomado por 009_rse_express.sql antes de reiniciar. La aplicación no lo lee. '
        'Se puede borrar con DROP SCHEMA nexus360_respaldo CASCADE.';

    CREATE TABLE nexus360_respaldo.ciclo_tamizaje_v1      AS SELECT * FROM nexus360.ciclo_tamizaje;
    CREATE TABLE nexus360_respaldo.diagnostico_v1         AS SELECT * FROM nexus360.diagnostico;
    CREATE TABLE nexus360_respaldo.respuesta_v1           AS SELECT * FROM nexus360.respuesta;
    CREATE TABLE nexus360_respaldo.evidencia_v1           AS SELECT * FROM nexus360.evidencia;
    CREATE TABLE nexus360_respaldo.peso_sector_materia_v1 AS SELECT * FROM nexus360.peso_sector_materia;

    SELECT count(*) INTO v_ciclos       FROM nexus360.ciclo_tamizaje;
    SELECT count(*) INTO v_diagnosticos FROM nexus360.diagnostico;
    SELECT count(*) INTO v_respuestas   FROM nexus360.respuesta;

    -- Reinicio: solo lo que era del instrumento anterior. usuario, sesion,
    -- usuario_foto, usuario_empresa y empresa NO se tocan.
    DELETE FROM nexus360.evidencia;
    DELETE FROM nexus360.respuesta;
    DELETE FROM nexus360.diagnostico;
    DELETE FROM nexus360.ciclo_tamizaje;

    -- Tamizaje nuevo. La tabla quedó vacía, así que las columnas NOT NULL
    -- se pueden agregar sin valor por defecto.
    ALTER TABLE nexus360.ciclo_tamizaje
        DROP COLUMN empleados,
        DROP COLUMN areas_de_vida,
        DROP COLUMN ciclo_previo,
        DROP COLUMN comunidades_etnicas,
        DROP COLUMN consumidor_final,
        DROP CONSTRAINT IF EXISTS ciclo_tamizaje_tamano_check;

    ALTER TABLE nexus360.ciclo_tamizaje
        -- T1 · ¿Cómo describiría el tamaño de su empresa?
        ADD CONSTRAINT chk_ciclo_tamano CHECK (tamano IN ('micro', 'pequena', 'mediana', 'nose')),
        -- T1 (opcional) · rango de ingresos anuales, si lo conoce
        ADD COLUMN ingresos_rango TEXT
            CHECK (ingresos_rango IS NULL OR ingresos_rango IN
                   ('menos_1000m', '1000m_10000m', '10000m_50000m', 'mas_50000m', 'no_indica')),
        -- T2 · ¿Cuántas personas trabajan hoy con la empresa y cómo están vinculadas?
        ADD COLUMN personas INTEGER NOT NULL CHECK (personas > 0),
        ADD COLUMN vinculacion TEXT[] NOT NULL DEFAULT '{}'
            CHECK (cardinality(vinculacion) >= 1
                   AND vinculacion <@ ARRAY['laboral', 'servicios', 'socios', 'temporada', 'otra']::TEXT[]),
        ADD COLUMN vinculacion_detalle TEXT CHECK (vinculacion_detalle IS NULL OR char_length(vinculacion_detalle) <= 1000),
        -- T5 · ¿En qué lugares desarrolla su actividad y qué comunidades o vecinos están cerca?
        ADD COLUMN zonas TEXT[] NOT NULL DEFAULT '{}'
            CHECK (zonas <@ ARRAY['barrios', 'veredas', 'rural', 'indigenas', 'afro', 'otras']::TEXT[]),
        ADD COLUMN territorio TEXT CHECK (territorio IS NULL OR char_length(territorio) <= 2000),
        -- T6 · ¿Quiénes son principalmente sus clientes?
        ADD COLUMN clientes TEXT NOT NULL CHECK (clientes IN ('personas', 'empresas', 'publicas', 'mezcla')),
        ADD COLUMN clientes_detalle TEXT CHECK (clientes_detalle IS NULL OR char_length(clientes_detalle) <= 1000),
        ADD COLUMN instrumento TEXT NOT NULL DEFAULT 'rse_express',
        ADD COLUMN actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
        -- T5 exige al menos una zona marcada o el texto libre.
        ADD CONSTRAINT chk_ciclo_territorio CHECK (cardinality(zonas) >= 1 OR coalesce(btrim(territorio), '') <> '');

    COMMENT ON COLUMN nexus360.ciclo_tamizaje.personas IS
        'T2: personas que trabajan hoy con la empresa, con cualquier vinculación (no solo contrato laboral).';

    ALTER TABLE nexus360.ciclo_tamizaje FORCE ROW LEVEL SECURITY;
    ALTER TABLE nexus360.diagnostico    FORCE ROW LEVEL SECURITY;
    ALTER TABLE nexus360.respuesta      FORCE ROW LEVEL SECURITY;
    ALTER TABLE nexus360.evidencia      FORCE ROW LEVEL SECURITY;

    RAISE NOTICE '009: respaldados y reiniciados % tamizajes, % diagnósticos y % respuestas. Usuarios y empresas se conservan.',
        v_ciclos, v_diagnosticos, v_respuestas;
END
$migracion$;

-- =====================================================================
-- 3. Catálogo: se retiran los formatos anteriores (archivados, no borrados)
-- =====================================================================
-- Columnas nuevas del catálogo. Van ANTES de los UPDATE: Postgres no deja
-- alterar una tabla con eventos de triggers diferidos pendientes (los de
-- suma de pesos).
ALTER TABLE nexus360.dimension ADD COLUMN IF NOT EXISTS pregunta_cierre TEXT;
ALTER TABLE nexus360.dimension DROP CONSTRAINT IF EXISTS dimension_condicional_check;
ALTER TABLE nexus360.dimension ADD CONSTRAINT dimension_condicional_check
    CHECK (condicional IS NULL OR condicional IN ('requiereAreasDeVida', 'soloConsumidorFinal'));
ALTER TABLE nexus360.pregunta
    ADD COLUMN IF NOT EXISTS ejemplos TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS proposito TEXT;

COMMENT ON COLUMN nexus360.pregunta.accion IS
    'En rse_express: la oportunidad que se propone a la matriz de priorización cuando la etapa es baja.';


UPDATE nexus360.formato
   SET activo = FALSE, archivado_en = COALESCE(archivado_en, now())
 WHERE formato_id IN ('iso26000', 'ley2173');

UPDATE nexus360.pregunta p
   SET archivado_en = now()
  FROM nexus360.seccion s
  JOIN nexus360.dimension d ON d.dimension_id = s.dimension_id
 WHERE p.seccion_id = s.seccion_id
   AND d.formato_id IN ('iso26000', 'ley2173')
   AND p.archivado_en IS NULL;

UPDATE nexus360.seccion s
   SET archivado_en = now()
  FROM nexus360.dimension d
 WHERE s.dimension_id = d.dimension_id
   AND d.formato_id IN ('iso26000', 'ley2173')
   AND s.archivado_en IS NULL;

UPDATE nexus360.dimension
   SET archivado_en = now()
 WHERE formato_id IN ('iso26000', 'ley2173')
   AND archivado_en IS NULL;

-- El trigger de pesos por sector suma TODAS las filas del sector (no mira
-- si la dimensión está archivada): las de las materias viejas se sacan
-- para que las nuevas sumen 1.0. Quedaron copiadas en el respaldo.
DELETE FROM nexus360.peso_sector_materia
 WHERE dimension_id IN (SELECT dimension_id FROM nexus360.dimension
                         WHERE formato_id IN ('iso26000', 'ley2173'));

-- =====================================================================
-- 4. Respuesta abierta
-- =====================================================================
ALTER TABLE nexus360.respuesta
    ADD COLUMN IF NOT EXISTS es_diferente      BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS texto             TEXT,
    ADD COLUMN IF NOT EXISTS ejemplos          TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS otro_texto        TEXT,
    ADD COLUMN IF NOT EXISTS valor_clasificado SMALLINT REFERENCES nexus360.nivel_escala(valor),
    ADD COLUMN IF NOT EXISTS clasificado_por   UUID REFERENCES nexus360.usuario(usuario_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS clasificado_en    TIMESTAMPTZ;

-- Antes: o hay valor, o es N/A. Ahora una respuesta puede tener texto sin
-- etapa todavía (borrador), o ser «Hacemos algo diferente» sin valor hasta
-- que NEXUS la clasifique.
ALTER TABLE nexus360.respuesta DROP CONSTRAINT IF EXISTS chk_valor_o_na;
ALTER TABLE nexus360.respuesta DROP CONSTRAINT IF EXISTS chk_etapa_respuesta;
ALTER TABLE nexus360.respuesta ADD CONSTRAINT chk_etapa_respuesta CHECK (
    NOT (es_na AND es_diferente)
    AND (NOT es_na OR valor IS NULL)
    AND (NOT es_diferente OR valor IS NULL)
    AND (valor_clasificado IS NULL OR es_diferente)
);
ALTER TABLE nexus360.respuesta DROP CONSTRAINT IF EXISTS chk_respuesta_longitudes;
ALTER TABLE nexus360.respuesta ADD CONSTRAINT chk_respuesta_longitudes CHECK (
    (texto IS NULL OR char_length(texto) <= 4000)
    AND (otro_texto IS NULL OR char_length(otro_texto) <= 1000)
    AND cardinality(ejemplos) <= 20
);

COMMENT ON COLUMN nexus360.respuesta.valor IS
    'Lectura interna 0–4 de la etapa elegida (sección 6.3). NULL si no eligió etapa, si es N/A o si es «Hacemos algo diferente».';
COMMENT ON COLUMN nexus360.respuesta.valor_clasificado IS
    'Clasificación 0–4 que NEXUS asigna a una respuesta «Hacemos algo diferente». Solo un admin la escribe.';

-- Defensa en profundidad: la clasificación la hace NEXUS, no la empresa.
-- (El rol de aplicación es uno solo para todos, así que la separación no
-- puede hacerse con GRANT por columna.)
CREATE OR REPLACE FUNCTION nexus360.proteger_clasificacion()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = nexus360, extensions, pg_temp
AS $$
BEGIN
    IF NEW.valor_clasificado IS NOT NULL
       AND (TG_OP = 'INSERT' OR NEW.valor_clasificado IS DISTINCT FROM OLD.valor_clasificado)
       AND COALESCE(nexus360.rol_usuario_actual(), '') <> 'admin' THEN
        RAISE EXCEPTION 'Solo un administrador puede clasificar respuestas';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_proteger_clasificacion ON nexus360.respuesta;
CREATE TRIGGER trg_proteger_clasificacion
    BEFORE INSERT OR UPDATE ON nexus360.respuesta
    FOR EACH ROW EXECUTE FUNCTION nexus360.proteger_clasificacion();

-- =====================================================================
-- 5. Cierre por materia, pregunta final y matriz de priorización
-- =====================================================================
ALTER TABLE nexus360.diagnostico
    ADD COLUMN IF NOT EXISTS comentario_final TEXT
        CHECK (comentario_final IS NULL OR char_length(comentario_final) <= 4000),
    ADD COLUMN IF NOT EXISTS priorizacion JSONB,
    ADD COLUMN IF NOT EXISTS actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now();

COMMENT ON COLUMN nexus360.diagnostico.comentario_final IS
    '«¿Hay algo que haga la empresa por sus trabajadores, clientes, el ambiente o la comunidad que no le hayamos preguntado?»';
COMMENT ON COLUMN nexus360.diagnostico.priorizacion IS
    'Matriz de priorización (sección 7): {filas: {codigo: {importancia, viabilidad, potencial, interes}}, elegida: codigo}. Escala 1–3.';

-- «¿Qué le gustaría fortalecer o empezar a hacer en este tema?», una por materia.
CREATE TABLE IF NOT EXISTS nexus360.respuesta_materia (
    diagnostico_id  UUID NOT NULL REFERENCES nexus360.diagnostico(diagnostico_id) ON DELETE CASCADE,
    dimension_id    UUID NOT NULL REFERENCES nexus360.dimension(dimension_id) ON DELETE RESTRICT,
    fortalecer      TEXT NOT NULL CHECK (char_length(fortalecer) BETWEEN 1 AND 2000),
    respondido_en   TIMESTAMPTZ NOT NULL DEFAULT now(),
    respondido_por  UUID REFERENCES nexus360.usuario(usuario_id) ON DELETE SET NULL,
    PRIMARY KEY (diagnostico_id, dimension_id)
);

ALTER TABLE nexus360.respuesta_materia ENABLE ROW LEVEL SECURITY;
ALTER TABLE nexus360.respuesta_materia FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS respuesta_materia_visible_pol ON nexus360.respuesta_materia;
CREATE POLICY respuesta_materia_visible_pol ON nexus360.respuesta_materia
    USING (EXISTS (
        SELECT 1 FROM nexus360.diagnostico d
         WHERE d.diagnostico_id = respuesta_materia.diagnostico_id
           AND nexus360.empresa_visible(d.empresa_id)
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM nexus360.diagnostico d
         WHERE d.diagnostico_id = respuesta_materia.diagnostico_id
           AND nexus360.empresa_visible(d.empresa_id)
    ));

GRANT SELECT, INSERT, UPDATE, DELETE ON nexus360.respuesta_materia TO nexus360_app;
GRANT SELECT ON nexus360.formato, nexus360.dimension, nexus360.seccion,
                nexus360.pregunta, nexus360.peso_sector_materia TO nexus360_app;

-- =====================================================================
-- 6. Catálogo RSE Express (generado desde el Anexo 1; mismo contenido que
--    src/data/rseExpress.ts en el frontend)
-- =====================================================================
INSERT INTO nexus360.formato (formato_id, codigo, nombre, norma, naturaleza, activo) VALUES
    ('rse_express', 'RSE Express', 'Autodiagnóstico RSE Express', 'ISO 26000 · 7 materias', 'Autodiagnóstico abierto · no es una auditoría', TRUE)
ON CONFLICT (formato_id) DO UPDATE SET codigo = EXCLUDED.codigo, nombre = EXCLUDED.nombre,
    norma = EXCLUDED.norma, naturaleza = EXCLUDED.naturaleza, activo = TRUE, archivado_en = NULL;

-- 01 · Gobernanza organizacional
INSERT INTO nexus360.dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional, pregunta_cierre) VALUES
    ('2b26d7eb-7abd-55d3-866c-a048464bb172', 'rse_express', '01', 'Gobernanza organizacional', 'Gobernanza', 'Cómo se toman las decisiones en la empresa y quién impulsa lo que hace por sus trabajadores, clientes, el ambiente y la comunidad.', NULL, NULL, '¿Qué le gustaría fortalecer o empezar a hacer en este tema?')
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO nexus360.seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('e069cd68-073c-5839-b07f-f3a3e4ffab39', '2b26d7eb-7abd-55d3-866c-a048464bb172', NULL, 1, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('fe6997af-4429-5e01-b184-1067eac81263', '01a', 'e069cd68-073c-5839-b07f-f3a3e4ffab39', 'A', 'Más allá de su actividad comercial, ¿qué hace hoy la empresa por sus trabajadores, clientes, el ambiente o la comunidad, y quién impulsa esas acciones?', 0.3, NULL, 'dejar claro qué quiere impulsar la empresa en estos temas y quién lo lidera', ARRAY['Lo decide la gerencia o el dueño', 'Acuerdos entre socios', 'Forma parte de los valores de la empresa', 'Política escrita']::TEXT[], 'Conocer si existe un compromiso de la dirección, formal o no, y quién lo sostiene.')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('0434882d-dd92-5536-9d42-067416a97f65', '01b', 'e069cd68-073c-5839-b07f-f3a3e4ffab39', 'D', '¿Quién se encarga de estas acciones y cómo consiguen el tiempo y los recursos para hacerlas?', 0.35, NULL, 'asignar un responsable y reservar tiempo y recursos para estas acciones', ARRAY['Lo asume el gerente', 'Una persona encargada', 'Se hace con recursos del momento', 'Hay un monto destinado']::TEXT[], 'Conocer quién lleva el tema y con qué recursos cuenta.')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('bdd99e10-1e69-5de0-aeca-492244f22539', '01c', 'e069cd68-073c-5839-b07f-f3a3e4ffab39', 'E', '¿Cómo le cuenta la empresa a sus trabajadores, clientes, socios o comunidad lo que hace en estos temas?', 0.35, NULL, 'contar de forma periódica lo que la empresa hace y lo que ha logrado', ARRAY['Conversaciones', 'Reuniones', 'Redes sociales', 'Carteleras', 'Informe o balance']::TEXT[], 'Conocer cómo comunica y comparte lo que hace.')
ON CONFLICT (pregunta_id) DO NOTHING;

-- 02 · Derechos humanos
INSERT INTO nexus360.dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional, pregunta_cierre) VALUES
    ('0c8dd1c4-ca8b-518b-b859-ce3f719cdcfe', 'rse_express', '02', 'Derechos humanos', 'DD. HH.', 'El trato respetuoso y digno a las personas con las que se relaciona la empresa: equipo, proveedores, clientes y vecinos.', NULL, NULL, '¿Qué le gustaría fortalecer o empezar a hacer en este tema?')
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO nexus360.seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('3ab6cae9-4566-5ed7-aa25-65e4246107f1', '0c8dd1c4-ca8b-518b-b859-ce3f719cdcfe', NULL, 1, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('76aee61d-5ed3-5d12-baf9-bed1360302bb', '02a', '3ab6cae9-4566-5ed7-aa25-65e4246107f1', 'A', '¿Cómo se asegura la empresa de que las personas con las que se relaciona (equipo, proveedores, clientes, vecinos) sean tratadas con respeto y dignidad?', 0.3, NULL, 'acordar reglas claras de respeto, no discriminación e inclusión', ARRAY['Trato respetuoso', 'No discriminación', 'No contratar menores de edad', 'Inclusión de personas', 'Reglas de convivencia']::TEXT[], 'Conocer las prácticas de respeto a las personas como base de derechos humanos.')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('46c2329d-b16b-50d1-8b5c-30451ede6c7f', '02b', '3ab6cae9-4566-5ed7-aa25-65e4246107f1', 'D', '¿Han identificado situaciones, en la empresa o con sus proveedores, que puedan afectar a las personas? ¿Qué hacen cuando las detectan?', 0.35, NULL, 'identificar a tiempo situaciones que puedan afectar a las personas, dentro de la empresa y con proveedores', ARRAY['Condiciones inseguras', 'Jornadas excesivas', 'Trabajo infantil', 'Discriminación']::TEXT[], 'Conocer cómo la empresa detecta y atiende situaciones de riesgo, dentro y fuera.')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('99a2c106-3530-5011-ad4e-f89ba7b4d84e', '02c', '3ab6cae9-4566-5ed7-aa25-65e4246107f1', 'E', 'Si una persona o un vecino se siente afectado por la empresa, ¿cómo se entera la empresa y qué hace para responder?', 0.35, NULL, 'tener un canal conocido para recibir inquietudes y responderlas a tiempo', ARRAY['Habla directamente con el dueño', 'Línea o WhatsApp', 'Buzón', 'Reunión', 'Procedimiento escrito']::TEXT[], 'Conocer los canales reales de escucha y respuesta.')
ON CONFLICT (pregunta_id) DO NOTHING;

-- 03 · Prácticas laborales
INSERT INTO nexus360.dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional, pregunta_cierre) VALUES
    ('c9b6158f-bd63-5e45-bad7-b9d987d45dec', 'rse_express', '03', 'Prácticas laborales', 'Laboral', 'Las condiciones de trabajo, el diálogo con el equipo, la seguridad y la salud, y el aprendizaje de las personas.', NULL, NULL, '¿Qué le gustaría fortalecer o empezar a hacer en este tema?')
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO nexus360.seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('2d138d89-fa12-516a-a4f4-144bed9ddb57', 'c9b6158f-bd63-5e45-bad7-b9d987d45dec', NULL, 1, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('82f87be7-8e1c-5791-a889-3cf75323554d', '03a', '2d138d89-fa12-516a-a4f4-144bed9ddb57', 'A', '¿Cómo acuerda la empresa las condiciones de trabajo con su equipo y cómo conversa con ellos sobre lo que funciona y lo que se puede mejorar?', 0.3, NULL, 'dejar claras las condiciones de trabajo y abrir espacios regulares de diálogo con el equipo', ARRAY['Contratos escritos', 'Reglamento interno', 'Reuniones periódicas', 'Conversación directa con la gerencia', 'Grupo de chat', 'Buzón', 'Comité']::TEXT[], 'Conocer la formalidad laboral y los espacios de diálogo, formales o no.')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('f480d733-fec9-5a2b-871e-0de38be5271d', '03b', '2d138d89-fa12-516a-a4f4-144bed9ddb57', 'D', '¿Qué hace la empresa para cuidar la seguridad y la salud de las personas mientras trabajan?', 0.35, NULL, 'organizar el cuidado de la seguridad y la salud de las personas en el trabajo', ARRAY['Afiliación a ARL', 'Elementos de protección', 'Capacitaciones', 'Pausas activas', 'Revisión de equipos', 'SG-SST']::TEXT[], 'Conocer prácticas de cuidado; los vacíos se presentan como oportunidad prioritaria y orientación, no como sanción.')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('855e6321-4f50-5d2a-abc1-b4bd3fba0d5f', '03c', '2d138d89-fa12-516a-a4f4-144bed9ddb57', 'E', '¿Cómo aprende y crece el equipo en la empresa y cómo se dan cuenta de que eso sirve en el trabajo diario?', 0.35, NULL, 'planear el aprendizaje del equipo y comprobar que se aplica en el trabajo', ARRAY['Aprendizaje entre compañeros', 'Inducción', 'Capacitaciones', 'Cursos SENA', 'Seguimiento del jefe']::TEXT[], 'Conocer cómo se forma el equipo y si se observa la aplicación de lo aprendido.')
ON CONFLICT (pregunta_id) DO NOTHING;

-- 04 · Medio ambiente
INSERT INTO nexus360.dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional, pregunta_cierre) VALUES
    ('7f5c709e-6186-515d-94c6-449d1ed918c0', 'rse_express', '04', 'Medio ambiente', 'Ambiental', 'El uso del agua, la energía y los materiales, el manejo de los residuos y lo que la empresa hace por cuidar el entorno.', NULL, NULL, '¿Qué le gustaría fortalecer o empezar a hacer en este tema?')
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO nexus360.seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('cc9a8bd2-b0a3-56e2-a4be-a5b884c6d039', '7f5c709e-6186-515d-94c6-449d1ed918c0', NULL, 1, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('9666c433-5b8b-5223-bdce-65f1c0930e69', '04a', 'cc9a8bd2-b0a3-56e2-a4be-a5b884c6d039', 'A', '¿Qué cuidados o acciones ambientales tiene hoy la empresa, aunque no estén escritos, y hay algo concreto que quieran lograr?', 0.3, NULL, 'fijar una o dos metas ambientales concretas y alcanzables', ARRAY['Reducir consumos', 'Manejar mejor los residuos', 'Cambiar materiales', 'Cumplir un requisito de un cliente']::TEXT[], 'Conocer las prácticas y la intención ambiental de la empresa.')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('7a8ee1fc-3157-59f8-bbbf-a615c93462b4', '04b', 'cc9a8bd2-b0a3-56e2-a4be-a5b884c6d039', 'D', 'En el día a día, ¿qué hacen para usar mejor el agua, la energía y los materiales, y qué pasa con los residuos que generan?', 0.35, NULL, 'ordenar el uso de recursos y el manejo de residuos en el día a día', ARRAY['Apagar equipos', 'Ahorro de agua', 'Reutilizar', 'Separar y reciclar', 'Entregar a gestor autorizado']::TEXT[], 'Conocer dónde ocurre el impacto ambiental real y qué se hace al respecto.')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('2bc5922a-8cf6-5f3c-b2d4-59f21ef89829', '04c', 'cc9a8bd2-b0a3-56e2-a4be-a5b884c6d039', 'E', '¿Cómo se dan cuenta si esas acciones están funcionando y han cambiado algo a partir de eso?', 0.35, NULL, 'hacer un seguimiento sencillo para saber si las acciones ambientales funcionan', ARRAY['Revisan recibos de servicios', 'Pesan o cuentan residuos', 'Observan cambios', 'Llevan un registro']::TEXT[], 'Conocer si hay seguimiento, aunque sea sencillo, y aprendizaje.')
ON CONFLICT (pregunta_id) DO NOTHING;

-- 05 · Prácticas justas de operación
INSERT INTO nexus360.dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional, pregunta_cierre) VALUES
    ('107fb1c3-e60d-5e2d-9c52-8afd43b8b03e', 'rse_express', '05', 'Prácticas justas de operación', 'Op. justas', 'La transparencia y la honestidad en las relaciones con clientes, proveedores, competidores y entidades públicas.', NULL, NULL, '¿Qué le gustaría fortalecer o empezar a hacer para que sus relaciones con clientes, proveedores, competidores y entidades sean más transparentes?')
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO nexus360.seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('e5813965-89ed-5cd1-b845-3b036acc8bd9', '107fb1c3-e60d-5e2d-9c52-8afd43b8b03e', NULL, 1, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('69a07638-cd5e-58e4-ae92-3a5181868700', '05a', 'e5813965-89ed-5cd1-b845-3b036acc8bd9', 'A', 'Cuéntenos cómo aborda actualmente la empresa la prevención de situaciones de corrupción, conflictos de interés o prácticas que puedan afectar la transparencia de sus operaciones.', 0.3, NULL, 'acordar reglas claras de transparencia para compras, pagos y relación con terceros', ARRAY['Reglas claras para compras y pagos', 'La gerencia revisa y aprueba los pagos', 'Dos personas aprueban gastos importantes', 'No se aceptan regalos o favores de proveedores', 'Se habla del tema con el equipo', 'Código de conducta o política escrita']::TEXT[], 'Conocer las prácticas de transparencia, formales o no.')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('c20bc5d5-3f1b-52ca-a2af-130321d16997', '05b', 'e5813965-89ed-5cd1-b845-3b036acc8bd9', 'D', 'Además del precio y la calidad, ¿qué tiene en cuenta la empresa al escoger a sus proveedores?', 0.35, NULL, 'tener en cuenta criterios sociales y ambientales al escoger proveedores', ARRAY['Que sean locales', 'Que estén formalizados', 'Que cuiden el ambiente', 'Que traten bien a su gente', 'Relación de confianza']::TEXT[], 'Conocer si la RSE llega a la cadena de proveedores.')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('62c99768-6d13-5fe8-81c6-afe2e321a65f', '05c', 'e5813965-89ed-5cd1-b845-3b036acc8bd9', 'E', '¿Cómo procura la empresa competir de manera honesta y tener una relación transparente con clientes, competidores y entidades públicas? ¿Hacen algo para revisar que esto se cumpla?', 0.35, NULL, 'revisar de vez en cuando que la empresa compite de forma honesta y tiene al día su relación con las entidades', ARRAY['Precios y ofertas claras', 'Trámites al día', 'Revisión de la gerencia', 'Asesoría contable o jurídica']::TEXT[], 'Conocer las prácticas de competencia justa y relación con el Estado y si existe alguna revisión.')
ON CONFLICT (pregunta_id) DO NOTHING;

-- 06 · Consumidores
INSERT INTO nexus360.dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional, pregunta_cierre) VALUES
    ('118880dc-6fb4-5bb2-abf4-6dff2bac1ae9', 'rse_express', '06', 'Consumidores', 'Consumo', 'La información clara, la calidad y la seguridad de lo que se vende, el cuidado de los datos personales y la atención a los clientes. Solo aplica si vende a consumidor final.', NULL, 'soloConsumidorFinal', '¿Qué le gustaría fortalecer o empezar a hacer en este tema?')
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO nexus360.seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('856f9d6e-9519-5ca1-adfa-987d9eb46a8b', '118880dc-6fb4-5bb2-abf4-6dff2bac1ae9', NULL, 1, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('99ba63e2-1658-5e77-985a-ae04aaf98e01', '06a', '856f9d6e-9519-5ca1-adfa-987d9eb46a8b', 'A', '¿Cómo se asegura la empresa de que sus clientes reciban información clara y productos o servicios de calidad y seguros?', 0.3, NULL, 'asegurar información clara, calidad y seguridad en lo que se ofrece a los clientes', ARRAY['Etiquetas o fichas claras', 'Garantías', 'Controles de calidad', 'Explicación directa']::TEXT[], 'Conocer las prácticas de cuidado del cliente.')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('df9f7d32-74c8-5261-b1ac-6ed5e7f3cd8e', '06b', '856f9d6e-9519-5ca1-adfa-987d9eb46a8b', 'D', '¿Qué información personal de sus clientes maneja la empresa (nombres, teléfonos, correos) y cómo la cuidan?', 0.35, NULL, 'cuidar la información personal de los clientes', ARRAY['Acceso restringido', 'Piden autorización', 'Contraseñas', 'Política de datos']::TEXT[], 'Conocer prácticas de cuidado de datos; si hay vacíos, orientar sobre la obligación legal como oportunidad.')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('4ffa8999-4559-5e99-914a-8ab21a4df56e', '06c', '856f9d6e-9519-5ca1-adfa-987d9eb46a8b', 'E', 'Cuando un cliente tiene una queja, sugerencia o reclamo, ¿cómo lo recibe la empresa y cómo le responde?', 0.35, NULL, 'recibir y responder de forma ordenada las quejas y sugerencias de los clientes', ARRAY['Atención directa', 'WhatsApp o redes', 'Correo', 'Formato o registro', 'Seguimiento de tiempos']::TEXT[], 'Conocer cómo escucha y responde a sus clientes.')
ON CONFLICT (pregunta_id) DO NOTHING;

-- 07 · Comunidad y territorio
INSERT INTO nexus360.dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional, pregunta_cierre) VALUES
    ('83e5c873-062d-5dcf-9e8b-a24e23589a8a', 'rse_express', '07', 'Comunidad y territorio', 'Comunidad', 'La relación de la empresa con el barrio, la vereda o el municipio donde opera, y los apoyos que da.', NULL, NULL, '¿Qué le gustaría fortalecer o empezar a hacer en este tema?')
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO nexus360.seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('d0bd8e20-a0b1-57af-a907-a12f84160420', '83e5c873-062d-5dcf-9e8b-a24e23589a8a', NULL, 1, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('1ab204e4-11fa-5eb6-b282-f557b826b6e6', '07a', 'd0bd8e20-a0b1-57af-a907-a12f84160420', 'A', '¿Qué relación tiene la empresa con la comunidad o el sector donde opera?', 0.3, NULL, 'construir una relación cercana y constante con la comunidad donde opera', ARRAY['Participa en actividades del barrio o municipio', 'Apoya iniciativas', 'Conversa con vecinos, líderes u organizaciones', 'Contrata personas de la zona']::TEXT[], 'Conocer el vínculo real con el territorio.')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('599eb261-b389-5b01-969a-64183beb3f25', '07b', 'd0bd8e20-a0b1-57af-a907-a12f84160420', 'D', 'Cuando la empresa apoya a la comunidad (donaciones, patrocinios, empleo local, voluntariado), ¿cómo decide a quién y en qué apoyar?', 0.35, NULL, 'definir criterios sencillos para decidir a quién y en qué apoyar', ARRAY['Donaciones', 'Patrocinios', 'Empleo local', 'Voluntariado']::TEXT[], 'Conocer cómo se toman las decisiones de apoyo y si hay criterios, aunque sean informales.')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO nexus360.pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion, ejemplos, proposito) VALUES
    ('85ab9b07-b240-5e95-9242-22b55a1f9621', '07c', 'd0bd8e20-a0b1-57af-a907-a12f84160420', 'E', '¿Qué cambios han notado en la comunidad o en la empresa a partir de esos apoyos y cómo se dan cuenta?', 0.35, NULL, 'reconocer, con evidencias sencillas, qué cambia gracias a los apoyos', ARRAY['Comentarios de la comunidad', 'Fotos o registros', 'Número de personas beneficiadas', 'Relación con vecinos']::TEXT[], 'Distinguir entre “hicimos una actividad” y “cambió algo”, con evidencias sencillas.')
ON CONFLICT (pregunta_id) DO NOTHING;

-- Pesos por sector de las materias nuevas (mismo juicio de materialidad del Formato 01).
INSERT INTO nexus360.peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('industrial', '2b26d7eb-7abd-55d3-866c-a048464bb172', 0.14),
    ('industrial', '0c8dd1c4-ca8b-518b-b859-ce3f719cdcfe', 0.12),
    ('industrial', 'c9b6158f-bd63-5e45-bad7-b9d987d45dec', 0.18),
    ('industrial', '7f5c709e-6186-515d-94c6-449d1ed918c0', 0.22),
    ('industrial', '107fb1c3-e60d-5e2d-9c52-8afd43b8b03e', 0.14),
    ('industrial', '118880dc-6fb4-5bb2-abf4-6dff2bac1ae9', 0.08),
    ('industrial', '83e5c873-062d-5dcf-9e8b-a24e23589a8a', 0.12)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO nexus360.peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('servicios', '2b26d7eb-7abd-55d3-866c-a048464bb172', 0.16),
    ('servicios', '0c8dd1c4-ca8b-518b-b859-ce3f719cdcfe', 0.12),
    ('servicios', 'c9b6158f-bd63-5e45-bad7-b9d987d45dec', 0.2),
    ('servicios', '7f5c709e-6186-515d-94c6-449d1ed918c0', 0.1),
    ('servicios', '107fb1c3-e60d-5e2d-9c52-8afd43b8b03e', 0.16),
    ('servicios', '118880dc-6fb4-5bb2-abf4-6dff2bac1ae9', 0.16),
    ('servicios', '83e5c873-062d-5dcf-9e8b-a24e23589a8a', 0.1)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO nexus360.peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('agroindustrial', '2b26d7eb-7abd-55d3-866c-a048464bb172', 0.12),
    ('agroindustrial', '0c8dd1c4-ca8b-518b-b859-ce3f719cdcfe', 0.14),
    ('agroindustrial', 'c9b6158f-bd63-5e45-bad7-b9d987d45dec', 0.16),
    ('agroindustrial', '7f5c709e-6186-515d-94c6-449d1ed918c0', 0.22),
    ('agroindustrial', '107fb1c3-e60d-5e2d-9c52-8afd43b8b03e', 0.1),
    ('agroindustrial', '118880dc-6fb4-5bb2-abf4-6dff2bac1ae9', 0.08),
    ('agroindustrial', '83e5c873-062d-5dcf-9e8b-a24e23589a8a', 0.18)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO nexus360.peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('comercio', '2b26d7eb-7abd-55d3-866c-a048464bb172', 0.14),
    ('comercio', '0c8dd1c4-ca8b-518b-b859-ce3f719cdcfe', 0.1),
    ('comercio', 'c9b6158f-bd63-5e45-bad7-b9d987d45dec', 0.16),
    ('comercio', '7f5c709e-6186-515d-94c6-449d1ed918c0', 0.12),
    ('comercio', '107fb1c3-e60d-5e2d-9c52-8afd43b8b03e', 0.16),
    ('comercio', '118880dc-6fb4-5bb2-abf4-6dff2bac1ae9', 0.22),
    ('comercio', '83e5c873-062d-5dcf-9e8b-a24e23589a8a', 0.1)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO nexus360.peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('energia', '2b26d7eb-7abd-55d3-866c-a048464bb172', 0.14),
    ('energia', '0c8dd1c4-ca8b-518b-b859-ce3f719cdcfe', 0.14),
    ('energia', 'c9b6158f-bd63-5e45-bad7-b9d987d45dec', 0.16),
    ('energia', '7f5c709e-6186-515d-94c6-449d1ed918c0', 0.22),
    ('energia', '107fb1c3-e60d-5e2d-9c52-8afd43b8b03e', 0.12),
    ('energia', '118880dc-6fb4-5bb2-abf4-6dff2bac1ae9', 0.06),
    ('energia', '83e5c873-062d-5dcf-9e8b-a24e23589a8a', 0.16)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO nexus360.peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('movilidad', '2b26d7eb-7abd-55d3-866c-a048464bb172', 0.14),
    ('movilidad', '0c8dd1c4-ca8b-518b-b859-ce3f719cdcfe', 0.12),
    ('movilidad', 'c9b6158f-bd63-5e45-bad7-b9d987d45dec', 0.18),
    ('movilidad', '7f5c709e-6186-515d-94c6-449d1ed918c0', 0.18),
    ('movilidad', '107fb1c3-e60d-5e2d-9c52-8afd43b8b03e', 0.12),
    ('movilidad', '118880dc-6fb4-5bb2-abf4-6dff2bac1ae9', 0.16),
    ('movilidad', '83e5c873-062d-5dcf-9e8b-a24e23589a8a', 0.1)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;

COMMIT;
