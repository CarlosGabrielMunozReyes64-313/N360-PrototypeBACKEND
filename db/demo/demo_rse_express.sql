-- db/demo/demo_rse_express.sql
-- =====================================================================
-- DATOS DE DEMOSTRACIÓN del Autodiagnóstico RSE Express (OPCIONAL)
-- =====================================================================
-- Crea 12 empresas ficticias cuyo nombre empieza por «DEMO · », con su
-- tamizaje y su autodiagnóstico (respuestas abiertas, etapas, prácticas
-- propias, «qué le gustaría fortalecer» y matriz de priorización), para
-- ver el panel de estadísticas y las gráficas antes de que respondan las
-- empresas reales. NO toca usuarios ni empresas reales.
--
-- Requiere haber aplicado db/009_rse_express.sql. Correr con el rol dueño
-- del esquema:
--   psql "<conexión>" -f db/demo/demo_rse_express.sql
-- Se puede correr varias veces: primero borra la demo anterior.
-- Para quitarla:
--   psql "<conexión>" -f db/demo/borrar_demo.sql
-- =====================================================================
BEGIN;
SET search_path TO nexus360;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'nexus360' AND table_name = 'ciclo_tamizaje'
                      AND column_name = 'clientes') THEN
        RAISE EXCEPTION 'Primero aplique db/009_rse_express.sql: la base todavía tiene el tamizaje anterior.';
    END IF;
END $$;

-- Mismo tratamiento que 009: el FORCE RLS se levanta solo dentro de esta
-- transacción (la escribe el dueño del esquema, sin sesión de usuario) y
-- se vuelve a poner al final.
ALTER TABLE nexus360.empresa           NO FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.ciclo_tamizaje    NO FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.diagnostico       NO FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.respuesta         NO FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.respuesta_materia NO FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.evidencia         NO FORCE ROW LEVEL SECURITY;
-- Las clasificaciones de NEXUS de la demo se escriben sin sesión de admin.
ALTER TABLE nexus360.respuesta DISABLE TRIGGER trg_proteger_clasificacion;

-- Demo anterior, si existe.
CREATE TEMP TABLE demo_empresas ON COMMIT DROP AS
    SELECT empresa_id FROM nexus360.empresa WHERE razon_social LIKE 'DEMO · %';
DELETE FROM nexus360.respuesta_materia WHERE diagnostico_id IN (SELECT diagnostico_id FROM nexus360.diagnostico WHERE empresa_id IN (SELECT empresa_id FROM demo_empresas));
DELETE FROM nexus360.evidencia WHERE respuesta_id IN (SELECT r.respuesta_id FROM nexus360.respuesta r JOIN nexus360.diagnostico d ON d.diagnostico_id = r.diagnostico_id WHERE d.empresa_id IN (SELECT empresa_id FROM demo_empresas));
DELETE FROM nexus360.respuesta WHERE diagnostico_id IN (SELECT diagnostico_id FROM nexus360.diagnostico WHERE empresa_id IN (SELECT empresa_id FROM demo_empresas));
DELETE FROM nexus360.diagnostico WHERE empresa_id IN (SELECT empresa_id FROM demo_empresas);
DELETE FROM nexus360.ciclo_tamizaje WHERE empresa_id IN (SELECT empresa_id FROM demo_empresas);
DELETE FROM nexus360.usuario_empresa WHERE empresa_id IN (SELECT empresa_id FROM demo_empresas);
DELETE FROM nexus360.empresa WHERE empresa_id IN (SELECT empresa_id FROM demo_empresas);

-- Preguntas vigentes del RSE Express, por código.
CREATE TEMP TABLE demo_preguntas ON COMMIT DROP AS
    SELECT p.codigo, p.pregunta_id, d.dimension_id, d.numero
      FROM nexus360.pregunta p
      JOIN nexus360.seccion s   ON s.seccion_id = p.seccion_id
      JOIN nexus360.dimension d ON d.dimension_id = s.dimension_id
     WHERE d.formato_id = 'rse_express' AND p.archivado_en IS NULL;


-- 1. Panificadora La Espiga
INSERT INTO nexus360.empresa (empresa_id, razon_social, nit, dv, sector_id, municipio, departamento, extranjera, creado_en)
VALUES ('df79e808-ea5d-5952-aba0-4c98e41e661d', 'DEMO · Panificadora La Espiga', '901900100', nexus360.calcular_dv('901900100'), 'comercio', 'Pasto', 'Nariño', FALSE, now() - interval '75 days');
INSERT INTO nexus360.ciclo_tamizaje (ciclo_id, empresa_id, anio, tamano, ingresos_rango, personas, vinculacion, vinculacion_detalle, zonas, territorio, clientes, clientes_detalle, creado_en, actualizado_en)
VALUES ('501b9a65-e782-58b5-b0bc-df2e04b4d8cd', 'df79e808-ea5d-5952-aba0-4c98e41e661d', 2026, 'pequena', 'menos_1000m', 18, ARRAY['laboral', 'socios']::TEXT[], NULL, ARRAY['barrios']::TEXT[], 'Barrio Obrero, cerca de un colegio', 'personas', NULL, now() - interval '75 days', now() - interval '75 days');
INSERT INTO nexus360.diagnostico (diagnostico_id, empresa_id, ciclo_id, formato_id, estado, creado_en, completado_en, comentario_final, priorizacion, actualizado_en)
VALUES ('116cbf3b-8875-5103-bbb2-fb096e290bd7', 'df79e808-ea5d-5952-aba0-4c98e41e661d', '501b9a65-e782-58b5-b0bc-df2e04b4d8cd', 'rse_express', 'completado', now() - interval '75 days', now() - interval '70 days', 'Apoyamos cada año la fiesta patronal del municipio.', '{"filas": {"03b": {"importancia": 3, "viabilidad": 1, "potencial": 3, "interes": 1}, "07c": {"importancia": 2, "viabilidad": 1, "potencial": 3, "interes": 3}, "01a": {"importancia": 2, "viabilidad": 3, "potencial": 2, "interes": 1}, "02b": {"importancia": 2, "viabilidad": 3, "potencial": 2, "interes": 3}}, "elegida": "02b"}'::jsonb, now() - interval '70 days');
INSERT INTO nexus360.respuesta (diagnostico_id, pregunta_id, valor, es_na, es_diferente, texto, ejemplos, otro_texto, valor_clasificado, clasificado_en, respondido_en)
SELECT '116cbf3b-8875-5103-bbb2-fb096e290bd7', dp.pregunta_id, v.valor::smallint, v.es_na, v.es_diferente, v.texto, v.ejemplos, v.otro, v.clasif::smallint,
       CASE WHEN v.clasif IS NULL THEN NULL ELSE now() - interval '68 days' END, now() - interval '70 days'
  FROM (VALUES
    ('01a', 1, FALSE, FALSE, 'Lo hacemos cuando se presenta la necesidad, sin un orden fijo.', ARRAY[]::TEXT[], NULL, NULL),
    ('01b', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Hay un monto destinado', 'Se hace con recursos del momento', 'Una persona encargada']::TEXT[], NULL, NULL),
    ('01c', NULL, FALSE, TRUE, 'Lo hacemos a nuestra manera, con apoyo de otros.', ARRAY['Conversaciones']::TEXT[], 'Hacemos una jornada anual con las familias del equipo.', NULL),
    ('02a', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY['Inclusión de personas']::TEXT[], NULL, NULL),
    ('02b', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY['Discriminación']::TEXT[], NULL, NULL),
    ('02c', NULL, FALSE, TRUE, 'Lo hacemos a nuestra manera, con apoyo de otros.', ARRAY['Buzón']::TEXT[], 'Hacemos una jornada anual con las familias del equipo.', NULL),
    ('03a', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY['Contratos escritos', 'Buzón']::TEXT[], NULL, NULL),
    ('03b', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY['Revisión de equipos']::TEXT[], NULL, NULL),
    ('03c', NULL, FALSE, TRUE, 'Lo hacemos a nuestra manera, con apoyo de otros.', ARRAY['Cursos SENA']::TEXT[], 'Compostamos los residuos con una huerta vecina.', 2),
    ('04a', 3, FALSE, FALSE, 'Funciona bien: el equipo lo reconoce y hay resultados.', ARRAY[]::TEXT[], NULL, NULL),
    ('04b', NULL, FALSE, TRUE, 'Lo hacemos a nuestra manera, con apoyo de otros.', ARRAY[]::TEXT[], 'Tenemos un acuerdo con la junta de acción comunal.', 3),
    ('04c', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Llevan un registro']::TEXT[], NULL, NULL),
    ('05a', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY['Código de conducta o política escrita']::TEXT[], NULL, NULL),
    ('05b', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY['Relación de confianza']::TEXT[], NULL, NULL),
    ('05c', 1, FALSE, FALSE, 'Lo hacemos cuando se presenta la necesidad, sin un orden fijo.', ARRAY['Asesoría contable o jurídica']::TEXT[], NULL, NULL),
    ('06a', NULL, TRUE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('06b', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY['Política de datos', 'Piden autorización', 'Acceso restringido']::TEXT[], NULL, NULL),
    ('06c', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY['Formato o registro', 'Atención directa', 'WhatsApp o redes']::TEXT[], NULL, NULL),
    ('07a', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY['Contrata personas de la zona', 'Participa en actividades del barrio o municipio']::TEXT[], NULL, NULL),
    ('07b', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY[]::TEXT[], NULL, NULL),
    ('07c', 0, FALSE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL)
  ) AS v(codigo, valor, es_na, es_diferente, texto, ejemplos, otro, clasif)
  JOIN demo_preguntas dp ON dp.codigo = v.codigo;
INSERT INTO nexus360.respuesta_materia (diagnostico_id, dimension_id, fortalecer, respondido_en)
SELECT DISTINCT '116cbf3b-8875-5103-bbb2-fb096e290bd7'::uuid, dp.dimension_id, v.texto, now() - interval '70 days'
  FROM (VALUES
    ('02', 'Nos gustaría tener un canal para que los vecinos nos cuenten sus inquietudes.'),
    ('05', 'Queremos reglas claras para compras y pagos.'),
    ('06', 'Queremos atender mejor las quejas de los clientes.'),
    ('07', 'Nos gustaría apoyar a la comunidad de forma más ordenada.')
  ) AS v(numero, texto)
  JOIN demo_preguntas dp ON dp.numero = v.numero;

-- 2. Lácteos del Guáitara
INSERT INTO nexus360.empresa (empresa_id, razon_social, nit, dv, sector_id, municipio, departamento, extranjera, creado_en)
VALUES ('a48269ea-4ba2-54d5-ba2e-0a5d845349c8', 'DEMO · Lácteos del Guáitara', '901900107', nexus360.calcular_dv('901900107'), 'agroindustrial', 'Ipiales', 'Nariño', FALSE, now() - interval '69 days');
INSERT INTO nexus360.ciclo_tamizaje (ciclo_id, empresa_id, anio, tamano, ingresos_rango, personas, vinculacion, vinculacion_detalle, zonas, territorio, clientes, clientes_detalle, creado_en, actualizado_en)
VALUES ('90fbf4d6-fdb0-5b0c-8a15-77e795e47990', 'a48269ea-4ba2-54d5-ba2e-0a5d845349c8', 2026, 'pequena', '1000m_10000m', 34, ARRAY['laboral', 'temporada']::TEXT[], NULL, ARRAY['veredas', 'rural', 'indigenas']::TEXT[], 'Veredas del resguardo, proveedores de leche', 'mezcla', NULL, now() - interval '69 days', now() - interval '69 days');
INSERT INTO nexus360.diagnostico (diagnostico_id, empresa_id, ciclo_id, formato_id, estado, creado_en, completado_en, comentario_final, priorizacion, actualizado_en)
VALUES ('aa9cda9f-ac6d-5520-b9d6-b26b36cdacf9', 'a48269ea-4ba2-54d5-ba2e-0a5d845349c8', '90fbf4d6-fdb0-5b0c-8a15-77e795e47990', 'rse_express', 'completado', now() - interval '69 days', now() - interval '64 days', NULL, '{"filas": {"02a": {"importancia": 2, "viabilidad": 1, "potencial": 3, "interes": 1}, "05a": {"importancia": 3, "viabilidad": 1, "potencial": 2, "interes": 3}, "01b": {"importancia": 2, "viabilidad": 2, "potencial": 2, "interes": 3}, "03b": {"importancia": 2, "viabilidad": 3, "potencial": 3, "interes": 3}}, "elegida": "03b"}'::jsonb, now() - interval '64 days');
INSERT INTO nexus360.respuesta (diagnostico_id, pregunta_id, valor, es_na, es_diferente, texto, ejemplos, otro_texto, valor_clasificado, clasificado_en, respondido_en)
SELECT 'aa9cda9f-ac6d-5520-b9d6-b26b36cdacf9', dp.pregunta_id, v.valor::smallint, v.es_na, v.es_diferente, v.texto, v.ejemplos, v.otro, v.clasif::smallint,
       CASE WHEN v.clasif IS NULL THEN NULL ELSE now() - interval '62 days' END, now() - interval '64 days'
  FROM (VALUES
    ('01a', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY['Acuerdos entre socios', 'Lo decide la gerencia o el dueño']::TEXT[], NULL, NULL),
    ('01b', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY['Una persona encargada', 'Se hace con recursos del momento', 'Lo asume el gerente']::TEXT[], NULL, NULL),
    ('01c', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Conversaciones', 'Carteleras']::TEXT[], NULL, NULL),
    ('02a', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY['Reglas de convivencia']::TEXT[], NULL, NULL),
    ('02b', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY[]::TEXT[], NULL, NULL),
    ('02c', NULL, FALSE, TRUE, 'Lo hacemos a nuestra manera, con apoyo de otros.', ARRAY['Buzón']::TEXT[], 'Tenemos un acuerdo con la junta de acción comunal.', NULL),
    ('03a', NULL, TRUE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('03b', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY['Capacitaciones', 'Afiliación a ARL', 'Pausas activas']::TEXT[], NULL, NULL),
    ('03c', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Seguimiento del jefe']::TEXT[], NULL, NULL),
    ('04a', 3, FALSE, FALSE, 'Funciona bien: el equipo lo reconoce y hay resultados.', ARRAY['Reducir consumos']::TEXT[], NULL, NULL),
    ('04b', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Apagar equipos']::TEXT[], NULL, NULL),
    ('04c', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Pesan o cuentan residuos', 'Llevan un registro', 'Revisan recibos de servicios']::TEXT[], NULL, NULL),
    ('05a', 1, FALSE, FALSE, 'Lo hacemos cuando se presenta la necesidad, sin un orden fijo.', ARRAY[]::TEXT[], NULL, NULL),
    ('05b', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Que traten bien a su gente', 'Relación de confianza']::TEXT[], NULL, NULL),
    ('05c', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY[]::TEXT[], NULL, NULL),
    ('06a', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY['Explicación directa', 'Etiquetas o fichas claras']::TEXT[], NULL, NULL),
    ('06b', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Acceso restringido', 'Política de datos']::TEXT[], NULL, NULL),
    ('06c', NULL, FALSE, TRUE, 'Lo hacemos a nuestra manera, con apoyo de otros.', ARRAY['Formato o registro']::TEXT[], 'Compostamos los residuos con una huerta vecina.', 3),
    ('07a', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY['Participa en actividades del barrio o municipio']::TEXT[], NULL, NULL),
    ('07b', 3, FALSE, FALSE, 'Funciona bien: el equipo lo reconoce y hay resultados.', ARRAY['Donaciones']::TEXT[], NULL, NULL),
    ('07c', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Número de personas beneficiadas']::TEXT[], NULL, NULL)
  ) AS v(codigo, valor, es_na, es_diferente, texto, ejemplos, otro, clasif)
  JOIN demo_preguntas dp ON dp.codigo = v.codigo;
INSERT INTO nexus360.respuesta_materia (diagnostico_id, dimension_id, fortalecer, respondido_en)
SELECT DISTINCT 'aa9cda9f-ac6d-5520-b9d6-b26b36cdacf9'::uuid, dp.dimension_id, v.texto, now() - interval '64 days'
  FROM (VALUES
    ('01', 'Queremos dejar por escrito lo que hacemos y quién lo lidera.'),
    ('03', 'Queremos organizar mejor la seguridad y salud en el trabajo.'),
    ('05', 'Queremos reglas claras para compras y pagos.'),
    ('06', 'Queremos atender mejor las quejas de los clientes.'),
    ('07', 'Nos gustaría apoyar a la comunidad de forma más ordenada.')
  ) AS v(numero, texto)
  JOIN demo_preguntas dp ON dp.numero = v.numero;

-- 3. Transportes Galeras
INSERT INTO nexus360.empresa (empresa_id, razon_social, nit, dv, sector_id, municipio, departamento, extranjera, creado_en)
VALUES ('b8cf0c7c-bd47-561a-bb65-2d2bfe3db912', 'DEMO · Transportes Galeras', '901900114', nexus360.calcular_dv('901900114'), 'movilidad', 'Pasto', 'Nariño', FALSE, now() - interval '63 days');
INSERT INTO nexus360.ciclo_tamizaje (ciclo_id, empresa_id, anio, tamano, ingresos_rango, personas, vinculacion, vinculacion_detalle, zonas, territorio, clientes, clientes_detalle, creado_en, actualizado_en)
VALUES ('8569ec84-d037-50ae-b9d3-b05ce993df69', 'b8cf0c7c-bd47-561a-bb65-2d2bfe3db912', 2026, 'mediana', '10000m_50000m', 85, ARRAY['laboral', 'servicios']::TEXT[], NULL, ARRAY['barrios']::TEXT[], 'Terminal y rutas urbanas', 'personas', NULL, now() - interval '63 days', now() - interval '63 days');
INSERT INTO nexus360.diagnostico (diagnostico_id, empresa_id, ciclo_id, formato_id, estado, creado_en, completado_en, comentario_final, priorizacion, actualizado_en)
VALUES ('36233ea8-1169-5657-8b84-e81cb223bedb', 'b8cf0c7c-bd47-561a-bb65-2d2bfe3db912', '8569ec84-d037-50ae-b9d3-b05ce993df69', 'rse_express', 'completado', now() - interval '63 days', now() - interval '58 days', NULL, '{"filas": {"03b": {"importancia": 2, "viabilidad": 1, "potencial": 3, "interes": 1}, "02c": {"importancia": 3, "viabilidad": 1, "potencial": 3, "interes": 3}, "04c": {"importancia": 3, "viabilidad": 1, "potencial": 2, "interes": 1}, "01a": {"importancia": 3, "viabilidad": 2, "potencial": 3, "interes": 3}}, "elegida": "01a"}'::jsonb, now() - interval '58 days');
INSERT INTO nexus360.respuesta (diagnostico_id, pregunta_id, valor, es_na, es_diferente, texto, ejemplos, otro_texto, valor_clasificado, clasificado_en, respondido_en)
SELECT '36233ea8-1169-5657-8b84-e81cb223bedb', dp.pregunta_id, v.valor::smallint, v.es_na, v.es_diferente, v.texto, v.ejemplos, v.otro, v.clasif::smallint,
       CASE WHEN v.clasif IS NULL THEN NULL ELSE now() - interval '56 days' END, now() - interval '58 days'
  FROM (VALUES
    ('01a', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY['Forma parte de los valores de la empresa', 'Lo decide la gerencia o el dueño']::TEXT[], NULL, NULL),
    ('01b', NULL, TRUE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('01c', 3, FALSE, FALSE, 'Lo aplicamos todo el año y ya vemos resultados concretos.', ARRAY['Carteleras', 'Conversaciones']::TEXT[], NULL, NULL),
    ('02a', NULL, FALSE, TRUE, 'Lo hacemos a nuestra manera, con apoyo de otros.', ARRAY['Reglas de convivencia']::TEXT[], 'Hacemos una jornada anual con las familias del equipo.', 2),
    ('02b', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY[]::TEXT[], NULL, NULL),
    ('02c', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY['Reunión']::TEXT[], NULL, NULL),
    ('03a', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY['Conversación directa con la gerencia', 'Reuniones periódicas']::TEXT[], NULL, NULL),
    ('03b', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY[]::TEXT[], NULL, NULL),
    ('03c', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY[]::TEXT[], NULL, NULL),
    ('04a', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Manejar mejor los residuos', 'Cambiar materiales']::TEXT[], NULL, NULL),
    ('04b', NULL, FALSE, TRUE, 'Lo hacemos a nuestra manera, con apoyo de otros.', ARRAY[]::TEXT[], 'Tenemos un acuerdo con la junta de acción comunal.', NULL),
    ('04c', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY['Revisan recibos de servicios']::TEXT[], NULL, NULL),
    ('05a', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['No se aceptan regalos o favores de proveedores']::TEXT[], NULL, NULL),
    ('05b', NULL, FALSE, TRUE, 'Lo hacemos a nuestra manera, con apoyo de otros.', ARRAY['Que cuiden el ambiente']::TEXT[], 'Tenemos un acuerdo con la junta de acción comunal.', 3),
    ('05c', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY[]::TEXT[], NULL, NULL),
    ('06a', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Etiquetas o fichas claras']::TEXT[], NULL, NULL),
    ('06b', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Contraseñas', 'Política de datos']::TEXT[], NULL, NULL),
    ('06c', 3, FALSE, FALSE, 'Funciona bien: el equipo lo reconoce y hay resultados.', ARRAY[]::TEXT[], NULL, NULL),
    ('07a', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Contrata personas de la zona']::TEXT[], NULL, NULL),
    ('07b', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY['Empleo local']::TEXT[], NULL, NULL),
    ('07c', 3, FALSE, FALSE, 'Funciona bien: el equipo lo reconoce y hay resultados.', ARRAY['Relación con vecinos', 'Número de personas beneficiadas', 'Fotos o registros']::TEXT[], NULL, NULL)
  ) AS v(codigo, valor, es_na, es_diferente, texto, ejemplos, otro, clasif)
  JOIN demo_preguntas dp ON dp.codigo = v.codigo;
INSERT INTO nexus360.respuesta_materia (diagnostico_id, dimension_id, fortalecer, respondido_en)
SELECT DISTINCT '36233ea8-1169-5657-8b84-e81cb223bedb'::uuid, dp.dimension_id, v.texto, now() - interval '58 days'
  FROM (VALUES
    ('01', 'Queremos dejar por escrito lo que hacemos y quién lo lidera.'),
    ('05', 'Queremos reglas claras para compras y pagos.')
  ) AS v(numero, texto)
  JOIN demo_preguntas dp ON dp.numero = v.numero;

-- 4. Metalmecánica El Tiple
INSERT INTO nexus360.empresa (empresa_id, razon_social, nit, dv, sector_id, municipio, departamento, extranjera, creado_en)
VALUES ('1cadc178-8f9f-50c7-ab66-4cb2767304c3', 'DEMO · Metalmecánica El Tiple', '901900121', nexus360.calcular_dv('901900121'), 'industrial', 'Candelaria', 'Valle del Cauca', FALSE, now() - interval '57 days');
INSERT INTO nexus360.ciclo_tamizaje (ciclo_id, empresa_id, anio, tamano, ingresos_rango, personas, vinculacion, vinculacion_detalle, zonas, territorio, clientes, clientes_detalle, creado_en, actualizado_en)
VALUES ('c9ca4e6e-a413-5cef-975f-16575c2feb53', '1cadc178-8f9f-50c7-ab66-4cb2767304c3', 2026, 'pequena', '1000m_10000m', 27, ARRAY['laboral']::TEXT[], NULL, ARRAY['rural']::TEXT[], 'Zona industrial rural', 'empresas', NULL, now() - interval '57 days', now() - interval '57 days');
INSERT INTO nexus360.diagnostico (diagnostico_id, empresa_id, ciclo_id, formato_id, estado, creado_en, completado_en, comentario_final, priorizacion, actualizado_en)
VALUES ('cc60e4d8-b7f9-5d9e-9aaf-2eeafc22e1b0', '1cadc178-8f9f-50c7-ab66-4cb2767304c3', 'c9ca4e6e-a413-5cef-975f-16575c2feb53', 'rse_express', 'completado', now() - interval '57 days', now() - interval '52 days', 'Apoyamos cada año la fiesta patronal del municipio.', '{"filas": {"01a": {"importancia": 3, "viabilidad": 2, "potencial": 3, "interes": 3}, "02a": {"importancia": 2, "viabilidad": 1, "potencial": 3, "interes": 3}, "04b": {"importancia": 2, "viabilidad": 2, "potencial": 3, "interes": 2}, "07c": {"importancia": 2, "viabilidad": 2, "potencial": 3, "interes": 2}}, "elegida": "01a"}'::jsonb, now() - interval '52 days');
INSERT INTO nexus360.respuesta (diagnostico_id, pregunta_id, valor, es_na, es_diferente, texto, ejemplos, otro_texto, valor_clasificado, clasificado_en, respondido_en)
SELECT 'cc60e4d8-b7f9-5d9e-9aaf-2eeafc22e1b0', dp.pregunta_id, v.valor::smallint, v.es_na, v.es_diferente, v.texto, v.ejemplos, v.otro, v.clasif::smallint,
       CASE WHEN v.clasif IS NULL THEN NULL ELSE now() - interval '50 days' END, now() - interval '52 days'
  FROM (VALUES
    ('01a', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY[]::TEXT[], NULL, NULL),
    ('01b', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY['Lo asume el gerente']::TEXT[], NULL, NULL),
    ('01c', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY[]::TEXT[], NULL, NULL),
    ('02a', 1, FALSE, FALSE, 'Lo hacemos cuando se presenta la necesidad, sin un orden fijo.', ARRAY['No contratar menores de edad']::TEXT[], NULL, NULL),
    ('02b', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY['Jornadas excesivas']::TEXT[], NULL, NULL),
    ('02c', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY[]::TEXT[], NULL, NULL),
    ('03a', NULL, TRUE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('03b', 3, FALSE, FALSE, 'Funciona bien: el equipo lo reconoce y hay resultados.', ARRAY['Capacitaciones', 'Revisión de equipos', 'Elementos de protección']::TEXT[], NULL, NULL),
    ('03c', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Inducción']::TEXT[], NULL, NULL),
    ('04a', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY[]::TEXT[], NULL, NULL),
    ('04b', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY[]::TEXT[], NULL, NULL),
    ('04c', NULL, FALSE, TRUE, 'Lo hacemos a nuestra manera, con apoyo de otros.', ARRAY[]::TEXT[], 'Hacemos una jornada anual con las familias del equipo.', 2),
    ('05a', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY['Código de conducta o política escrita', 'Reglas claras para compras y pagos']::TEXT[], NULL, NULL),
    ('05b', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Que cuiden el ambiente']::TEXT[], NULL, NULL),
    ('05c', 3, FALSE, FALSE, 'Lo aplicamos todo el año y ya vemos resultados concretos.', ARRAY['Precios y ofertas claras', 'Asesoría contable o jurídica']::TEXT[], NULL, NULL),
    ('07a', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY['Apoya iniciativas']::TEXT[], NULL, NULL),
    ('07b', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY['Voluntariado', 'Patrocinios']::TEXT[], NULL, NULL),
    ('07c', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY[]::TEXT[], NULL, NULL)
  ) AS v(codigo, valor, es_na, es_diferente, texto, ejemplos, otro, clasif)
  JOIN demo_preguntas dp ON dp.codigo = v.codigo;
INSERT INTO nexus360.respuesta_materia (diagnostico_id, dimension_id, fortalecer, respondido_en)
SELECT DISTINCT 'cc60e4d8-b7f9-5d9e-9aaf-2eeafc22e1b0'::uuid, dp.dimension_id, v.texto, now() - interval '52 days'
  FROM (VALUES
    ('01', 'Queremos dejar por escrito lo que hacemos y quién lo lidera.'),
    ('02', 'Nos gustaría tener un canal para que los vecinos nos cuenten sus inquietudes.')
  ) AS v(numero, texto)
  JOIN demo_preguntas dp ON dp.numero = v.numero;

-- 5. Café Altos del Sur
INSERT INTO nexus360.empresa (empresa_id, razon_social, nit, dv, sector_id, municipio, departamento, extranjera, creado_en)
VALUES ('89a4ad45-0cfd-547a-9907-4aed153c4e85', 'DEMO · Café Altos del Sur', '901900128', nexus360.calcular_dv('901900128'), 'agroindustrial', 'La Unión', 'Nariño', FALSE, now() - interval '52 days');
INSERT INTO nexus360.ciclo_tamizaje (ciclo_id, empresa_id, anio, tamano, ingresos_rango, personas, vinculacion, vinculacion_detalle, zonas, territorio, clientes, clientes_detalle, creado_en, actualizado_en)
VALUES ('4751afff-f71b-5ce1-bccb-d43a2e78f395', '89a4ad45-0cfd-547a-9907-4aed153c4e85', 2026, 'micro', 'menos_1000m', 8, ARRAY['socios', 'temporada']::TEXT[], NULL, ARRAY['veredas', 'rural']::TEXT[], 'Fincas de la vereda La Palma', 'mezcla', NULL, now() - interval '52 days', now() - interval '52 days');
INSERT INTO nexus360.diagnostico (diagnostico_id, empresa_id, ciclo_id, formato_id, estado, creado_en, completado_en, comentario_final, priorizacion, actualizado_en)
VALUES ('80a61238-3197-5610-aaa3-d5dba1119a7b', '89a4ad45-0cfd-547a-9907-4aed153c4e85', '4751afff-f71b-5ce1-bccb-d43a2e78f395', 'rse_express', 'completado', now() - interval '52 days', now() - interval '47 days', NULL, '{"filas": {"03b": {"importancia": 3, "viabilidad": 2, "potencial": 2, "interes": 3}, "06b": {"importancia": 2, "viabilidad": 2, "potencial": 2, "interes": 3}, "01c": {"importancia": 3, "viabilidad": 2, "potencial": 2, "interes": 3}, "02c": {"importancia": 3, "viabilidad": 2, "potencial": 3, "interes": 3}}, "elegida": "02c"}'::jsonb, now() - interval '47 days');
INSERT INTO nexus360.respuesta (diagnostico_id, pregunta_id, valor, es_na, es_diferente, texto, ejemplos, otro_texto, valor_clasificado, clasificado_en, respondido_en)
SELECT '80a61238-3197-5610-aaa3-d5dba1119a7b', dp.pregunta_id, v.valor::smallint, v.es_na, v.es_diferente, v.texto, v.ejemplos, v.otro, v.clasif::smallint,
       CASE WHEN v.clasif IS NULL THEN NULL ELSE now() - interval '45 days' END, now() - interval '47 days'
  FROM (VALUES
    ('01a', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY['Acuerdos entre socios']::TEXT[], NULL, NULL),
    ('01b', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY[]::TEXT[], NULL, NULL),
    ('01c', 0, FALSE, FALSE, 'Todavía no lo hemos trabajado.', ARRAY[]::TEXT[], NULL, NULL),
    ('02a', 1, FALSE, FALSE, 'Lo hacemos cuando se presenta la necesidad, sin un orden fijo.', ARRAY['No contratar menores de edad']::TEXT[], NULL, NULL),
    ('02b', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY[]::TEXT[], NULL, NULL),
    ('02c', 0, FALSE, FALSE, 'Todavía no lo hemos trabajado.', ARRAY[]::TEXT[], NULL, NULL),
    ('03a', 0, FALSE, FALSE, 'Todavía no lo hemos trabajado.', ARRAY[]::TEXT[], NULL, NULL),
    ('03b', 0, FALSE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('03c', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY['Cursos SENA']::TEXT[], NULL, NULL),
    ('04a', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Cambiar materiales', 'Reducir consumos']::TEXT[], NULL, NULL),
    ('04b', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Apagar equipos', 'Ahorro de agua']::TEXT[], NULL, NULL),
    ('04c', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Observan cambios']::TEXT[], NULL, NULL),
    ('05a', 0, FALSE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('05b', 0, FALSE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('05c', 1, FALSE, FALSE, 'Lo hacemos cuando se presenta la necesidad, sin un orden fijo.', ARRAY[]::TEXT[], NULL, NULL),
    ('06a', NULL, TRUE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('06b', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY[]::TEXT[], NULL, NULL),
    ('06c', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY['Correo']::TEXT[], NULL, NULL),
    ('07a', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY['Participa en actividades del barrio o municipio']::TEXT[], NULL, NULL),
    ('07b', NULL, TRUE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('07c', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Fotos o registros', 'Relación con vecinos', 'Número de personas beneficiadas']::TEXT[], NULL, NULL)
  ) AS v(codigo, valor, es_na, es_diferente, texto, ejemplos, otro, clasif)
  JOIN demo_preguntas dp ON dp.codigo = v.codigo;
INSERT INTO nexus360.respuesta_materia (diagnostico_id, dimension_id, fortalecer, respondido_en)
SELECT DISTINCT '80a61238-3197-5610-aaa3-d5dba1119a7b'::uuid, dp.dimension_id, v.texto, now() - interval '47 days'
  FROM (VALUES
    ('01', 'Queremos dejar por escrito lo que hacemos y quién lo lidera.'),
    ('03', 'Queremos organizar mejor la seguridad y salud en el trabajo.'),
    ('05', 'Queremos reglas claras para compras y pagos.'),
    ('06', 'Queremos atender mejor las quejas de los clientes.')
  ) AS v(numero, texto)
  JOIN demo_preguntas dp ON dp.numero = v.numero;

-- 6. Soluciones Contables Andinas
INSERT INTO nexus360.empresa (empresa_id, razon_social, nit, dv, sector_id, municipio, departamento, extranjera, creado_en)
VALUES ('c349e541-ff1f-5e99-9dfb-e36e062415e9', 'DEMO · Soluciones Contables Andinas', '901900135', nexus360.calcular_dv('901900135'), 'servicios', 'Pasto', 'Nariño', FALSE, now() - interval '46 days');
INSERT INTO nexus360.ciclo_tamizaje (ciclo_id, empresa_id, anio, tamano, ingresos_rango, personas, vinculacion, vinculacion_detalle, zonas, territorio, clientes, clientes_detalle, creado_en, actualizado_en)
VALUES ('a4a0eed3-27c3-5d53-8ade-dff48bd9adc9', 'c349e541-ff1f-5e99-9dfb-e36e062415e9', 2026, 'micro', 'menos_1000m', 6, ARRAY['laboral', 'servicios']::TEXT[], NULL, ARRAY['barrios']::TEXT[], 'Centro de la ciudad', 'empresas', NULL, now() - interval '46 days', now() - interval '46 days');
INSERT INTO nexus360.diagnostico (diagnostico_id, empresa_id, ciclo_id, formato_id, estado, creado_en, completado_en, comentario_final, priorizacion, actualizado_en)
VALUES ('0f51c585-d933-5917-a6f1-ecc589f47da2', 'c349e541-ff1f-5e99-9dfb-e36e062415e9', 'a4a0eed3-27c3-5d53-8ade-dff48bd9adc9', 'rse_express', 'completado', now() - interval '46 days', now() - interval '41 days', NULL, '{"filas": {"01a": {"importancia": 2, "viabilidad": 2, "potencial": 3, "interes": 3}, "02b": {"importancia": 3, "viabilidad": 1, "potencial": 2, "interes": 3}, "04a": {"importancia": 2, "viabilidad": 1, "potencial": 2, "interes": 2}, "05a": {"importancia": 2, "viabilidad": 1, "potencial": 2, "interes": 3}}, "elegida": "01a"}'::jsonb, now() - interval '41 days');
INSERT INTO nexus360.respuesta (diagnostico_id, pregunta_id, valor, es_na, es_diferente, texto, ejemplos, otro_texto, valor_clasificado, clasificado_en, respondido_en)
SELECT '0f51c585-d933-5917-a6f1-ecc589f47da2', dp.pregunta_id, v.valor::smallint, v.es_na, v.es_diferente, v.texto, v.ejemplos, v.otro, v.clasif::smallint,
       CASE WHEN v.clasif IS NULL THEN NULL ELSE now() - interval '39 days' END, now() - interval '41 days'
  FROM (VALUES
    ('01a', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY[]::TEXT[], NULL, NULL),
    ('01b', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Lo asume el gerente', 'Se hace con recursos del momento', 'Hay un monto destinado']::TEXT[], NULL, NULL),
    ('01c', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY[]::TEXT[], NULL, NULL),
    ('02a', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['No discriminación', 'No contratar menores de edad', 'Reglas de convivencia']::TEXT[], NULL, NULL),
    ('02b', 1, FALSE, FALSE, 'Lo hacemos cuando se presenta la necesidad, sin un orden fijo.', ARRAY[]::TEXT[], NULL, NULL),
    ('02c', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY[]::TEXT[], NULL, NULL),
    ('03a', 3, FALSE, FALSE, 'Funciona bien: el equipo lo reconoce y hay resultados.', ARRAY[]::TEXT[], NULL, NULL),
    ('03b', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY['Elementos de protección', 'SG-SST']::TEXT[], NULL, NULL),
    ('03c', 3, FALSE, FALSE, 'Lo aplicamos todo el año y ya vemos resultados concretos.', ARRAY['Cursos SENA']::TEXT[], NULL, NULL),
    ('04a', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY[]::TEXT[], NULL, NULL),
    ('04b', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY[]::TEXT[], NULL, NULL),
    ('04c', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY[]::TEXT[], NULL, NULL),
    ('05a', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY[]::TEXT[], NULL, NULL),
    ('05b', 1, FALSE, FALSE, 'Lo hacemos cuando se presenta la necesidad, sin un orden fijo.', ARRAY[]::TEXT[], NULL, NULL),
    ('05c', 1, FALSE, FALSE, 'Lo hacemos cuando se presenta la necesidad, sin un orden fijo.', ARRAY['Revisión de la gerencia']::TEXT[], NULL, NULL),
    ('07a', 1, FALSE, FALSE, 'Lo hacemos cuando se presenta la necesidad, sin un orden fijo.', ARRAY['Contrata personas de la zona']::TEXT[], NULL, NULL),
    ('07b', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Voluntariado']::TEXT[], NULL, NULL),
    ('07c', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY['Relación con vecinos']::TEXT[], NULL, NULL)
  ) AS v(codigo, valor, es_na, es_diferente, texto, ejemplos, otro, clasif)
  JOIN demo_preguntas dp ON dp.codigo = v.codigo;
INSERT INTO nexus360.respuesta_materia (diagnostico_id, dimension_id, fortalecer, respondido_en)
SELECT DISTINCT '0f51c585-d933-5917-a6f1-ecc589f47da2'::uuid, dp.dimension_id, v.texto, now() - interval '41 days'
  FROM (VALUES
    ('01', 'Queremos dejar por escrito lo que hacemos y quién lo lidera.'),
    ('02', 'Nos gustaría tener un canal para que los vecinos nos cuenten sus inquietudes.'),
    ('03', 'Queremos organizar mejor la seguridad y salud en el trabajo.'),
    ('05', 'Queremos reglas claras para compras y pagos.')
  ) AS v(numero, texto)
  JOIN demo_preguntas dp ON dp.numero = v.numero;

-- 7. Energía Solar del Pacífico
INSERT INTO nexus360.empresa (empresa_id, razon_social, nit, dv, sector_id, municipio, departamento, extranjera, creado_en)
VALUES ('b666e675-4b66-529e-9318-cbd618480647', 'DEMO · Energía Solar del Pacífico', '901900142', nexus360.calcular_dv('901900142'), 'energia', 'Tumaco', 'Nariño', FALSE, now() - interval '41 days');
INSERT INTO nexus360.ciclo_tamizaje (ciclo_id, empresa_id, anio, tamano, ingresos_rango, personas, vinculacion, vinculacion_detalle, zonas, territorio, clientes, clientes_detalle, creado_en, actualizado_en)
VALUES ('afb585d7-c02c-53ba-a7f2-ef556153d902', 'b666e675-4b66-529e-9318-cbd618480647', 2026, 'pequena', '1000m_10000m', 22, ARRAY['laboral', 'servicios']::TEXT[], NULL, ARRAY['afro', 'rural']::TEXT[], 'Consejos comunitarios de la costa', 'publicas', NULL, now() - interval '41 days', now() - interval '41 days');
INSERT INTO nexus360.diagnostico (diagnostico_id, empresa_id, ciclo_id, formato_id, estado, creado_en, completado_en, comentario_final, priorizacion, actualizado_en)
VALUES ('8ec1306b-717e-5722-b8e7-41af4816a68d', 'b666e675-4b66-529e-9318-cbd618480647', 'afb585d7-c02c-53ba-a7f2-ef556153d902', 'rse_express', 'completado', now() - interval '41 days', now() - interval '36 days', 'Apoyamos cada año la fiesta patronal del municipio.', '{"filas": {"03c": {"importancia": 3, "viabilidad": 3, "potencial": 2, "interes": 3}, "05c": {"importancia": 2, "viabilidad": 3, "potencial": 3, "interes": 1}, "01a": {"importancia": 2, "viabilidad": 3, "potencial": 2, "interes": 3}, "02a": {"importancia": 3, "viabilidad": 2, "potencial": 2, "interes": 3}}, "elegida": "03c"}'::jsonb, now() - interval '36 days');
INSERT INTO nexus360.respuesta (diagnostico_id, pregunta_id, valor, es_na, es_diferente, texto, ejemplos, otro_texto, valor_clasificado, clasificado_en, respondido_en)
SELECT '8ec1306b-717e-5722-b8e7-41af4816a68d', dp.pregunta_id, v.valor::smallint, v.es_na, v.es_diferente, v.texto, v.ejemplos, v.otro, v.clasif::smallint,
       CASE WHEN v.clasif IS NULL THEN NULL ELSE now() - interval '34 days' END, now() - interval '36 days'
  FROM (VALUES
    ('01a', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Lo decide la gerencia o el dueño', 'Forma parte de los valores de la empresa', 'Política escrita']::TEXT[], NULL, NULL),
    ('01b', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY['Se hace con recursos del momento', 'Hay un monto destinado']::TEXT[], NULL, NULL),
    ('01c', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Redes sociales', 'Informe o balance', 'Reuniones']::TEXT[], NULL, NULL),
    ('02a', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Inclusión de personas', 'Reglas de convivencia']::TEXT[], NULL, NULL),
    ('02b', NULL, TRUE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('02c', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY['Habla directamente con el dueño', 'Reunión']::TEXT[], NULL, NULL),
    ('03a', 4, FALSE, FALSE, 'Medimos resultados y hacemos cambios con lo aprendido.', ARRAY[]::TEXT[], NULL, NULL),
    ('03b', NULL, FALSE, TRUE, 'Lo hacemos a nuestra manera, con apoyo de otros.', ARRAY['Revisión de equipos']::TEXT[], 'Tenemos un acuerdo con la junta de acción comunal.', NULL),
    ('03c', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY['Seguimiento del jefe']::TEXT[], NULL, NULL),
    ('04a', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY[]::TEXT[], NULL, NULL),
    ('04b', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Apagar equipos', 'Entregar a gestor autorizado']::TEXT[], NULL, NULL),
    ('04c', 4, FALSE, FALSE, 'Medimos resultados y hacemos cambios con lo aprendido.', ARRAY[]::TEXT[], NULL, NULL),
    ('05a', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Código de conducta o política escrita', 'No se aceptan regalos o favores de proveedores']::TEXT[], NULL, NULL),
    ('05b', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY['Que traten bien a su gente', 'Que sean locales']::TEXT[], NULL, NULL),
    ('05c', 1, FALSE, FALSE, 'Lo hacemos cuando se presenta la necesidad, sin un orden fijo.', ARRAY[]::TEXT[], NULL, NULL),
    ('07a', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY[]::TEXT[], NULL, NULL),
    ('07b', 4, FALSE, FALSE, 'Medimos resultados y hacemos cambios con lo aprendido.', ARRAY[]::TEXT[], NULL, NULL),
    ('07c', 3, FALSE, FALSE, 'Funciona bien: el equipo lo reconoce y hay resultados.', ARRAY['Número de personas beneficiadas', 'Fotos o registros']::TEXT[], NULL, NULL)
  ) AS v(codigo, valor, es_na, es_diferente, texto, ejemplos, otro, clasif)
  JOIN demo_preguntas dp ON dp.codigo = v.codigo;
INSERT INTO nexus360.respuesta_materia (diagnostico_id, dimension_id, fortalecer, respondido_en)
SELECT DISTINCT '8ec1306b-717e-5722-b8e7-41af4816a68d'::uuid, dp.dimension_id, v.texto, now() - interval '36 days'
  FROM (VALUES
    ('01', 'Queremos dejar por escrito lo que hacemos y quién lo lidera.'),
    ('02', 'Nos gustaría tener un canal para que los vecinos nos cuenten sus inquietudes.'),
    ('03', 'Queremos organizar mejor la seguridad y salud en el trabajo.')
  ) AS v(numero, texto)
  JOIN demo_preguntas dp ON dp.numero = v.numero;

-- 8. Confecciones Nariño
INSERT INTO nexus360.empresa (empresa_id, razon_social, nit, dv, sector_id, municipio, departamento, extranjera, creado_en)
VALUES ('acb29294-c42f-58b2-bd4d-e5582fc8f58d', 'DEMO · Confecciones Nariño', '901900149', nexus360.calcular_dv('901900149'), 'industrial', 'Pasto', 'Nariño', FALSE, now() - interval '35 days');
INSERT INTO nexus360.ciclo_tamizaje (ciclo_id, empresa_id, anio, tamano, ingresos_rango, personas, vinculacion, vinculacion_detalle, zonas, territorio, clientes, clientes_detalle, creado_en, actualizado_en)
VALUES ('e09d160f-94ac-58dc-a0b7-bacc83b52804', 'acb29294-c42f-58b2-bd4d-e5582fc8f58d', 2026, 'pequena', 'menos_1000m', 42, ARRAY['laboral', 'otra']::TEXT[], NULL, ARRAY['barrios']::TEXT[], 'Barrio Santa Mónica', 'empresas', NULL, now() - interval '35 days', now() - interval '35 days');
INSERT INTO nexus360.diagnostico (diagnostico_id, empresa_id, ciclo_id, formato_id, estado, creado_en, completado_en, comentario_final, priorizacion, actualizado_en)
VALUES ('2e75fabb-760c-5c73-aaf4-14ee49d19f6b', 'acb29294-c42f-58b2-bd4d-e5582fc8f58d', 'e09d160f-94ac-58dc-a0b7-bacc83b52804', 'rse_express', 'completado', now() - interval '35 days', now() - interval '30 days', NULL, '{"filas": {"01b": {"importancia": 3, "viabilidad": 3, "potencial": 3, "interes": 3}, "04c": {"importancia": 3, "viabilidad": 1, "potencial": 2, "interes": 3}, "05b": {"importancia": 3, "viabilidad": 1, "potencial": 2, "interes": 3}, "07b": {"importancia": 3, "viabilidad": 1, "potencial": 3, "interes": 3}}, "elegida": "01b"}'::jsonb, now() - interval '30 days');
INSERT INTO nexus360.respuesta (diagnostico_id, pregunta_id, valor, es_na, es_diferente, texto, ejemplos, otro_texto, valor_clasificado, clasificado_en, respondido_en)
SELECT '2e75fabb-760c-5c73-aaf4-14ee49d19f6b', dp.pregunta_id, v.valor::smallint, v.es_na, v.es_diferente, v.texto, v.ejemplos, v.otro, v.clasif::smallint,
       CASE WHEN v.clasif IS NULL THEN NULL ELSE now() - interval '28 days' END, now() - interval '30 days'
  FROM (VALUES
    ('01a', 3, FALSE, FALSE, 'Lo aplicamos todo el año y ya vemos resultados concretos.', ARRAY['Política escrita', 'Lo decide la gerencia o el dueño', 'Forma parte de los valores de la empresa']::TEXT[], NULL, NULL),
    ('01b', 0, FALSE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('01c', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY[]::TEXT[], NULL, NULL),
    ('02a', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY[]::TEXT[], NULL, NULL),
    ('02b', NULL, TRUE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('02c', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Procedimiento escrito', 'Habla directamente con el dueño', 'Reunión']::TEXT[], NULL, NULL),
    ('03a', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Buzón']::TEXT[], NULL, NULL),
    ('03b', NULL, FALSE, TRUE, 'Lo hacemos a nuestra manera, con apoyo de otros.', ARRAY['Afiliación a ARL']::TEXT[], 'Tenemos un acuerdo con la junta de acción comunal.', 2),
    ('03c', 3, FALSE, FALSE, 'Funciona bien: el equipo lo reconoce y hay resultados.', ARRAY['Seguimiento del jefe']::TEXT[], NULL, NULL),
    ('04a', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY[]::TEXT[], NULL, NULL),
    ('04b', 1, FALSE, FALSE, 'Lo hacemos cuando se presenta la necesidad, sin un orden fijo.', ARRAY['Apagar equipos']::TEXT[], NULL, NULL),
    ('04c', 0, FALSE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('05a', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['La gerencia revisa y aprueba los pagos']::TEXT[], NULL, NULL),
    ('05b', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY['Que cuiden el ambiente']::TEXT[], NULL, NULL),
    ('05c', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY[]::TEXT[], NULL, NULL),
    ('07a', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Contrata personas de la zona']::TEXT[], NULL, NULL),
    ('07b', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY[]::TEXT[], NULL, NULL),
    ('07c', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY['Comentarios de la comunidad']::TEXT[], NULL, NULL)
  ) AS v(codigo, valor, es_na, es_diferente, texto, ejemplos, otro, clasif)
  JOIN demo_preguntas dp ON dp.codigo = v.codigo;
INSERT INTO nexus360.respuesta_materia (diagnostico_id, dimension_id, fortalecer, respondido_en)
SELECT DISTINCT '2e75fabb-760c-5c73-aaf4-14ee49d19f6b'::uuid, dp.dimension_id, v.texto, now() - interval '30 days'
  FROM (VALUES
    ('01', 'Queremos dejar por escrito lo que hacemos y quién lo lidera.'),
    ('03', 'Queremos organizar mejor la seguridad y salud en el trabajo.'),
    ('04', 'Nos interesa separar residuos y bajar el consumo de energía.'),
    ('05', 'Queremos reglas claras para compras y pagos.'),
    ('07', 'Nos gustaría apoyar a la comunidad de forma más ordenada.')
  ) AS v(numero, texto)
  JOIN demo_preguntas dp ON dp.numero = v.numero;

-- 9. Supermercado El Vecino
INSERT INTO nexus360.empresa (empresa_id, razon_social, nit, dv, sector_id, municipio, departamento, extranjera, creado_en)
VALUES ('0c996bb5-d7f2-5844-a981-bf77712c2313', 'DEMO · Supermercado El Vecino', '901900156', nexus360.calcular_dv('901900156'), 'comercio', 'Túquerres', 'Nariño', FALSE, now() - interval '29 days');
INSERT INTO nexus360.ciclo_tamizaje (ciclo_id, empresa_id, anio, tamano, ingresos_rango, personas, vinculacion, vinculacion_detalle, zonas, territorio, clientes, clientes_detalle, creado_en, actualizado_en)
VALUES ('b6189f26-6ee9-5aeb-a813-920a8443183e', '0c996bb5-d7f2-5844-a981-bf77712c2313', 2026, 'nose', 'no_indica', 15, ARRAY['laboral', 'socios']::TEXT[], NULL, ARRAY['barrios', 'veredas']::TEXT[], 'Plaza principal y veredas cercanas', 'personas', NULL, now() - interval '29 days', now() - interval '29 days');
INSERT INTO nexus360.diagnostico (diagnostico_id, empresa_id, ciclo_id, formato_id, estado, creado_en, completado_en, comentario_final, priorizacion, actualizado_en)
VALUES ('45ba49c7-c3e6-5e7a-b60a-4b4d3c19bcfa', '0c996bb5-d7f2-5844-a981-bf77712c2313', 'b6189f26-6ee9-5aeb-a813-920a8443183e', 'rse_express', 'completado', now() - interval '29 days', now() - interval '24 days', NULL, '{"filas": {"02a": {"importancia": 3, "viabilidad": 3, "potencial": 3, "interes": 3}, "04a": {"importancia": 2, "viabilidad": 3, "potencial": 3, "interes": 3}, "05c": {"importancia": 3, "viabilidad": 3, "potencial": 2, "interes": 1}, "01b": {"importancia": 2, "viabilidad": 1, "potencial": 2, "interes": 3}}, "elegida": "02a"}'::jsonb, now() - interval '24 days');
INSERT INTO nexus360.respuesta (diagnostico_id, pregunta_id, valor, es_na, es_diferente, texto, ejemplos, otro_texto, valor_clasificado, clasificado_en, respondido_en)
SELECT '45ba49c7-c3e6-5e7a-b60a-4b4d3c19bcfa', dp.pregunta_id, v.valor::smallint, v.es_na, v.es_diferente, v.texto, v.ejemplos, v.otro, v.clasif::smallint,
       CASE WHEN v.clasif IS NULL THEN NULL ELSE now() - interval '22 days' END, now() - interval '24 days'
  FROM (VALUES
    ('01a', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Forma parte de los valores de la empresa']::TEXT[], NULL, NULL),
    ('01b', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY['Una persona encargada']::TEXT[], NULL, NULL),
    ('01c', NULL, FALSE, TRUE, 'Lo hacemos a nuestra manera, con apoyo de otros.', ARRAY['Conversaciones']::TEXT[], 'Compostamos los residuos con una huerta vecina.', NULL),
    ('02a', 0, FALSE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('02b', 1, FALSE, FALSE, 'Lo hacemos cuando se presenta la necesidad, sin un orden fijo.', ARRAY['Trabajo infantil']::TEXT[], NULL, NULL),
    ('02c', 1, FALSE, FALSE, 'Lo hacemos cuando se presenta la necesidad, sin un orden fijo.', ARRAY['Procedimiento escrito']::TEXT[], NULL, NULL),
    ('03a', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY[]::TEXT[], NULL, NULL),
    ('03b', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY['SG-SST', 'Capacitaciones', 'Revisión de equipos']::TEXT[], NULL, NULL),
    ('03c', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Capacitaciones', 'Inducción']::TEXT[], NULL, NULL),
    ('04a', 0, FALSE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('04b', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY['Ahorro de agua']::TEXT[], NULL, NULL),
    ('04c', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY[]::TEXT[], NULL, NULL),
    ('05a', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['La gerencia revisa y aprueba los pagos', 'Se habla del tema con el equipo', 'Dos personas aprueban gastos importantes']::TEXT[], NULL, NULL),
    ('05b', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY['Que cuiden el ambiente']::TEXT[], NULL, NULL),
    ('05c', 0, FALSE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('06a', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Garantías', 'Explicación directa', 'Controles de calidad']::TEXT[], NULL, NULL),
    ('06b', NULL, TRUE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('06c', NULL, TRUE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('07a', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY['Apoya iniciativas']::TEXT[], NULL, NULL),
    ('07b', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY['Empleo local']::TEXT[], NULL, NULL),
    ('07c', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY[]::TEXT[], NULL, NULL)
  ) AS v(codigo, valor, es_na, es_diferente, texto, ejemplos, otro, clasif)
  JOIN demo_preguntas dp ON dp.codigo = v.codigo;
INSERT INTO nexus360.respuesta_materia (diagnostico_id, dimension_id, fortalecer, respondido_en)
SELECT DISTINCT '45ba49c7-c3e6-5e7a-b60a-4b4d3c19bcfa'::uuid, dp.dimension_id, v.texto, now() - interval '24 days'
  FROM (VALUES
    ('01', 'Queremos dejar por escrito lo que hacemos y quién lo lidera.'),
    ('02', 'Nos gustaría tener un canal para que los vecinos nos cuenten sus inquietudes.'),
    ('04', 'Nos interesa separar residuos y bajar el consumo de energía.'),
    ('07', 'Nos gustaría apoyar a la comunidad de forma más ordenada.')
  ) AS v(numero, texto)
  JOIN demo_preguntas dp ON dp.numero = v.numero;

-- 10. Clínica Veterinaria Patitas
INSERT INTO nexus360.empresa (empresa_id, razon_social, nit, dv, sector_id, municipio, departamento, extranjera, creado_en)
VALUES ('72e0038a-31af-58da-8d11-7fa41e79a72f', 'DEMO · Clínica Veterinaria Patitas', '901900163', nexus360.calcular_dv('901900163'), 'servicios', 'Palmira', 'Valle del Cauca', FALSE, now() - interval '17 days');
INSERT INTO nexus360.ciclo_tamizaje (ciclo_id, empresa_id, anio, tamano, ingresos_rango, personas, vinculacion, vinculacion_detalle, zonas, territorio, clientes, clientes_detalle, creado_en, actualizado_en)
VALUES ('14bcea30-2bcf-586d-85b1-85a476f86794', '72e0038a-31af-58da-8d11-7fa41e79a72f', 2026, 'micro', 'menos_1000m', 9, ARRAY['laboral']::TEXT[], NULL, ARRAY['barrios']::TEXT[], 'Barrio Colombia', 'personas', NULL, now() - interval '17 days', now() - interval '17 days');
INSERT INTO nexus360.diagnostico (diagnostico_id, empresa_id, ciclo_id, formato_id, estado, creado_en, completado_en, comentario_final, priorizacion, actualizado_en)
VALUES ('3bccaebc-6534-511f-8061-8dc11080734c', '72e0038a-31af-58da-8d11-7fa41e79a72f', '14bcea30-2bcf-586d-85b1-85a476f86794', 'rse_express', 'borrador', now() - interval '17 days', NULL, NULL, NULL, now() - interval '12 days');
INSERT INTO nexus360.respuesta (diagnostico_id, pregunta_id, valor, es_na, es_diferente, texto, ejemplos, otro_texto, valor_clasificado, clasificado_en, respondido_en)
SELECT '3bccaebc-6534-511f-8061-8dc11080734c', dp.pregunta_id, v.valor::smallint, v.es_na, v.es_diferente, v.texto, v.ejemplos, v.otro, v.clasif::smallint,
       CASE WHEN v.clasif IS NULL THEN NULL ELSE now() - interval '10 days' END, now() - interval '12 days'
  FROM (VALUES
    ('01a', 3, FALSE, FALSE, 'Funciona bien: el equipo lo reconoce y hay resultados.', ARRAY['Política escrita']::TEXT[], NULL, NULL),
    ('01b', NULL, TRUE, FALSE, NULL, ARRAY[]::TEXT[], NULL, NULL),
    ('01c', NULL, FALSE, TRUE, 'Lo hacemos a nuestra manera, con apoyo de otros.', ARRAY['Conversaciones']::TEXT[], 'Lo trabajamos con la cooperativa de productores.', NULL),
    ('02a', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY[]::TEXT[], NULL, NULL),
    ('02b', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY[]::TEXT[], NULL, NULL),
    ('02c', 3, FALSE, FALSE, 'Funciona bien: el equipo lo reconoce y hay resultados.', ARRAY['Reunión']::TEXT[], NULL, NULL),
    ('03a', 4, FALSE, FALSE, 'Medimos resultados y hacemos cambios con lo aprendido.', ARRAY['Comité']::TEXT[], NULL, NULL),
    ('03b', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY[]::TEXT[], NULL, NULL),
    ('03c', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY[]::TEXT[], NULL, NULL)
  ) AS v(codigo, valor, es_na, es_diferente, texto, ejemplos, otro, clasif)
  JOIN demo_preguntas dp ON dp.codigo = v.codigo;
INSERT INTO nexus360.respuesta_materia (diagnostico_id, dimension_id, fortalecer, respondido_en)
SELECT DISTINCT '3bccaebc-6534-511f-8061-8dc11080734c'::uuid, dp.dimension_id, v.texto, now() - interval '12 days'
  FROM (VALUES
    ('01', 'Queremos dejar por escrito lo que hacemos y quién lo lidera.'),
    ('02', 'Nos gustaría tener un canal para que los vecinos nos cuenten sus inquietudes.')
  ) AS v(numero, texto)
  JOIN demo_preguntas dp ON dp.numero = v.numero;

-- 11. Agroinsumos La Cosecha
INSERT INTO nexus360.empresa (empresa_id, razon_social, nit, dv, sector_id, municipio, departamento, extranjera, creado_en)
VALUES ('30f7b6ce-577d-5c92-8fb2-d5fb369eeeda', 'DEMO · Agroinsumos La Cosecha', '901900170', nexus360.calcular_dv('901900170'), 'comercio', 'Pasto', 'Nariño', FALSE, now() - interval '11 days');
INSERT INTO nexus360.ciclo_tamizaje (ciclo_id, empresa_id, anio, tamano, ingresos_rango, personas, vinculacion, vinculacion_detalle, zonas, territorio, clientes, clientes_detalle, creado_en, actualizado_en)
VALUES ('908d630c-ac2d-5c6e-b150-8d4e3b697a6d', '30f7b6ce-577d-5c92-8fb2-d5fb369eeeda', 2026, 'mediana', '10000m_50000m', 60, ARRAY['laboral', 'temporada']::TEXT[], NULL, ARRAY['rural', 'otras']::TEXT[], 'Bodegas en zona rural', 'mezcla', NULL, now() - interval '11 days', now() - interval '11 days');
INSERT INTO nexus360.diagnostico (diagnostico_id, empresa_id, ciclo_id, formato_id, estado, creado_en, completado_en, comentario_final, priorizacion, actualizado_en)
VALUES ('341248fe-45f9-5ec5-a5c0-2e52b6e6efa2', '30f7b6ce-577d-5c92-8fb2-d5fb369eeeda', '908d630c-ac2d-5c6e-b150-8d4e3b697a6d', 'rse_express', 'borrador', now() - interval '11 days', NULL, NULL, NULL, now() - interval '6 days');
INSERT INTO nexus360.respuesta (diagnostico_id, pregunta_id, valor, es_na, es_diferente, texto, ejemplos, otro_texto, valor_clasificado, clasificado_en, respondido_en)
SELECT '341248fe-45f9-5ec5-a5c0-2e52b6e6efa2', dp.pregunta_id, v.valor::smallint, v.es_na, v.es_diferente, v.texto, v.ejemplos, v.otro, v.clasif::smallint,
       CASE WHEN v.clasif IS NULL THEN NULL ELSE now() - interval '4 days' END, now() - interval '6 days'
  FROM (VALUES
    ('01a', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY[]::TEXT[], NULL, NULL),
    ('01b', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY[]::TEXT[], NULL, NULL),
    ('01c', 2, FALSE, FALSE, 'Tenemos un acuerdo escrito y lo revisamos en reunión.', ARRAY['Conversaciones', 'Informe o balance']::TEXT[], NULL, NULL),
    ('02a', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Inclusión de personas']::TEXT[], NULL, NULL),
    ('02b', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY[]::TEXT[], NULL, NULL),
    ('02c', 2, FALSE, FALSE, 'Hay una persona a cargo y acuerdos claros con el equipo.', ARRAY['Habla directamente con el dueño', 'Línea o WhatsApp', 'Reunión']::TEXT[], NULL, NULL),
    ('03a', 3, FALSE, FALSE, 'Funciona bien: el equipo lo reconoce y hay resultados.', ARRAY['Reuniones periódicas', 'Conversación directa con la gerencia']::TEXT[], NULL, NULL),
    ('03b', 3, FALSE, FALSE, 'Llevamos un registro y hemos visto mejoras.', ARRAY['Revisión de equipos']::TEXT[], NULL, NULL),
    ('03c', 1, FALSE, FALSE, 'Lo maneja el dueño directamente, de manera informal.', ARRAY['Seguimiento del jefe']::TEXT[], NULL, NULL),
    ('04a', 3, FALSE, FALSE, 'Lo aplicamos todo el año y ya vemos resultados concretos.', ARRAY['Cumplir un requisito de un cliente']::TEXT[], NULL, NULL),
    ('04b', 2, FALSE, FALSE, 'Está organizado: sabemos quién lo hace y cada cuánto.', ARRAY['Reutilizar', 'Apagar equipos']::TEXT[], NULL, NULL),
    ('04c', 1, FALSE, FALSE, 'Hemos empezado hace poco, todavía sin responsable claro.', ARRAY['Observan cambios']::TEXT[], NULL, NULL)
  ) AS v(codigo, valor, es_na, es_diferente, texto, ejemplos, otro, clasif)
  JOIN demo_preguntas dp ON dp.codigo = v.codigo;
INSERT INTO nexus360.respuesta_materia (diagnostico_id, dimension_id, fortalecer, respondido_en)
SELECT DISTINCT '341248fe-45f9-5ec5-a5c0-2e52b6e6efa2'::uuid, dp.dimension_id, v.texto, now() - interval '6 days'
  FROM (VALUES
    ('01', 'Queremos dejar por escrito lo que hacemos y quién lo lidera.'),
    ('02', 'Nos gustaría tener un canal para que los vecinos nos cuenten sus inquietudes.'),
    ('03', 'Queremos organizar mejor la seguridad y salud en el trabajo.')
  ) AS v(numero, texto)
  JOIN demo_preguntas dp ON dp.numero = v.numero;

-- 12. Taller Mecánico Rueda Libre
INSERT INTO nexus360.empresa (empresa_id, razon_social, nit, dv, sector_id, municipio, departamento, extranjera, creado_en)
VALUES ('aafa5517-2883-5d58-80a8-210d589c162f', 'DEMO · Taller Mecánico Rueda Libre', '901900177', nexus360.calcular_dv('901900177'), 'movilidad', 'Ipiales', 'Nariño', FALSE, now() - interval '8 days');
INSERT INTO nexus360.ciclo_tamizaje (ciclo_id, empresa_id, anio, tamano, ingresos_rango, personas, vinculacion, vinculacion_detalle, zonas, territorio, clientes, clientes_detalle, creado_en, actualizado_en)
VALUES ('55b7909f-4171-5e87-89ec-e624c85a79c1', 'aafa5517-2883-5d58-80a8-210d589c162f', 2026, 'micro', NULL, 5, ARRAY['socios']::TEXT[], NULL, ARRAY['barrios']::TEXT[], 'Barrio El Charco', 'personas', NULL, now() - interval '8 days', now() - interval '8 days');

ALTER TABLE nexus360.respuesta ENABLE TRIGGER trg_proteger_clasificacion;
ALTER TABLE nexus360.empresa           FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.ciclo_tamizaje    FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.diagnostico       FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.respuesta         FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.respuesta_materia FORCE ROW LEVEL SECURITY;
ALTER TABLE nexus360.evidencia         FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    RAISE NOTICE 'Demo RSE Express: % empresas, % respuestas.',
        (SELECT count(*) FROM nexus360.empresa WHERE razon_social LIKE 'DEMO · %'),
        (SELECT count(*) FROM nexus360.respuesta r JOIN nexus360.diagnostico d ON d.diagnostico_id = r.diagnostico_id
           JOIN nexus360.empresa e ON e.empresa_id = d.empresa_id WHERE e.razon_social LIKE 'DEMO · %');
END $$;

COMMIT;
