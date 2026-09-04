-- 005_catalogo.sql
-- Siembra el catálogo normativo (formato, dimension, seccion, pregunta,
-- peso_sector_materia) EXACTAMENTE con los datos que hoy vive
-- hardcodeados en el front (src/data/formato01.ts y formato02.ts),
-- generado automáticamente para no transcribir a mano (47 preguntas,
-- 11 dimensiones, pesos validados por los triggers Σ=1.0 del schema).
--
-- UUIDs determinísticos (uuid5 sobre una clave natural) -> el mismo id
-- sale igual en local y en Supabase, y correr esto dos veces no duplica
-- nada (ON CONFLICT DO NOTHING sobre la propia PK).
--
-- Aplicar UNA vez, con el rol dueño del esquema:
--   psql "<conexión>" -f db/005_catalogo.sql

BEGIN;
SET search_path TO nexus360;

-- formato
INSERT INTO formato (formato_id, codigo, nombre, norma, naturaleza) VALUES
    ('iso26000', 'Formato 01', 'Madurez en Responsabilidad Social', 'ISO 26000:2010', 'Estándar voluntario · autoevaluación'),
    ('ley2173', 'Formato 02', 'Áreas de Vida', 'Ley 2173 de 2021', 'Obligación legal · verificable documentalmente')
ON CONFLICT (formato_id) DO NOTHING;

-- ===== dimensiones/secciones/preguntas de iso26000 =====
INSERT INTO dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional) VALUES
    ('d4864442-5a36-5d13-b602-14600c2dabb1', 'iso26000', '01', 'Gobernanza Organizacional', 'Gobernanza', 'Los procesos y estructuras de decisión que permiten crear y aplicar políticas de responsabilidad social.', NULL, NULL)
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('ab4e142f-fcb3-5d0b-a99d-686f258e8e91', 'd4864442-5a36-5d13-b602-14600c2dabb1', NULL, 1, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('b327d05b-5ea2-5e9c-a573-ff6d5c9e5170', 'gobernanza.a', 'ab4e142f-fcb3-5d0b-a99d-686f258e8e91', 'A', '¿Cómo se define y aprueba la orientación de la organización en responsabilidad social?', 0.3, NULL, 'una política de RSE aprobada por la alta dirección')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('2b02fec0-883a-5114-b7d8-1d436d1de61c', 'gobernanza.b', 'ab4e142f-fcb3-5d0b-a99d-686f258e8e91', 'D', '¿Cómo están asignados los roles, las responsabilidades y los recursos para la gestión de RSE?', 0.35, NULL, 'el mapa de roles, responsabilidades y presupuesto de RSE')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('6c8a3775-7349-5f04-9134-822d211727b9', 'gobernanza.c', 'ab4e142f-fcb3-5d0b-a99d-686f258e8e91', 'E', '¿Cómo rinde cuentas la organización ante sus grupos de interés sobre su desempeño en RSE?', 0.35, NULL, 'un reporte periódico de desempeño hacia los grupos de interés')
ON CONFLICT (pregunta_id) DO NOTHING;

INSERT INTO dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional) VALUES
    ('6b0a2242-490b-5573-8f28-82090ade9ca5', 'iso26000', '02', 'Derechos Humanos', 'DD. HH.', 'Debida diligencia, situaciones de riesgo, no discriminación y derechos civiles, políticos, económicos, sociales y culturales.', NULL, NULL)
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('df01e4ea-dd08-5f78-b1da-67f7c3302199', '6b0a2242-490b-5573-8f28-82090ade9ca5', NULL, 1, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('1ab5e89b-20ee-511d-b1e1-254dd688f10b', 'ddhh.a', 'df01e4ea-dd08-5f78-b1da-67f7c3302199', 'A', '¿Cómo aborda la organización su compromiso con los derechos humanos?', 0.3, NULL, 'una declaración de compromiso en derechos humanos')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('789bdae6-74a5-5af9-9c38-eff83b3e678c', 'ddhh.b', 'df01e4ea-dd08-5f78-b1da-67f7c3302199', 'D', '¿Cómo identifica y evalúa los riesgos de derechos humanos en sus operaciones y en su cadena de valor?', 0.35, NULL, 'la matriz de debida diligencia sobre operaciones y proveedores')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('5ec9ab24-709f-5e64-ac94-e19efb0c4328', 'ddhh.c', 'df01e4ea-dd08-5f78-b1da-67f7c3302199', 'E', '¿Cómo atiende y resuelve las reclamaciones de personas o comunidades afectadas?', 0.35, NULL, 'un mecanismo de reclamación accesible con tiempos de respuesta medidos')
ON CONFLICT (pregunta_id) DO NOTHING;

INSERT INTO dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional) VALUES
    ('89694bea-feb4-50bd-9f7c-37ae0d015f7e', 'iso26000', '03', 'Prácticas Laborales', 'Laboral', 'Empleo y relaciones laborales, condiciones de trabajo, protección social, diálogo social, salud y seguridad, desarrollo humano.', NULL, NULL)
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('8c471e50-c790-5c84-8b11-31a23e78fbc6', '89694bea-feb4-50bd-9f7c-37ae0d015f7e', NULL, 1, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('53a94136-da8a-569d-bcda-a91e19ebeba9', 'laborales.a', '8c471e50-c790-5c84-8b11-31a23e78fbc6', 'A', '¿Cómo están formalizadas las condiciones de empleo y los canales de diálogo con los trabajadores?', 0.3, NULL, 'las condiciones de empleo y los canales de diálogo con los trabajadores')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('b2e55d55-3566-5e5e-9c94-e5c74ade7d21', 'laborales.b', '8c471e50-c790-5c84-8b11-31a23e78fbc6', 'D', '¿Cómo gestiona la seguridad y salud en el trabajo?', 0.35, NULL, 'el sistema de gestión de seguridad y salud en el trabajo')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('b89dfe6c-469b-5112-9e40-0560cb90370d', 'laborales.c', '8c471e50-c790-5c84-8b11-31a23e78fbc6', 'E', '¿Cómo desarrolla las competencias de sus trabajadores y verifica el resultado de esa formación?', 0.35, NULL, 'el plan de formación con medición de resultado, no solo de asistencia')
ON CONFLICT (pregunta_id) DO NOTHING;

INSERT INTO dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional) VALUES
    ('2a0d3f40-0db5-5cab-bba6-fd712039a2f7', 'iso26000', '04', 'Medio Ambiente', 'Ambiental', 'Prevención de la contaminación, uso sostenible de recursos, mitigación del cambio climático y protección del entorno.', NULL, NULL)
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('e915ad92-aeee-5ef7-b92f-d3d6c7ef3967', '2a0d3f40-0db5-5cab-bba6-fd712039a2f7', NULL, 1, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('32edbba0-f6ed-5962-a17c-1b3602054d65', 'ambiente.a', 'e915ad92-aeee-5ef7-b92f-d3d6c7ef3967', 'A', '¿Cómo define la organización sus compromisos y metas ambientales?', 0.3, NULL, 'las metas ambientales con horizonte y responsable')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('47e6b694-98bd-5111-83b6-03955a1f5c02', 'ambiente.b', 'e915ad92-aeee-5ef7-b92f-d3d6c7ef3967', 'D', '¿Cómo gestiona el uso de recursos (agua, energía, materiales) y la generación de residuos?', 0.35, NULL, 'el programa de uso de recursos y manejo de residuos')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('53a3b52e-4566-5dc7-84d4-412d90614c33', 'ambiente.c', 'e915ad92-aeee-5ef7-b92f-d3d6c7ef3967', 'E', '¿Cómo mide su desempeño ambiental y actúa sobre los resultados obtenidos?', 0.35, NULL, 'los indicadores ambientales y el ciclo de acción sobre los resultados')
ON CONFLICT (pregunta_id) DO NOTHING;

INSERT INTO dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional) VALUES
    ('47d4b5cc-544e-5476-98a9-45af4e3a4864', 'iso26000', '05', 'Prácticas Justas de Operación', 'Op. Justas', 'Anticorrupción, participación política responsable, competencia justa, promoción de la RSE en la cadena de valor.', NULL, NULL)
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('87355a5d-5749-56bd-978f-8e1bd40d1bea', '47d4b5cc-544e-5476-98a9-45af4e3a4864', NULL, 1, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('62d2868e-3cf7-53af-b32d-19837ea82761', 'practicas.a', '87355a5d-5749-56bd-978f-8e1bd40d1bea', 'A', '¿Cómo previene la corrupción y los conflictos de intereses?', 0.3, NULL, 'la política anticorrupción y de conflicto de intereses')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('fe402b36-1d24-5233-b503-479b2fa33f97', 'practicas.b', '87355a5d-5749-56bd-978f-8e1bd40d1bea', 'D', '¿Cómo integra criterios de responsabilidad social en la selección y evaluación de proveedores?', 0.35, NULL, 'los criterios de RSE en selección y evaluación de proveedores')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('a5086df3-b51c-5b9c-8da8-0e98b08f95dc', 'practicas.c', '87355a5d-5749-56bd-978f-8e1bd40d1bea', 'E', '¿Cómo verifica el cumplimiento de sus lineamientos de competencia justa y de relación con el Estado?', 0.35, NULL, 'la verificación periódica de competencia justa y relación con el Estado')
ON CONFLICT (pregunta_id) DO NOTHING;

INSERT INTO dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional) VALUES
    ('111a243d-09bf-5bf4-a7a1-fde4c935ad98', 'iso26000', '06', 'Asuntos de Consumidores', 'Consumo', 'Prácticas justas de mercadeo, protección de la salud y seguridad, consumo sostenible, privacidad de datos.', NULL, NULL)
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('d3f707b8-36c3-5866-ad6f-b1ae5e2098c2', '111a243d-09bf-5bf4-a7a1-fde4c935ad98', NULL, 1, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('a40f0f7c-5a15-5959-81c3-fdf0bf762526', 'consumidores.a', 'd3f707b8-36c3-5866-ad6f-b1ae5e2098c2', 'A', '¿Cómo define sus compromisos frente a clientes en información, calidad y seguridad?', 0.3, NULL, 'los compromisos de información, calidad y seguridad al cliente')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('a9dfd60b-b66f-589d-850f-8c6ca1ea40d7', 'consumidores.b', 'd3f707b8-36c3-5866-ad6f-b1ae5e2098c2', 'D', '¿Cómo protege los datos personales de sus clientes?', 0.35, NULL, 'la política de tratamiento de datos personales')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('c35925a1-7660-58ce-bae4-87a8bb6f1474', 'consumidores.c', 'd3f707b8-36c3-5866-ad6f-b1ae5e2098c2', 'E', '¿Cómo atiende, registra y resuelve las peticiones, quejas y reclamos?', 0.35, NULL, 'el registro y la resolución medida de peticiones, quejas y reclamos')
ON CONFLICT (pregunta_id) DO NOTHING;

INSERT INTO dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional) VALUES
    ('7520f6c9-fa30-53d6-bdb0-e97b35f29fc3', 'iso26000', '07', 'Participación Activa y Desarrollo de la Comunidad', 'Comunidad', 'Involucramiento, educación, generación de empleo, desarrollo tecnológico e inversión social en el territorio.', NULL, NULL)
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('f92011a3-e599-5096-97c4-eee12aba3af9', '7520f6c9-fa30-53d6-bdb0-e97b35f29fc3', NULL, 1, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('b09bc52a-12cc-5869-9941-c59376986bba', 'comunidad.a', 'f92011a3-e599-5096-97c4-eee12aba3af9', 'A', '¿Cómo define su relacionamiento con las comunidades del territorio donde opera?', 0.3, NULL, 'la estrategia de relacionamiento con las comunidades del territorio')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('d6058a6e-7a3a-5fc8-94f5-27017b1c6ca5', 'comunidad.b', 'f92011a3-e599-5096-97c4-eee12aba3af9', 'D', '¿Cómo planifica su inversión social y bajo qué criterios?', 0.35, NULL, 'los criterios y el plan de inversión social')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('2f465095-1d51-5c3a-a8d2-a8e31ecc6490', 'comunidad.c', 'f92011a3-e599-5096-97c4-eee12aba3af9', 'E', '¿Cómo mide el resultado de sus iniciativas en el territorio?', 0.35, NULL, 'la medición de resultado de las iniciativas territoriales')
ON CONFLICT (pregunta_id) DO NOTHING;

-- ===== dimensiones/secciones/preguntas de ley2173 =====
INSERT INTO dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional) VALUES
    ('5948d55c-fc84-5659-b36d-986cbdd08a20', 'ley2173', 'D1', 'Línea base y gobernanza de la obligación', 'Línea base', 'Determinar a cuánto asciende la obligación y quién responde por ella.', 0.15, NULL)
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('cae4083c-86e2-5be7-a1f7-675a145cefae', '5948d55c-fc84-5659-b36d-986cbdd08a20', 'Determinación de la obligación', 0.6, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('73575151-b65b-596f-81d2-3e7f85d23ea0', '1.1', 'cae4083c-86e2-5be7-a1f7-675a145cefae', 'B', '¿Cómo determina y actualiza su clasificación de tamaño empresarial según ingresos brutos en UVT?', 0.3, 'Clasificación soportada en los estados financieros del último cierre.', 'la clasificación de tamaño en UVT con soporte contable')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('527edd79-d622-51b2-8886-9f01e4220ca0', '1.2', 'cae4083c-86e2-5be7-a1f7-675a145cefae', 'B', '¿Cómo consolida y certifica el número de empleados con contrato vigente al 31 de diciembre?', 0.4, 'Certificación firmada por el representante legal.', 'la certificación de empleados firmada por el representante legal')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('263b3a45-70e4-50de-8a38-f8856106fa26', '1.3', 'cae4083c-86e2-5be7-a1f7-675a145cefae', 'B', '¿Cómo calcula la meta anual de individuos a sembrar?', 0.3, 'Memoria de cálculo aprobada internamente.', 'la memoria de cálculo de la meta anual de siembra')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('08e3ecae-81f7-5966-93e6-9a81dd1daecc', '5948d55c-fc84-5659-b36d-986cbdd08a20', 'Responsabilidad interna', 0.4, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('d826e2f7-f07f-567d-9a45-cb54a5afc349', '1.4', '08e3ecae-81f7-5966-93e6-9a81dd1daecc', 'A', '¿Cómo asigna la responsabilidad interna sobre esta obligación?', 0.45, 'Designación formal con rol y autoridad definidos.', 'la designación del responsable interno de la obligación')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('d9ebdb5e-1b33-5f2e-b816-bc6ae06033a2', '1.5', '08e3ecae-81f7-5966-93e6-9a81dd1daecc', 'A', '¿Cómo incorpora la obligación en su matriz de requisitos legales y en el presupuesto anual?', 0.55, 'Matriz legal vigente que la incluye.', 'la inclusión de la obligación en matriz legal y presupuesto')
ON CONFLICT (pregunta_id) DO NOTHING;

INSERT INTO dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional) VALUES
    ('2a2dda1e-1066-53f8-97fa-9a47a5204884', 'ley2173', 'D2', 'Habilitación territorial', 'Territorio', 'Consultar, seleccionar y formalizar el Área de Vida donde se ejecutará.', 0.2, NULL)
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('7650caa4-2f80-598c-9314-a904cb335fb4', '2a2dda1e-1066-53f8-97fa-9a47a5204884', 'Consulta y disponibilidad', 0.55, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('ee7e1f65-7fd5-525f-a55d-16e27dcd1fbc', '2.1', '7650caa4-2f80-598c-9314-a904cb335fb4', 'C', '¿Cómo verifica la publicación oficial de Áreas de Vida en los municipios de su interés?', 0.35, 'Constancia de consulta a fuente oficial.', 'la verificación documentada de Áreas de Vida publicadas')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('eae25e4a-8017-595d-898b-88078a88e95e', '2.2', '7650caa4-2f80-598c-9314-a904cb335fb4', 'C', '¿Cómo gestiona la consulta de disponibilidad y capacidad ante la autoridad municipal?', 0.4, 'Número de radicado de la consulta.', 'la consulta de disponibilidad ante la autoridad municipal')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('272b9dab-4551-5238-acee-c31114af925b', '2.3', '7650caa4-2f80-598c-9314-a904cb335fb4', 'C', '¿Cómo archiva y hace seguimiento a las respuestas de la autoridad?', 0.25, 'Oficio de respuesta archivado y trazable.', 'el archivo y seguimiento de respuestas de la autoridad')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('b0553a2e-a5a9-517a-a890-65c890226b6a', '2a2dda1e-1066-53f8-97fa-9a47a5204884', 'Selección y formalización', 0.45, 'requiereAreasDeVida')
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('9ccfad58-c5a2-5919-9321-abd1ea1af554', '2.4', 'b0553a2e-a5a9-517a-a890-65c890226b6a', 'C', '¿Cómo formaliza ante el municipio la elección del Área de Vida?', 0.4, 'Comunicación radicada de elección del área.', 'la comunicación formal de elección del Área de Vida')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('0a22b038-e06c-54e2-ae3d-95720cdb84cc', '2.5', 'b0553a2e-a5a9-517a-a890-65c890226b6a', 'C', '¿Cómo verifica la inscripción del área en el REAA?', 0.3, 'Consulta al REAA documentada.', 'la verificación de inscripción del área en el REAA')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('d2c85404-da42-5a58-8b90-4555bc485648', '2.6', 'b0553a2e-a5a9-517a-a890-65c890226b6a', 'C', '¿Cómo gestiona los acuerdos de conservación cuando el predio es privado o colectivo?', 0.3, 'Acuerdo de conservación suscrito.', 'el acuerdo de conservación con el titular del predio')
ON CONFLICT (pregunta_id) DO NOTHING;

INSERT INTO dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional) VALUES
    ('52f4098b-1586-5fdc-b2c2-e78a26e363a0', 'ley2173', 'D3', 'Programa de siembra', 'Programa', 'El instrumento técnico, su presupuesto y su radicación ante la autoridad.', 0.3, 'requiereAreasDeVida')
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('1248e3ec-1db6-565c-b765-c23367b17ab4', '52f4098b-1586-5fdc-b2c2-e78a26e363a0', 'Contenido técnico', 0.55, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('b8f1b399-8bbe-5cdc-a398-35a106193949', '3.1', '1248e3ec-1db6-565c-b765-c23367b17ab4', 'D', '¿Cómo define las especies nativas a establecer y su pertinencia ecosistémica?', 0.3, 'Listado con identificación taxonómica.', 'el listado de especies nativas con identificación taxonómica')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('6ba1563c-a73e-5d10-918a-b9c1c06767f9', '3.2', '1248e3ec-1db6-565c-b765-c23367b17ab4', 'D', '¿Cómo define el área de intervención, la densidad y el arreglo de siembra?', 0.25, 'Ficha técnica con cartografía del polígono.', 'la ficha técnica de área, densidad y arreglo de siembra')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('2191be8f-e4df-503f-85e4-2f5c2b2d6c0d', '3.3', '1248e3ec-1db6-565c-b765-c23367b17ab4', 'D', '¿Cómo caracteriza ecológica y socioeconómicamente el Área de Vida?', 0.25, 'Estudio de caracterización del área.', 'la caracterización ecológica y socioeconómica del área')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('c353c2f3-7b66-5688-ba69-4097363801f5', '3.4', '1248e3ec-1db6-565c-b765-c23367b17ab4', 'D', '¿Cómo construye el cronograma frente al calendario municipal y la ventana climática?', 0.2, 'Cronograma alineado y aprobado.', 'el cronograma alineado a la ventana climática del municipio')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('593abda2-4bb0-5b9f-ab43-cf52a10d8006', '52f4098b-1586-5fdc-b2c2-e78a26e363a0', 'Recursos y trámite', 0.45, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('73c964ba-2b57-5449-8d3b-4a733433307d', '3.5', '593abda2-4bb0-5b9f-ab43-cf52a10d8006', 'D', '¿Cómo presupuesta el ciclo completo, incluyendo mantenimiento y monitoreo a dos años?', 0.4, 'Presupuesto plurianual aprobado.', 'el presupuesto plurianual que cubre los dos años de permanencia')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('988a4a1e-c26f-5b18-8b22-8260aee78211', '3.6', '593abda2-4bb0-5b9f-ab43-cf52a10d8006', 'D', '¿Cómo selecciona operador y viveros con registro ICA vigente?', 0.3, 'Registro ICA del vivero verificado.', 'la selección de viveros con registro ICA vigente')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('f392270f-4fc6-5c51-ab02-c7b945f9c176', '3.7', '593abda2-4bb0-5b9f-ab43-cf52a10d8006', 'C', '¿Cómo gestiona la radicación del programa y el seguimiento a su aprobación?', 0.3, 'Radicado y acto de aprobación.', 'la radicación del programa de siembra ante la autoridad')
ON CONFLICT (pregunta_id) DO NOTHING;

INSERT INTO dimension (dimension_id, formato_id, numero, nombre, abrev, descripcion, peso, condicional) VALUES
    ('3742d827-54d1-5bd0-b02c-3d0065eac7b9', 'ley2173', 'D4', 'Ejecución, permanencia y trazabilidad', 'Permanencia', 'Sembrar es la mitad. Lo que valida el cumplimiento es que los árboles sigan vivos a dos años.', 0.35, 'requiereAreasDeVida')
ON CONFLICT (dimension_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('d0545cff-2e36-514c-8e2a-b59524a11331', '3742d827-54d1-5bd0-b02c-3d0065eac7b9', 'Ejecución', 0.3, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('71980961-5143-5837-ba55-d746e1cc196c', '4.1', 'd0545cff-2e36-514c-8e2a-b59524a11331', 'C', '¿Cómo gestiona el aviso previo de inicio de actividades?', 0.45, 'Comunicación radicada con diez días o más de antelación.', 'el aviso previo de inicio con diez días de antelación')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('fd082e0e-c3b0-59f5-8f20-7868c2a6d303', '4.2', 'd0545cff-2e36-514c-8e2a-b59524a11331', 'E', '¿Cómo verifica y documenta el origen del material vegetal?', 0.55, 'Certificado ICA del vivero de origen.', 'el certificado ICA que acredita el origen del material vegetal')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('2581817d-d2a5-54d0-b50f-c1f71b8488bc', '3742d827-54d1-5bd0-b02c-3d0065eac7b9', 'Permanencia', 0.45, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('7c5d8403-ce1c-5f08-990e-0dd795265886', '4.3', '2581817d-d2a5-54d0-b50f-c1f71b8488bc', 'D', '¿Cómo planifica el mantenimiento de los dos años posteriores a la siembra?', 0.35, 'Plan de mantenimiento documentado a 24 meses.', 'el plan de mantenimiento a veinticuatro meses')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('1de28892-434a-5985-b769-e64c62ae4ce1', '4.4', '2581817d-d2a5-54d0-b50f-c1f71b8488bc', 'E', '¿Cómo registra la supervivencia y gestiona la reposición de mortalidad?', 0.4, 'Registro de supervivencia con reposiciones ejecutadas.', 'el registro de supervivencia y la reposición de mortalidad')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('c67d23ae-77cc-5d0b-a46a-b06fcd8dbfaf', '4.5', '2581817d-d2a5-54d0-b50f-c1f71b8488bc', 'E', '¿Cómo monitorea con indicadores y periodicidad definida?', 0.25, 'Protocolo de monitoreo aplicado con reportes.', 'el protocolo de monitoreo con indicadores y periodicidad')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO seccion (seccion_id, dimension_id, nombre, peso, condicional) VALUES
    ('3217f5d3-327d-5b7d-b2ab-904f5d822f85', '3742d827-54d1-5bd0-b02c-3d0065eac7b9', 'Trazabilidad y certificación', 0.25, NULL)
ON CONFLICT (seccion_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('f2d253cd-3e93-5a64-a615-862a1ece19bf', '4.6', '3217f5d3-327d-5b7d-b2ab-904f5d822f85', 'E', '¿Cómo construye el expediente documental de la siembra?', 0.35, 'Expediente con geolocalización, fotografías y soportes.', 'el expediente documental con geolocalización y soportes')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('a2a37ceb-d5ca-5886-9149-00eda4c15482', '4.7', '3217f5d3-327d-5b7d-b2ab-904f5d822f85', 'E', '¿Cómo elabora el informe de cumplimiento y reporta al MADS?', 0.4, 'Informe con identificación taxonómica remitido.', 'el informe de cumplimiento con identificación taxonómica')
ON CONFLICT (pregunta_id) DO NOTHING;
INSERT INTO pregunta (pregunta_id, codigo, seccion_id, arquetipo_id, texto, peso, evidencia_nivel3, accion) VALUES
    ('b9f61ceb-e42d-56a1-84e8-9f0ace826b6f', '4.8', '3217f5d3-327d-5b7d-b2ab-904f5d822f85', 'C', '¿Cómo gestiona la solicitud del certificado «Siembra Vida Empresarial»?', 0.25, 'Solicitud radicada o certificado obtenido.', 'la solicitud del certificado Siembra Vida Empresarial')
ON CONFLICT (pregunta_id) DO NOTHING;

-- peso_sector_materia (pesos de cada materia ISO 26000 por sector)
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('industrial', 'd4864442-5a36-5d13-b602-14600c2dabb1', 0.14)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('industrial', '6b0a2242-490b-5573-8f28-82090ade9ca5', 0.12)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('industrial', '89694bea-feb4-50bd-9f7c-37ae0d015f7e', 0.18)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('industrial', '2a0d3f40-0db5-5cab-bba6-fd712039a2f7', 0.22)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('industrial', '47d4b5cc-544e-5476-98a9-45af4e3a4864', 0.14)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('industrial', '111a243d-09bf-5bf4-a7a1-fde4c935ad98', 0.08)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('industrial', '7520f6c9-fa30-53d6-bdb0-e97b35f29fc3', 0.12)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('servicios', 'd4864442-5a36-5d13-b602-14600c2dabb1', 0.16)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('servicios', '6b0a2242-490b-5573-8f28-82090ade9ca5', 0.12)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('servicios', '89694bea-feb4-50bd-9f7c-37ae0d015f7e', 0.2)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('servicios', '2a0d3f40-0db5-5cab-bba6-fd712039a2f7', 0.1)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('servicios', '47d4b5cc-544e-5476-98a9-45af4e3a4864', 0.16)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('servicios', '111a243d-09bf-5bf4-a7a1-fde4c935ad98', 0.16)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('servicios', '7520f6c9-fa30-53d6-bdb0-e97b35f29fc3', 0.1)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('agroindustrial', 'd4864442-5a36-5d13-b602-14600c2dabb1', 0.12)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('agroindustrial', '6b0a2242-490b-5573-8f28-82090ade9ca5', 0.14)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('agroindustrial', '89694bea-feb4-50bd-9f7c-37ae0d015f7e', 0.16)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('agroindustrial', '2a0d3f40-0db5-5cab-bba6-fd712039a2f7', 0.22)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('agroindustrial', '47d4b5cc-544e-5476-98a9-45af4e3a4864', 0.1)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('agroindustrial', '111a243d-09bf-5bf4-a7a1-fde4c935ad98', 0.08)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('agroindustrial', '7520f6c9-fa30-53d6-bdb0-e97b35f29fc3', 0.18)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('comercio', 'd4864442-5a36-5d13-b602-14600c2dabb1', 0.14)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('comercio', '6b0a2242-490b-5573-8f28-82090ade9ca5', 0.1)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('comercio', '89694bea-feb4-50bd-9f7c-37ae0d015f7e', 0.16)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('comercio', '2a0d3f40-0db5-5cab-bba6-fd712039a2f7', 0.12)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('comercio', '47d4b5cc-544e-5476-98a9-45af4e3a4864', 0.16)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('comercio', '111a243d-09bf-5bf4-a7a1-fde4c935ad98', 0.22)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('comercio', '7520f6c9-fa30-53d6-bdb0-e97b35f29fc3', 0.1)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('energia', 'd4864442-5a36-5d13-b602-14600c2dabb1', 0.14)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('energia', '6b0a2242-490b-5573-8f28-82090ade9ca5', 0.14)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('energia', '89694bea-feb4-50bd-9f7c-37ae0d015f7e', 0.16)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('energia', '2a0d3f40-0db5-5cab-bba6-fd712039a2f7', 0.22)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('energia', '47d4b5cc-544e-5476-98a9-45af4e3a4864', 0.12)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('energia', '111a243d-09bf-5bf4-a7a1-fde4c935ad98', 0.06)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('energia', '7520f6c9-fa30-53d6-bdb0-e97b35f29fc3', 0.16)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('movilidad', 'd4864442-5a36-5d13-b602-14600c2dabb1', 0.14)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('movilidad', '6b0a2242-490b-5573-8f28-82090ade9ca5', 0.12)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('movilidad', '89694bea-feb4-50bd-9f7c-37ae0d015f7e', 0.18)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('movilidad', '2a0d3f40-0db5-5cab-bba6-fd712039a2f7', 0.18)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('movilidad', '47d4b5cc-544e-5476-98a9-45af4e3a4864', 0.12)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('movilidad', '111a243d-09bf-5bf4-a7a1-fde4c935ad98', 0.16)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;
INSERT INTO peso_sector_materia (sector_id, dimension_id, peso) VALUES
    ('movilidad', '7520f6c9-fa30-53d6-bdb0-e97b35f29fc3', 0.1)
ON CONFLICT (sector_id, dimension_id) DO NOTHING;

COMMIT;