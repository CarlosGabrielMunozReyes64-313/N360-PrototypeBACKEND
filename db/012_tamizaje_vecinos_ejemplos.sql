-- 012_tamizaje_vecinos_ejemplos.sql
-- =====================================================================
-- Tamizaje: la T5 se divide en dos preguntas · Autodiagnóstico: ejemplos
-- descriptivos
-- =====================================================================
--
-- Qué hace, en este orden:
--
--  1. Divide la T5 («¿En qué lugares desarrolla su actividad y qué
--     comunidades o vecinos están cerca de su operación?») en:
--       T5a · ¿En qué lugares desarrolla su actividad?
--       T5b · ¿Qué comunidades o vecinos están cerca de su operación?
--     Las dos preguntas comparten la columna `zonas` (cada código pertenece
--     a una sola) y cada una tiene su texto libre: `territorio` (T5a, ya
--     existía) y `vecinos` (T5b, nueva). Así los tamizajes guardados siguen
--     siendo válidos: sus códigos no cambian.
--     Códigos nuevos de T5a: comercial, industrial.
--     Códigos nuevos de T5b: viviendas, instituciones, campesinos, negocios,
--     otros_vecinos y ninguno («No hay comunidades ni vecinos cerca», que no
--     se puede marcar junto con otro vecino).
--     T5b NO se exige en la base: los tamizajes anteriores no la tienen. La
--     exigen el backend (EmpresaIn) y el frontend al guardar; quien tenga un
--     tamizaje anterior la responde la próxima vez que entre.
--
--  2. Los ejemplos del autodiagnóstico pasan a ser frases descriptivas
--     (mismo número y mismo orden por pregunta). Se actualiza el catálogo
--     (pregunta.ejemplos) y se traducen los ejemplos ya marcados en las
--     respuestas guardadas (respuesta.ejemplos), del texto corto anterior
--     al texto nuevo. Mismo contenido que src/data/rseExpress.ts.
--
-- Es idempotente: se puede correr más de una vez (por ejemplo, después de
-- cargar db/demo/demo_rse_express.sql, que usa los textos cortos).
--
-- Aplicar con el rol dueño del esquema (NO nexus360_app), DESPUÉS de 011 y
-- ANTES de desplegar esta versión del backend (lee y escribe `vecinos`):
--   psql "<conexión>" -f db/012_tamizaje_vecinos_ejemplos.sql
-- =====================================================================

BEGIN;
SET search_path TO nexus360;

-- =====================================================================
-- 1. Tamizaje: T5a y T5b
-- =====================================================================
ALTER TABLE nexus360.ciclo_tamizaje
    ADD COLUMN IF NOT EXISTS vecinos TEXT
        CONSTRAINT chk_ciclo_vecinos_largo CHECK (vecinos IS NULL OR char_length(vecinos) <= 2000);

COMMENT ON COLUMN nexus360.ciclo_tamizaje.zonas IS
    'T5a (lugares: barrios, comercial, industrial, veredas, rural, otras) y T5b (comunidades o vecinos: '
    'viviendas, instituciones, campesinos, negocios, indigenas, afro, otros_vecinos, ninguno).';
COMMENT ON COLUMN nexus360.ciclo_tamizaje.territorio IS
    'T5a: texto libre sobre los lugares donde la empresa desarrolla su actividad.';
COMMENT ON COLUMN nexus360.ciclo_tamizaje.vecinos IS
    'T5b: texto libre sobre las comunidades o vecinos cercanos a la operación. NULL en tamizajes anteriores a la división de la T5.';

-- La lista de códigos permitidos la creó 009 como restricción de columna
-- (nombre automático). Se busca por su definición para no depender del nombre.
DO $zonas$
DECLARE
    v_nombre TEXT;
BEGIN
    FOR v_nombre IN
        SELECT conname
          FROM pg_constraint
         WHERE conrelid = 'nexus360.ciclo_tamizaje'::regclass
           AND contype = 'c'
           AND pg_get_constraintdef(oid) LIKE '%zonas <@%'
    LOOP
        EXECUTE format('ALTER TABLE nexus360.ciclo_tamizaje DROP CONSTRAINT %I', v_nombre);
    END LOOP;
END
$zonas$;

ALTER TABLE nexus360.ciclo_tamizaje DROP CONSTRAINT IF EXISTS chk_ciclo_zonas_ninguno;
ALTER TABLE nexus360.ciclo_tamizaje
    ADD CONSTRAINT chk_ciclo_zonas CHECK (zonas <@ ARRAY[
        'barrios', 'comercial', 'industrial', 'veredas', 'rural', 'otras',
        'viviendas', 'instituciones', 'campesinos', 'negocios', 'indigenas', 'afro', 'otros_vecinos', 'ninguno'
    ]::TEXT[]),
    -- «No hay comunidades ni vecinos cerca» excluye a los demás vecinos.
    ADD CONSTRAINT chk_ciclo_zonas_ninguno CHECK (NOT (
        'ninguno' = ANY (zonas)
        AND zonas && ARRAY['viviendas', 'instituciones', 'campesinos', 'negocios', 'indigenas', 'afro', 'otros_vecinos']::TEXT[]
    ));

-- =====================================================================
-- 2. Ejemplos descriptivos
-- =====================================================================
CREATE TEMP TABLE _ejemplo_nuevo (
    pregunta_id UUID NOT NULL,
    codigo      TEXT NOT NULL,
    orden       INT  NOT NULL,
    antes       TEXT NOT NULL,
    texto       TEXT NOT NULL CHECK (char_length(texto) <= 200),
    PRIMARY KEY (pregunta_id, orden)
) ON COMMIT DROP;

INSERT INTO _ejemplo_nuevo (pregunta_id, codigo, orden, antes, texto) VALUES
    ('fe6997af-4429-5e01-b184-1067eac81263', '01a', 1, 'Lo decide la gerencia o el dueño',
     'El dueño o la gerencia decide qué acciones hacer, por ejemplo apoyar a un trabajador en una calamidad o donar a una causa'),
    ('fe6997af-4429-5e01-b184-1067eac81263', '01a', 2, 'Acuerdos entre socios',
     'Los socios conversan y se ponen de acuerdo sobre qué hacer por el equipo, los clientes, el ambiente o la comunidad'),
    ('fe6997af-4429-5e01-b184-1067eac81263', '01a', 3, 'Forma parte de los valores de la empresa',
     'Cuidar a las personas y al entorno hace parte de los valores de la empresa y se nota en cómo trabajamos'),
    ('fe6997af-4429-5e01-b184-1067eac81263', '01a', 4, 'Política escrita',
     'Tenemos una política escrita de responsabilidad social, aprobada por la dirección y conocida por el equipo'),
    ('0434882d-dd92-5536-9d42-067416a97f65', '01b', 1, 'Lo asume el gerente',
     'El gerente o el dueño se encarga personalmente, además de sus otras tareas'),
    ('0434882d-dd92-5536-9d42-067416a97f65', '01b', 2, 'Una persona encargada',
     'Una persona del equipo tiene a su cargo estas acciones y dedica algunas horas a organizarlas'),
    ('0434882d-dd92-5536-9d42-067416a97f65', '01b', 3, 'Se hace con recursos del momento',
     'Se hacen con el dinero o el tiempo que haya disponible en el momento, sin un presupuesto fijo'),
    ('0434882d-dd92-5536-9d42-067416a97f65', '01b', 4, 'Hay un monto destinado',
     'Cada año separamos un monto de dinero o un tiempo fijo para estas acciones dentro del presupuesto'),
    ('bdd99e10-1e69-5de0-aeca-492244f22539', '01c', 1, 'Conversaciones',
     'Lo contamos en conversaciones del día a día con el equipo, los clientes o los vecinos'),
    ('bdd99e10-1e69-5de0-aeca-492244f22539', '01c', 2, 'Reuniones',
     'Lo compartimos en reuniones con el equipo, los socios o la comunidad'),
    ('bdd99e10-1e69-5de0-aeca-492244f22539', '01c', 3, 'Redes sociales',
     'Publicamos fotos y noticias de lo que hacemos en redes sociales o en WhatsApp'),
    ('bdd99e10-1e69-5de0-aeca-492244f22539', '01c', 4, 'Carteleras',
     'Lo ponemos en carteleras o avisos visibles dentro de la empresa'),
    ('bdd99e10-1e69-5de0-aeca-492244f22539', '01c', 5, 'Informe o balance',
     'Preparamos un informe o balance, por ejemplo cada año, con lo que hicimos y los resultados'),
    ('76aee61d-5ed3-5d12-baf9-bed1360302bb', '02a', 1, 'Trato respetuoso',
     'Exigimos un trato amable y respetuoso entre compañeros, jefes, clientes y proveedores, sin gritos, burlas ni humillaciones'),
    ('76aee61d-5ed3-5d12-baf9-bed1360302bb', '02a', 2, 'No discriminación',
     'No tratamos distinto a nadie por su género, edad, origen, color de piel, religión, discapacidad u orientación sexual'),
    ('76aee61d-5ed3-5d12-baf9-bed1360302bb', '02a', 3, 'No contratar menores de edad',
     'No contratamos a menores de 18 años y no permitimos que niños, niñas o adolescentes trabajen en la empresa'),
    ('76aee61d-5ed3-5d12-baf9-bed1360302bb', '02a', 4, 'Inclusión de personas',
     'Abrimos oportunidades de trabajo a personas con discapacidad, víctimas del conflicto, migrantes, mayores de 50 años o jóvenes sin experiencia'),
    ('76aee61d-5ed3-5d12-baf9-bed1360302bb', '02a', 5, 'Reglas de convivencia',
     'Tenemos reglas de convivencia acordadas, por ejemplo cómo resolver un conflicto o qué hacer ante un caso de acoso'),
    ('46c2329d-b16b-50d1-8b5c-30451ede6c7f', '02b', 1, 'Condiciones inseguras',
     'Condiciones inseguras, como máquinas sin protección, pisos resbalosos, cables sueltos o trabajo en alturas sin equipo'),
    ('46c2329d-b16b-50d1-8b5c-30451ede6c7f', '02b', 2, 'Jornadas excesivas',
     'Jornadas excesivas, como turnos muy largos, horas extra sin pago o semanas sin día de descanso'),
    ('46c2329d-b16b-50d1-8b5c-30451ede6c7f', '02b', 3, 'Trabajo infantil',
     'Trabajo infantil: niños, niñas o adolescentes trabajando en la empresa o en la de un proveedor'),
    ('46c2329d-b16b-50d1-8b5c-30451ede6c7f', '02b', 4, 'Discriminación',
     'Discriminación o acoso: tratar peor a alguien por quién es, o burlas, presiones o maltratos repetidos'),
    ('99a2c106-3530-5011-ad4e-f89ba7b4d84e', '02c', 1, 'Habla directamente con el dueño',
     'La persona habla directamente con el dueño o el gerente, que la escucha y busca una solución'),
    ('99a2c106-3530-5011-ad4e-f89ba7b4d84e', '02c', 2, 'Línea o WhatsApp',
     'Tenemos una línea telefónica o un WhatsApp donde cualquier persona puede contar su inquietud'),
    ('99a2c106-3530-5011-ad4e-f89ba7b4d84e', '02c', 3, 'Buzón',
     'Hay un buzón, físico o en internet, para dejar quejas o sugerencias, incluso sin dar el nombre'),
    ('99a2c106-3530-5011-ad4e-f89ba7b4d84e', '02c', 4, 'Reunión',
     'Hacemos reuniones con el equipo o con los vecinos para escuchar inquietudes y acordar soluciones'),
    ('99a2c106-3530-5011-ad4e-f89ba7b4d84e', '02c', 5, 'Procedimiento escrito',
     'Tenemos un procedimiento escrito que dice quién recibe la queja, en cuánto tiempo se responde y cómo se hace seguimiento'),
    ('82f87be7-8e1c-5791-a889-3cf75323554d', '03a', 1, 'Contratos escritos',
     'Cada persona tiene un contrato escrito con su salario, horario, funciones y tipo de vinculación'),
    ('82f87be7-8e1c-5791-a889-3cf75323554d', '03a', 2, 'Reglamento interno',
     'Tenemos un reglamento interno de trabajo que explica horarios, permisos, descansos y faltas'),
    ('82f87be7-8e1c-5791-a889-3cf75323554d', '03a', 3, 'Reuniones periódicas',
     'Hacemos reuniones periódicas, semanales o mensuales, para hablar con el equipo de lo que funciona y lo que se puede mejorar'),
    ('82f87be7-8e1c-5791-a889-3cf75323554d', '03a', 4, 'Conversación directa con la gerencia',
     'Las personas pueden hablar directamente con la gerencia cuando tienen una propuesta o un problema'),
    ('82f87be7-8e1c-5791-a889-3cf75323554d', '03a', 5, 'Grupo de chat',
     'Tenemos un grupo de chat del equipo donde también se comentan propuestas e inquietudes'),
    ('82f87be7-8e1c-5791-a889-3cf75323554d', '03a', 6, 'Buzón',
     'Hay un buzón de sugerencias para el equipo, en papel o en internet'),
    ('82f87be7-8e1c-5791-a889-3cf75323554d', '03a', 7, 'Comité',
     'Funciona un comité con trabajadores, como el de convivencia laboral o el COPASST, que se reúne y deja actas'),
    ('f480d733-fec9-5a2b-871e-0de38be5271d', '03b', 1, 'Afiliación a ARL',
     'Todas las personas que trabajan con la empresa están afiliadas a una ARL desde el primer día'),
    ('f480d733-fec9-5a2b-871e-0de38be5271d', '03b', 2, 'Elementos de protección',
     'Entregamos y reponemos elementos de protección (casco, guantes, gafas, tapabocas, botas) y revisamos que se usen'),
    ('f480d733-fec9-5a2b-871e-0de38be5271d', '03b', 3, 'Capacitaciones',
     'Damos capacitaciones sobre los riesgos del trabajo, primeros auxilios o qué hacer en una emergencia'),
    ('f480d733-fec9-5a2b-871e-0de38be5271d', '03b', 4, 'Pausas activas',
     'Hacemos pausas activas: unos minutos de estiramientos o ejercicios durante la jornada'),
    ('f480d733-fec9-5a2b-871e-0de38be5271d', '03b', 5, 'Revisión de equipos',
     'Revisamos y hacemos mantenimiento a máquinas, herramientas, vehículos e instalaciones eléctricas'),
    ('f480d733-fec9-5a2b-871e-0de38be5271d', '03b', 6, 'SG-SST',
     'Tenemos el SG-SST: identificamos los riesgos, seguimos un plan de trabajo anual y llevamos registros'),
    ('855e6321-4f50-5d2a-abc1-b4bd3fba0d5f', '03c', 1, 'Aprendizaje entre compañeros',
     'Las personas con más experiencia enseñan a las nuevas en el día a día'),
    ('855e6321-4f50-5d2a-abc1-b4bd3fba0d5f', '03c', 2, 'Inducción',
     'Quien llega recibe una inducción: le explicamos la empresa, sus funciones, las normas y los riesgos del puesto'),
    ('855e6321-4f50-5d2a-abc1-b4bd3fba0d5f', '03c', 3, 'Capacitaciones',
     'Organizamos o pagamos capacitaciones sobre temas del trabajo, como atención al cliente, manejo de máquinas o ventas'),
    ('855e6321-4f50-5d2a-abc1-b4bd3fba0d5f', '03c', 4, 'Cursos SENA',
     'Animamos al equipo a tomar cursos del SENA u otros cursos gratuitos y les damos tiempo para hacerlos'),
    ('855e6321-4f50-5d2a-abc1-b4bd3fba0d5f', '03c', 5, 'Seguimiento del jefe',
     'El jefe hace seguimiento para ver si lo aprendido se aplica y si el trabajo mejoró'),
    ('9666c433-5b8b-5223-bdce-65f1c0930e69', '04a', 1, 'Reducir consumos',
     'Queremos gastar menos agua, energía o combustible, por ejemplo cambiando bombillos o arreglando fugas'),
    ('9666c433-5b8b-5223-bdce-65f1c0930e69', '04a', 2, 'Manejar mejor los residuos',
     'Queremos manejar mejor los residuos: generar menos, separarlos y entregarlos a quien los aproveche'),
    ('9666c433-5b8b-5223-bdce-65f1c0930e69', '04a', 3, 'Cambiar materiales',
     'Cambiamos materiales o insumos por otros de menor impacto, como empaques reciclables o productos sin químicos fuertes'),
    ('9666c433-5b8b-5223-bdce-65f1c0930e69', '04a', 4, 'Cumplir un requisito de un cliente',
     'Lo hacemos porque un cliente, un comprador o una certificación nos lo pide'),
    ('7a8ee1fc-3157-59f8-bbbf-a615c93462b4', '04b', 1, 'Apagar equipos',
     'Apagamos luces, computadores y máquinas cuando no se están usando'),
    ('7a8ee1fc-3157-59f8-bbbf-a615c93462b4', '04b', 2, 'Ahorro de agua',
     'Ahorramos agua: arreglamos fugas, usamos llaves ahorradoras o recogemos agua lluvia'),
    ('7a8ee1fc-3157-59f8-bbbf-a615c93462b4', '04b', 3, 'Reutilizar',
     'Reutilizamos materiales, cajas, estibas o retales antes de botarlos'),
    ('7a8ee1fc-3157-59f8-bbbf-a615c93462b4', '04b', 4, 'Separar y reciclar',
     'Separamos los residuos en aprovechables, orgánicos y no aprovechables, y entregamos lo reciclable'),
    ('7a8ee1fc-3157-59f8-bbbf-a615c93462b4', '04b', 5, 'Entregar a gestor autorizado',
     'Entregamos aceites, baterías, químicos u otros residuos peligrosos a un gestor autorizado'),
    ('2bc5922a-8cf6-5f3c-b2d4-59f21ef89829', '04c', 1, 'Revisan recibos de servicios',
     'Revisamos cada mes los recibos de agua, luz o gas para ver si el consumo baja'),
    ('2bc5922a-8cf6-5f3c-b2d4-59f21ef89829', '04c', 2, 'Pesan o cuentan residuos',
     'Pesamos o contamos los residuos que entregamos para reciclar o desechar'),
    ('2bc5922a-8cf6-5f3c-b2d4-59f21ef89829', '04c', 3, 'Observan cambios',
     'Observamos cambios en el lugar de trabajo, como menos basura, menos desperdicio o menos olores'),
    ('2bc5922a-8cf6-5f3c-b2d4-59f21ef89829', '04c', 4, 'Llevan un registro',
     'Llevamos un registro en un cuaderno, una hoja de cálculo o un tablero con los consumos y los avances'),
    ('69a07638-cd5e-58e4-ae92-3a5181868700', '05a', 1, 'Reglas claras para compras y pagos',
     'Tenemos reglas claras para comprar y pagar: pedir cotizaciones, exigir factura y guardar el soporte de cada pago'),
    ('69a07638-cd5e-58e4-ae92-3a5181868700', '05a', 2, 'La gerencia revisa y aprueba los pagos',
     'La gerencia revisa y aprueba los pagos antes de hacerlos'),
    ('69a07638-cd5e-58e4-ae92-3a5181868700', '05a', 3, 'Dos personas aprueban gastos importantes',
     'Los gastos grandes los aprueban dos personas, no una sola'),
    ('69a07638-cd5e-58e4-ae92-3a5181868700', '05a', 4, 'No se aceptan regalos o favores de proveedores',
     'No aceptamos regalos, comisiones o favores de proveedores o clientes a cambio de preferirlos'),
    ('69a07638-cd5e-58e4-ae92-3a5181868700', '05a', 5, 'Se habla del tema con el equipo',
     'Hablamos con el equipo sobre qué hacer ante un soborno, un regalo o un conflicto de interés'),
    ('69a07638-cd5e-58e4-ae92-3a5181868700', '05a', 6, 'Código de conducta o política escrita',
     'Tenemos un código de conducta o una política escrita de ética y transparencia que el equipo conoce'),
    ('c20bc5d5-3f1b-52ca-a2af-130321d16997', '05b', 1, 'Que sean locales',
     'Preferimos proveedores locales, del mismo municipio o de la región'),
    ('c20bc5d5-3f1b-52ca-a2af-130321d16997', '05b', 2, 'Que estén formalizados',
     'Pedimos que estén formalizados: que tengan RUT, entreguen factura y paguen la seguridad social de su gente'),
    ('c20bc5d5-3f1b-52ca-a2af-130321d16997', '05b', 3, 'Que cuiden el ambiente',
     'Tenemos en cuenta que cuiden el ambiente, por ejemplo que manejen bien sus residuos o tengan sus permisos ambientales'),
    ('c20bc5d5-3f1b-52ca-a2af-130321d16997', '05b', 4, 'Que traten bien a su gente',
     'Nos fijamos en que traten bien a su gente: pagos a tiempo, condiciones dignas y nada de trabajo infantil'),
    ('c20bc5d5-3f1b-52ca-a2af-130321d16997', '05b', 5, 'Relación de confianza',
     'Trabajamos con proveedores de confianza, con quienes llevamos años y cumplimos acuerdos de lado y lado'),
    ('62c99768-6d13-5fe8-81c6-afe2e321a65f', '05c', 1, 'Precios y ofertas claras',
     'Nuestros precios, ofertas y publicidad son claros, completos y se pueden cumplir'),
    ('62c99768-6d13-5fe8-81c6-afe2e321a65f', '05c', 2, 'Trámites al día',
     'Tenemos al día los trámites: registro mercantil, impuestos, permisos y licencias'),
    ('62c99768-6d13-5fe8-81c6-afe2e321a65f', '05c', 3, 'Revisión de la gerencia',
     'La gerencia revisa de vez en cuando que se cumplan los acuerdos con clientes, competidores y entidades'),
    ('62c99768-6d13-5fe8-81c6-afe2e321a65f', '05c', 4, 'Asesoría contable o jurídica',
     'Un contador o un abogado nos asesora y revisa que cumplamos nuestras obligaciones'),
    ('99ba63e2-1658-5e77-985a-ae04aaf98e01', '06a', 1, 'Etiquetas o fichas claras',
     'Nuestros productos tienen etiquetas o fichas claras con ingredientes, precio, fecha de vencimiento y forma de uso'),
    ('99ba63e2-1658-5e77-985a-ae04aaf98e01', '06a', 2, 'Garantías',
     'Damos garantía: si el producto o el servicio sale mal, lo arreglamos, lo cambiamos o devolvemos el dinero'),
    ('99ba63e2-1658-5e77-985a-ae04aaf98e01', '06a', 3, 'Controles de calidad',
     'Revisamos la calidad antes de entregar, por ejemplo con una lista de chequeo o una prueba del producto'),
    ('99ba63e2-1658-5e77-985a-ae04aaf98e01', '06a', 4, 'Explicación directa',
     'Le explicamos directamente al cliente cómo usar el producto, sus riesgos y sus condiciones'),
    ('df9f7d32-74c8-5261-b1ac-6ed5e7f3cd8e', '06b', 1, 'Acceso restringido',
     'Solo algunas personas de la empresa pueden ver o usar los datos de los clientes'),
    ('df9f7d32-74c8-5261-b1ac-6ed5e7f3cd8e', '06b', 2, 'Piden autorización',
     'Pedimos autorización al cliente antes de guardar o usar sus datos, por ejemplo para enviarle publicidad'),
    ('df9f7d32-74c8-5261-b1ac-6ed5e7f3cd8e', '06b', 3, 'Contraseñas',
     'Protegemos con contraseña los computadores, celulares y archivos donde están los datos'),
    ('df9f7d32-74c8-5261-b1ac-6ed5e7f3cd8e', '06b', 4, 'Política de datos',
     'Tenemos una política de tratamiento de datos personales publicada o disponible para los clientes'),
    ('4ffa8999-4559-5e99-914a-8ab21a4df56e', '06c', 1, 'Atención directa',
     'Atendemos las quejas en persona, en el local o en el lugar donde prestamos el servicio'),
    ('4ffa8999-4559-5e99-914a-8ab21a4df56e', '06c', 2, 'WhatsApp o redes',
     'Recibimos quejas y sugerencias por WhatsApp o redes sociales y las respondemos'),
    ('4ffa8999-4559-5e99-914a-8ab21a4df56e', '06c', 3, 'Correo',
     'Tenemos un correo electrónico para recibir quejas y reclamos'),
    ('4ffa8999-4559-5e99-914a-8ab21a4df56e', '06c', 4, 'Formato o registro',
     'Anotamos cada queja en un formato o registro con la fecha, el caso y la respuesta dada'),
    ('4ffa8999-4559-5e99-914a-8ab21a4df56e', '06c', 5, 'Seguimiento de tiempos',
     'Medimos cuánto nos demoramos en responder y tratamos de cumplir un plazo fijo'),
    ('1ab204e4-11fa-5eb6-b282-f557b826b6e6', '07a', 1, 'Participa en actividades del barrio o municipio',
     'Participamos en actividades del barrio o del municipio, como ferias, fiestas, jornadas de limpieza o reuniones comunitarias'),
    ('1ab204e4-11fa-5eb6-b282-f557b826b6e6', '07a', 2, 'Apoya iniciativas',
     'Apoyamos iniciativas de la comunidad, como un equipo deportivo, un grupo de mujeres o un proyecto de la escuela'),
    ('1ab204e4-11fa-5eb6-b282-f557b826b6e6', '07a', 3, 'Conversa con vecinos, líderes u organizaciones',
     'Conversamos con vecinos, líderes, la junta de acción comunal u otras organizaciones de la zona'),
    ('1ab204e4-11fa-5eb6-b282-f557b826b6e6', '07a', 4, 'Contrata personas de la zona',
     'Contratamos a personas que viven en la zona donde operamos'),
    ('599eb261-b389-5b01-969a-64183beb3f25', '07b', 1, 'Donaciones',
     'Donamos dinero, productos o servicios a personas u organizaciones que lo necesitan'),
    ('599eb261-b389-5b01-969a-64183beb3f25', '07b', 2, 'Patrocinios',
     'Patrocinamos eventos, equipos o actividades, y a cambio aparece el nombre de la empresa'),
    ('599eb261-b389-5b01-969a-64183beb3f25', '07b', 3, 'Empleo local',
     'Damos prioridad a personas de la comunidad cuando abrimos vacantes'),
    ('599eb261-b389-5b01-969a-64183beb3f25', '07b', 4, 'Voluntariado',
     'Las personas de la empresa donan su tiempo a una causa, por ejemplo en jornadas de siembra o de refuerzo escolar'),
    ('85ab9b07-b240-5e95-9242-22b55a1f9621', '07c', 1, 'Comentarios de la comunidad',
     'La comunidad nos comenta o nos agradece los cambios que ha notado'),
    ('85ab9b07-b240-5e95-9242-22b55a1f9621', '07c', 2, 'Fotos o registros',
     'Guardamos fotos, listas de asistencia o actas de las actividades'),
    ('85ab9b07-b240-5e95-9242-22b55a1f9621', '07c', 3, 'Número de personas beneficiadas',
     'Contamos cuántas personas se beneficiaron con cada apoyo'),
    ('85ab9b07-b240-5e95-9242-22b55a1f9621', '07c', 4, 'Relación con vecinos',
     'Notamos que la relación con los vecinos mejoró: menos quejas, más confianza o trabajo conjunto');

-- Catálogo.
UPDATE nexus360.pregunta p
   SET ejemplos = n.ejemplos
  FROM (SELECT pregunta_id, array_agg(texto ORDER BY orden) AS ejemplos
          FROM _ejemplo_nuevo GROUP BY pregunta_id) n
 WHERE p.pregunta_id = n.pregunta_id
   AND p.ejemplos IS DISTINCT FROM n.ejemplos;

-- Respuestas guardadas. respuesta tiene FORCE ROW LEVEL SECURITY: sin una
-- sesión de usuario ni el dueño ve filas. Se levanta el FORCE solo dentro
-- de esta transacción, como en 009.
ALTER TABLE nexus360.respuesta NO FORCE ROW LEVEL SECURITY;

-- Cada ejemplo con el texto anterior se cambia por el nuevo, en el mismo
-- orden y sin repetidos. Lo que no reconoce lo deja igual.
UPDATE nexus360.respuesta r
   SET ejemplos = (
        SELECT coalesce(array_agg(t.valor ORDER BY t.primera), '{}'::TEXT[])
          FROM (SELECT coalesce(n.texto, u.ejemplo) AS valor, min(u.orden) AS primera
                  FROM unnest(r.ejemplos) WITH ORDINALITY AS u(ejemplo, orden)
                  LEFT JOIN _ejemplo_nuevo n
                         ON n.pregunta_id = r.pregunta_id AND n.antes = u.ejemplo
                 GROUP BY 1) t
       )
 WHERE EXISTS (SELECT 1 FROM _ejemplo_nuevo n
                WHERE n.pregunta_id = r.pregunta_id AND n.antes = ANY (r.ejemplos));

ALTER TABLE nexus360.respuesta FORCE ROW LEVEL SECURITY;

DO $resumen$
DECLARE
    v_pendientes INT;
BEGIN
    SELECT count(*) INTO v_pendientes
      FROM nexus360.pregunta p JOIN _ejemplo_nuevo n ON n.pregunta_id = p.pregunta_id
     WHERE NOT (n.texto = ANY (p.ejemplos));
    IF v_pendientes > 0 THEN
        RAISE EXCEPTION '012: % ejemplos del catálogo no quedaron actualizados', v_pendientes;
    END IF;
    RAISE NOTICE '012: T5 dividida en T5a y T5b (columna vecinos) y ejemplos descriptivos aplicados.';
END
$resumen$;

COMMIT;
