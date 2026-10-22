"""Base de conocimiento del asistente de NEXUS 360° (chatbot de la empresa).

ARCHIVO GENERADO por el frontend (scripts/generar-conocimiento-asistente.mjs)
a partir de src/data/tamizaje.ts, escala.ts, rseExpress.ts y glosario.ts:
no se edita a mano. Si cambia una pregunta, una opción o una ayuda, se vuelve
a generar y se sube VERSION_ASISTENTE en app/ia/asistente.py.

No incluye lo que es de uso interno de NEXUS (propósito de cada pregunta,
arquetipos, pesos, lectura numérica 0–4 ni alternativas de la matriz).
"""

# Número → nombre de cada materia: valida el contexto de pantalla que manda el front.
MATERIAS = {
    "01": "Gobernanza organizacional",
    "02": "Derechos humanos",
    "03": "Prácticas laborales",
    "04": "Medio ambiente",
    "05": "Prácticas justas de operación",
    "06": "Consumidores",
    "07": "Comunidad y territorio",
}

CONOCIMIENTO = """\
# NEXUS 360° y el Autodiagnóstico RSE Express
NEXUS 360° es una plataforma para empresas en Colombia (micro, pequeñas y medianas). El Autodiagnóstico RSE Express recorre las siete materias de la ISO 26000 con preguntas abiertas y en lenguaje sencillo. Toma unos 30 a 40 minutos.
Es un autodiagnóstico, no una auditoría: no verifica cumplimiento legal ni constituye concepto jurídico. A la empresa no se le muestra un puntaje: recibe un mapa de prácticas, sus fortalezas, temas por empezar o formalizar y una matriz para priorizar un reto.
Las respuestas se guardan solas a medida que se avanza; se puede salir y retomar después, y otra persona del equipo puede continuar con la misma cuenta.
La ISO 26000 es una guía de aplicación voluntaria, no una norma certificable.
El recorrido tiene cuatro pasos: 1) Perfil, 2) Tamizaje «Conozcamos su empresa», 3) Autodiagnóstico y 4) Resultados. Para pasar al siguiente paso hay que completar el anterior.
Cuando el perfil y el tamizaje ya están completos, esos datos se cambian desde el menú de la cuenta → Configuración («Datos y tamizaje»); el cambio queda en el historial.

# Paso 1 · Perfil (datos básicos de la empresa)
Pide: razón social; NIT y dígito de verificación (DV), que aparece en el RUT (el NIT debe tener al menos 5 dígitos); sector (ayuda a leer las respuestas según la actividad de la empresa); departamento y municipio; y si es una sociedad extranjera constituida en Colombia.
Sectores: Industrial, Servicios, Agroindustrial, Comercio, Energía / Combustibles, Movilidad.

# Paso 2 · Tamizaje «Conozcamos su empresa»
Cinco preguntas para conocer la realidad de la empresa. No pide documentos ni cifras exactas. Son obligatorias T1 (tamaño), T2 (número de personas y cómo están vinculadas), T5a (al menos un lugar o el texto), T5b (al menos una opción o el texto) y T6 (tipo de clientes). El rango de ingresos y los detalles en texto son opcionales.
- T1. ¿Cómo describiría el tamaño de su empresa? Opciones:
  - «Micro»: Negocio pequeño. Como referencia, suele tener hasta 10 personas trabajando.
  - «Pequeña»: Como referencia, suele tener entre 11 y 50 personas trabajando.
  - «Mediana»: Como referencia, suele tener entre 51 y 200 personas trabajando.
  - «No estoy seguro»: Elíjala si no conoce la clasificación oficial de su empresa. No hay problema: el tamaño solo se usa como referencia.
- T1 (opcional). Rango de ingresos anuales, si lo conoce. Opciones: «Menos de $1.000 millones», «Entre $1.000 y $10.000 millones», «Entre $10.000 y $50.000 millones», «Más de $50.000 millones», «Prefiero no indicarlo».
- T2. ¿Cuántas personas trabajan hoy con la empresa y cómo están vinculadas? Se escribe el número de personas (un número entero mayor que cero) y se marcan todas las formas de vinculación que apliquen:
  - «Contrato laboral»: La persona es empleada de la empresa: tiene salario, horario, prestaciones sociales y afiliación a salud, pensión y ARL. Puede ser a término fijo o indefinido.
  - «Prestación de servicios»: La persona trabaja de forma independiente: cobra honorarios por una tarea o un resultado, sin horario fijo, y paga su propia seguridad social.
  - «Socios o familiares que trabajan»: Dueños, socios o parientes que trabajan en la empresa, tengan o no un contrato o un pago fijo.
  - «Personal por temporada»: Personas que se contratan solo en ciertas épocas, como la cosecha, diciembre o una obra, y luego terminan su vínculo.
  - «Otra forma»: Por ejemplo, aprendices del SENA, practicantes, personal de una empresa de servicios temporales o de una cooperativa. Puede contarlo en el campo de abajo.
- T5a. ¿En qué lugares desarrolla su actividad? Se marcan todos los que apliquen y se puede escribir el detalle:
  - «Barrios»: Sectores dentro del casco urbano de una ciudad o un pueblo, donde hay calles, casas y comercio.
  - «Centro o zona comercial»: Sector con muchos locales, oficinas y comercio, como el centro de la ciudad, una plaza de mercado o un centro comercial.
  - «Zona industrial o de bodegas»: Sector destinado a fábricas, talleres, bodegas o parques industriales, por lo general separado de las viviendas.
  - «Veredas»: División del área rural de un municipio. Agrupa fincas y casas del campo, fuera del casco urbano, y cada una tiene su propio nombre.
  - «Zonas rurales»: Áreas de campo fuera del casco urbano, como fincas, cultivos, bosques o corregimientos. Si conoce el nombre de la vereda, marque también «Veredas».
  - «Otros lugares»: Por ejemplo, varios municipios, rutas de transporte, ventas por internet o trabajos en el sitio de sus clientes. Puede escribirlo en el campo de abajo.
- T5b. ¿Qué comunidades o vecinos están cerca de su operación? Se marcan todos los que apliquen y se puede escribir el detalle. «No hay comunidades ni vecinos cerca» desmarca las demás opciones de esta pregunta:
  - «Viviendas o familias vecinas»: Casas, edificios o conjuntos residenciales cerca de su sede, planta, local o finca. Pueden notar el ruido, los olores, el polvo o el tránsito de la operación.
  - «Escuelas, centros de salud o iglesias»: Lugares donde se reúnen niños, estudiantes, pacientes o fieles. Son especialmente sensibles al ruido, al tránsito de vehículos y a los residuos.
  - «Fincas o familias campesinas»: Familias que viven y trabajan en el campo, con cultivos o animales, cerca de su operación. Pueden compartir con usted el agua, los caminos o el aire.
  - «Otros negocios o empresas»: Tiendas, talleres, fábricas, restaurantes o cultivos de otras empresas que comparten la zona con usted.
  - «Comunidades indígenas»: Pueblos originarios con su propia cultura, lengua y autoridades, que pueden vivir en resguardos o estar organizados en cabildos. Tienen derechos especiales sobre su territorio, como la consulta previa.
  - «Comunidades afrodescendientes»: Comunidades negras, afrocolombianas, raizales o palenqueras. Muchas se organizan en consejos comunitarios y tienen territorios colectivos protegidos por la ley.
  - «Otros vecinos»: Por ejemplo, una junta de acción comunal, una asociación de productores u otra organización de la zona. Puede escribirlo en el campo de abajo.
  - «No hay comunidades ni vecinos cerca»: Elíjala si su operación está aislada y nadie vive o trabaja cerca. Si marca otra opción de esta pregunta, esta se desmarca sola.
- T6. ¿Quiénes son principalmente sus clientes? Opciones:
  - «Personas u hogares»: Le vende directamente a la gente para su uso personal o familiar (consumidor final), como una tienda, un restaurante o un taller de barrio.
  - «Otras empresas»: Le vende a negocios que usan su producto o servicio para trabajar o para revender. Con esta opción no le haremos las preguntas de la materia Consumidores.
  - «Entidades públicas»: Le vende al Estado: alcaldías, gobernaciones, hospitales o colegios oficiales u otras entidades, por lo general mediante contratos.
  - «Una mezcla»: Le vende tanto a personas u hogares como a empresas o entidades públicas.
- Si la empresa le vende solo a «Otras empresas» o a «Entidades públicas», la materia 06 «Consumidores» no se pregunta ni cuenta en los resultados.

# Paso 3 · Autodiagnóstico RSE Express
Se entra por la portada del autodiagnóstico, que muestra el avance de cada materia. Se puede abrir cualquier materia, responder en el orden que se quiera y usar «Guardar y volver» para regresar a la portada.
Cómo se responde cada pregunta:
- «Cuéntenos con sus palabras»: respuesta abierta sobre lo que la empresa hace hoy. No hay respuestas correctas ni incorrectas; sirve contar ejemplos concretos (qué hacen, quién lo hace, cada cuánto).
- Ejemplos orientadores (opcionales, se marcan los que apliquen): ayudan a recordar. Si un ejemplo no describe a la empresa, no se marca.
- «Hacemos algo diferente: ___»: para contar una práctica propia que no aparece en los ejemplos.
- «¿En qué punto está?»: una sola opción. Opciones:
  - «Aún no lo hemos abordado»: Todavía no hacen nada en este tema. No es algo malo: es el punto de partida y nos ayuda a encontrar oportunidades.
  - «Estamos comenzando / Lo hacemos de manera informal»: Hacen algo, pero de vez en cuando, cuando surge la necesidad o según quien esté. Todavía no hay acuerdos claros sobre cómo hacerlo.
  - «Lo tenemos organizado: hay acuerdos y alguien a cargo, esté o no por escrito»: Ya está claro qué se hace, quién lo hace y cada cuánto, y se hace con regularidad. No importa si está escrito o no.
  - «Lo aplicamos y vemos resultados»: Lo hacen de forma constante y pueden contar qué cambió gracias a eso: por ejemplo, menos accidentes, menos consumo o clientes más satisfechos.
  - «Lo revisamos y mejoramos con lo aprendido»: Además de aplicarlo, cada cierto tiempo revisan cómo va y hacen ajustes con lo que aprenden.
  - «Hacemos algo diferente»: Lo que hacen no encaja en las opciones anteriores. Cuéntenos con sus palabras qué hacen y el equipo NEXUS lo ubicará. Cuéntenos qué hacen: el equipo NEXUS lo ubicará a partir de su respuesta.
  - «No aplica a nuestra empresa»: El tema no tiene que ver con su empresa; por ejemplo, si no guarda datos de clientes. Sale del análisis: no cuenta como un cero. Sale del análisis: no cuenta como un cero.
- Una pregunta queda completa con la etapa elegida y algo de lo que hacen (texto, un ejemplo marcado o «Hacemos algo diferente»), salvo que la etapa sea «Aún no lo hemos abordado» o «No aplica a nuestra empresa», que no necesitan texto.
- «Hacemos algo diferente» y «No aplica a nuestra empresa» también son respuestas válidas.
- Al final de cada materia hay una pregunta abierta sobre lo que la empresa quiere fortalecer o empezar a hacer en ese tema. Lo que se escriba ahí sugiere el «interés» en la matriz de priorización.
- Para terminar hay una pregunta final: «¿Hay algo que haga la empresa por sus trabajadores, clientes, el ambiente o la comunidad que no le hayamos preguntado?»
- Cuando todas las preguntas están completas aparece «Ver mi mapa de resultados».

## Materias y preguntas
### 01 · Gobernanza organizacional
Cómo se toman las decisiones en la empresa y quién impulsa lo que hace por sus trabajadores, clientes, el ambiente y la comunidad.
- Pregunta 01a: Más allá de su actividad comercial, ¿qué hace hoy la empresa por sus trabajadores, clientes, el ambiente o la comunidad, y quién impulsa esas acciones?
  Ejemplos orientadores: «El dueño o la gerencia decide qué acciones hacer, por ejemplo apoyar a un trabajador en una calamidad o donar a una causa»; «Los socios conversan y se ponen de acuerdo sobre qué hacer por el equipo, los clientes, el ambiente o la comunidad»; «Cuidar a las personas y al entorno hace parte de los valores de la empresa y se nota en cómo trabajamos»; «Tenemos una política escrita de responsabilidad social, aprobada por la dirección y conocida por el equipo».
- Pregunta 01b: ¿Quién se encarga de estas acciones y cómo consiguen el tiempo y los recursos para hacerlas?
  Ejemplos orientadores: «El gerente o el dueño se encarga personalmente, además de sus otras tareas»; «Una persona del equipo tiene a su cargo estas acciones y dedica algunas horas a organizarlas»; «Se hacen con el dinero o el tiempo que haya disponible en el momento, sin un presupuesto fijo»; «Cada año separamos un monto de dinero o un tiempo fijo para estas acciones dentro del presupuesto».
- Pregunta 01c: ¿Cómo le cuenta la empresa a sus trabajadores, clientes, socios o comunidad lo que hace en estos temas?
  Ejemplos orientadores: «Lo contamos en conversaciones del día a día con el equipo, los clientes o los vecinos»; «Lo compartimos en reuniones con el equipo, los socios o la comunidad»; «Publicamos fotos y noticias de lo que hacemos en redes sociales o en WhatsApp»; «Lo ponemos en carteleras o avisos visibles dentro de la empresa»; «Preparamos un informe o balance, por ejemplo cada año, con lo que hicimos y los resultados».
- Cierre de la materia: ¿Qué le gustaría fortalecer o empezar a hacer en este tema?
### 02 · Derechos humanos
El trato respetuoso y digno a las personas con las que se relaciona la empresa: equipo, proveedores, clientes y vecinos.
- Pregunta 02a: ¿Cómo se asegura la empresa de que las personas con las que se relaciona (equipo, proveedores, clientes, vecinos) sean tratadas con respeto y dignidad?
  Ejemplos orientadores: «Exigimos un trato amable y respetuoso entre compañeros, jefes, clientes y proveedores, sin gritos, burlas ni humillaciones»; «No tratamos distinto a nadie por su género, edad, origen, color de piel, religión, discapacidad u orientación sexual»; «No contratamos a menores de 18 años y no permitimos que niños, niñas o adolescentes trabajen en la empresa»; «Abrimos oportunidades de trabajo a personas con discapacidad, víctimas del conflicto, migrantes, mayores de 50 años o jóvenes sin experiencia»; «Tenemos reglas de convivencia acordadas, por ejemplo cómo resolver un conflicto o qué hacer ante un caso de acoso».
- Pregunta 02b: ¿Han identificado situaciones, en la empresa o con sus proveedores, que puedan afectar a las personas? ¿Qué hacen cuando las detectan?
  Ejemplos orientadores: «Condiciones inseguras, como máquinas sin protección, pisos resbalosos, cables sueltos o trabajo en alturas sin equipo»; «Jornadas excesivas, como turnos muy largos, horas extra sin pago o semanas sin día de descanso»; «Trabajo infantil: niños, niñas o adolescentes trabajando en la empresa o en la de un proveedor»; «Discriminación o acoso: tratar peor a alguien por quién es, o burlas, presiones o maltratos repetidos».
- Pregunta 02c: Si una persona o un vecino se siente afectado por la empresa, ¿cómo se entera la empresa y qué hace para responder?
  Ejemplos orientadores: «La persona habla directamente con el dueño o el gerente, que la escucha y busca una solución»; «Tenemos una línea telefónica o un WhatsApp donde cualquier persona puede contar su inquietud»; «Hay un buzón, físico o en internet, para dejar quejas o sugerencias, incluso sin dar el nombre»; «Hacemos reuniones con el equipo o con los vecinos para escuchar inquietudes y acordar soluciones»; «Tenemos un procedimiento escrito que dice quién recibe la queja, en cuánto tiempo se responde y cómo se hace seguimiento».
- Cierre de la materia: ¿Qué le gustaría fortalecer o empezar a hacer en este tema?
### 03 · Prácticas laborales
Las condiciones de trabajo, el diálogo con el equipo, la seguridad y la salud, y el aprendizaje de las personas.
- Pregunta 03a: ¿Cómo acuerda la empresa las condiciones de trabajo con su equipo y cómo conversa con ellos sobre lo que funciona y lo que se puede mejorar?
  Ejemplos orientadores: «Cada persona tiene un contrato escrito con su salario, horario, funciones y tipo de vinculación»; «Tenemos un reglamento interno de trabajo que explica horarios, permisos, descansos y faltas»; «Hacemos reuniones periódicas, semanales o mensuales, para hablar con el equipo de lo que funciona y lo que se puede mejorar»; «Las personas pueden hablar directamente con la gerencia cuando tienen una propuesta o un problema»; «Tenemos un grupo de chat del equipo donde también se comentan propuestas e inquietudes»; «Hay un buzón de sugerencias para el equipo, en papel o en internet»; «Funciona un comité con trabajadores, como el de convivencia laboral o el COPASST, que se reúne y deja actas».
- Pregunta 03b: ¿Qué hace la empresa para cuidar la seguridad y la salud de las personas mientras trabajan?
  Ejemplos orientadores: «Todas las personas que trabajan con la empresa están afiliadas a una ARL desde el primer día»; «Entregamos y reponemos elementos de protección (casco, guantes, gafas, tapabocas, botas) y revisamos que se usen»; «Damos capacitaciones sobre los riesgos del trabajo, primeros auxilios o qué hacer en una emergencia»; «Hacemos pausas activas: unos minutos de estiramientos o ejercicios durante la jornada»; «Revisamos y hacemos mantenimiento a máquinas, herramientas, vehículos e instalaciones eléctricas»; «Tenemos el SG-SST: identificamos los riesgos, seguimos un plan de trabajo anual y llevamos registros».
- Pregunta 03c: ¿Cómo aprende y crece el equipo en la empresa y cómo se dan cuenta de que eso sirve en el trabajo diario?
  Ejemplos orientadores: «Las personas con más experiencia enseñan a las nuevas en el día a día»; «Quien llega recibe una inducción: le explicamos la empresa, sus funciones, las normas y los riesgos del puesto»; «Organizamos o pagamos capacitaciones sobre temas del trabajo, como atención al cliente, manejo de máquinas o ventas»; «Animamos al equipo a tomar cursos del SENA u otros cursos gratuitos y les damos tiempo para hacerlos»; «El jefe hace seguimiento para ver si lo aprendido se aplica y si el trabajo mejoró».
- Cierre de la materia: ¿Qué le gustaría fortalecer o empezar a hacer en este tema?
### 04 · Medio ambiente
El uso del agua, la energía y los materiales, el manejo de los residuos y lo que la empresa hace por cuidar el entorno.
- Pregunta 04a: ¿Qué cuidados o acciones ambientales tiene hoy la empresa, aunque no estén escritos, y hay algo concreto que quieran lograr?
  Ejemplos orientadores: «Queremos gastar menos agua, energía o combustible, por ejemplo cambiando bombillos o arreglando fugas»; «Queremos manejar mejor los residuos: generar menos, separarlos y entregarlos a quien los aproveche»; «Cambiamos materiales o insumos por otros de menor impacto, como empaques reciclables o productos sin químicos fuertes»; «Lo hacemos porque un cliente, un comprador o una certificación nos lo pide».
- Pregunta 04b: En el día a día, ¿qué hacen para usar mejor el agua, la energía y los materiales, y qué pasa con los residuos que generan?
  Ejemplos orientadores: «Apagamos luces, computadores y máquinas cuando no se están usando»; «Ahorramos agua: arreglamos fugas, usamos llaves ahorradoras o recogemos agua lluvia»; «Reutilizamos materiales, cajas, estibas o retales antes de botarlos»; «Separamos los residuos en aprovechables, orgánicos y no aprovechables, y entregamos lo reciclable»; «Entregamos aceites, baterías, químicos u otros residuos peligrosos a un gestor autorizado».
- Pregunta 04c: ¿Cómo se dan cuenta si esas acciones están funcionando y han cambiado algo a partir de eso?
  Ejemplos orientadores: «Revisamos cada mes los recibos de agua, luz o gas para ver si el consumo baja»; «Pesamos o contamos los residuos que entregamos para reciclar o desechar»; «Observamos cambios en el lugar de trabajo, como menos basura, menos desperdicio o menos olores»; «Llevamos un registro en un cuaderno, una hoja de cálculo o un tablero con los consumos y los avances».
- Cierre de la materia: ¿Qué le gustaría fortalecer o empezar a hacer en este tema?
### 05 · Prácticas justas de operación
La transparencia y la honestidad en las relaciones con clientes, proveedores, competidores y entidades públicas.
- Pregunta 05a: Cuéntenos cómo aborda actualmente la empresa la prevención de situaciones de corrupción, conflictos de interés o prácticas que puedan afectar la transparencia de sus operaciones.
  Ejemplos orientadores: «Tenemos reglas claras para comprar y pagar: pedir cotizaciones, exigir factura y guardar el soporte de cada pago»; «La gerencia revisa y aprueba los pagos antes de hacerlos»; «Los gastos grandes los aprueban dos personas, no una sola»; «No aceptamos regalos, comisiones o favores de proveedores o clientes a cambio de preferirlos»; «Hablamos con el equipo sobre qué hacer ante un soborno, un regalo o un conflicto de interés»; «Tenemos un código de conducta o una política escrita de ética y transparencia que el equipo conoce».
- Pregunta 05b: Además del precio y la calidad, ¿qué tiene en cuenta la empresa al escoger a sus proveedores?
  Ejemplos orientadores: «Preferimos proveedores locales, del mismo municipio o de la región»; «Pedimos que estén formalizados: que tengan RUT, entreguen factura y paguen la seguridad social de su gente»; «Tenemos en cuenta que cuiden el ambiente, por ejemplo que manejen bien sus residuos o tengan sus permisos ambientales»; «Nos fijamos en que traten bien a su gente: pagos a tiempo, condiciones dignas y nada de trabajo infantil»; «Trabajamos con proveedores de confianza, con quienes llevamos años y cumplimos acuerdos de lado y lado».
- Pregunta 05c: ¿Cómo procura la empresa competir de manera honesta y tener una relación transparente con clientes, competidores y entidades públicas? ¿Hacen algo para revisar que esto se cumpla?
  Ejemplos orientadores: «Nuestros precios, ofertas y publicidad son claros, completos y se pueden cumplir»; «Tenemos al día los trámites: registro mercantil, impuestos, permisos y licencias»; «La gerencia revisa de vez en cuando que se cumplan los acuerdos con clientes, competidores y entidades»; «Un contador o un abogado nos asesora y revisa que cumplamos nuestras obligaciones».
- Cierre de la materia: ¿Qué le gustaría fortalecer o empezar a hacer para que sus relaciones con clientes, proveedores, competidores y entidades sean más transparentes?
### 06 · Consumidores (solo aplica si la empresa le vende a personas u hogares, o a una mezcla)
La información clara, la calidad y la seguridad de lo que se vende, el cuidado de los datos personales y la atención a los clientes. Solo aplica si vende a consumidor final.
- Pregunta 06a: ¿Cómo se asegura la empresa de que sus clientes reciban información clara y productos o servicios de calidad y seguros?
  Ejemplos orientadores: «Nuestros productos tienen etiquetas o fichas claras con ingredientes, precio, fecha de vencimiento y forma de uso»; «Damos garantía: si el producto o el servicio sale mal, lo arreglamos, lo cambiamos o devolvemos el dinero»; «Revisamos la calidad antes de entregar, por ejemplo con una lista de chequeo o una prueba del producto»; «Le explicamos directamente al cliente cómo usar el producto, sus riesgos y sus condiciones».
- Pregunta 06b: ¿Qué información personal de sus clientes maneja la empresa (nombres, teléfonos, correos) y cómo la cuidan?
  Ejemplos orientadores: «Solo algunas personas de la empresa pueden ver o usar los datos de los clientes»; «Pedimos autorización al cliente antes de guardar o usar sus datos, por ejemplo para enviarle publicidad»; «Protegemos con contraseña los computadores, celulares y archivos donde están los datos»; «Tenemos una política de tratamiento de datos personales publicada o disponible para los clientes».
- Pregunta 06c: Cuando un cliente tiene una queja, sugerencia o reclamo, ¿cómo lo recibe la empresa y cómo le responde?
  Ejemplos orientadores: «Atendemos las quejas en persona, en el local o en el lugar donde prestamos el servicio»; «Recibimos quejas y sugerencias por WhatsApp o redes sociales y las respondemos»; «Tenemos un correo electrónico para recibir quejas y reclamos»; «Anotamos cada queja en un formato o registro con la fecha, el caso y la respuesta dada»; «Medimos cuánto nos demoramos en responder y tratamos de cumplir un plazo fijo».
- Cierre de la materia: ¿Qué le gustaría fortalecer o empezar a hacer en este tema?
### 07 · Comunidad y territorio
La relación de la empresa con el barrio, la vereda o el municipio donde opera, y los apoyos que da.
- Pregunta 07a: ¿Qué relación tiene la empresa con la comunidad o el sector donde opera?
  Ejemplos orientadores: «Participamos en actividades del barrio o del municipio, como ferias, fiestas, jornadas de limpieza o reuniones comunitarias»; «Apoyamos iniciativas de la comunidad, como un equipo deportivo, un grupo de mujeres o un proyecto de la escuela»; «Conversamos con vecinos, líderes, la junta de acción comunal u otras organizaciones de la zona»; «Contratamos a personas que viven en la zona donde operamos».
- Pregunta 07b: Cuando la empresa apoya a la comunidad (donaciones, patrocinios, empleo local, voluntariado), ¿cómo decide a quién y en qué apoyar?
  Ejemplos orientadores: «Donamos dinero, productos o servicios a personas u organizaciones que lo necesitan»; «Patrocinamos eventos, equipos o actividades, y a cambio aparece el nombre de la empresa»; «Damos prioridad a personas de la comunidad cuando abrimos vacantes»; «Las personas de la empresa donan su tiempo a una causa, por ejemplo en jornadas de siembra o de refuerzo escolar».
- Pregunta 07c: ¿Qué cambios han notado en la comunidad o en la empresa a partir de esos apoyos y cómo se dan cuenta?
  Ejemplos orientadores: «La comunidad nos comenta o nos agradece los cambios que ha notado»; «Guardamos fotos, listas de asistencia o actas de las actividades»; «Contamos cuántas personas se beneficiaron con cada apoyo»; «Notamos que la relación con los vecinos mejoró: menos quejas, más confianza o trabajo conjunto».
- Cierre de la materia: ¿Qué le gustaría fortalecer o empezar a hacer en este tema?

# Paso 4 · Resultados
- Mapa de prácticas: lo que la empresa ya hace en cada materia, con sus propias palabras, y su punto de partida por materia en una gráfica que es una referencia visual, no un puntaje.
- Categorías: «Fortaleza» (prácticas en «Lo aplicamos y vemos resultados» o «Lo revisamos y mejoramos con lo aprendido»), «En desarrollo» («Lo tenemos organizado»), «Oportunidad» («Aún no lo hemos abordado» o «Estamos comenzando / Lo hacemos de manera informal»), «Práctica propia» («Hacemos algo diferente»: el equipo NEXUS la revisa y la ubica) y «No aplica» (sale del análisis y no cuenta como un cero).
- Matriz de priorización: propone de 3 a 5 oportunidades, máximo una por materia; primero los temas con implicaciones legales que están en etapa inicial. Cada oportunidad trae un verbo según la etapa de partida: Empezar, Formalizar, Fortalecer o Ampliar. La empresa califica cada una de 1 (bajo) a 3 (alto) en cuatro criterios y elige la que quiere convertir en su reto. La suma orienta, pero no reemplaza su decisión; si hay empate, pesa más el interés de la empresa.
  - Importancia: ¿qué tan relevante es para la empresa y sus grupos de interés?
  - Viabilidad: ¿qué tan posible es hacerlo con los recursos actuales?
  - Potencial de mejora: ¿cuánto puede cambiar si se trabaja?
  - Interés de la empresa: ¿qué tanto quiere la empresa trabajar en esto? Se sugiere alto donde la empresa escribió qué quiere fortalecer.
- Cada oportunidad trae «Alternativas para conversar con NEXUS»: son ideas para la conversación, no recomendaciones validadas.
- Siguiente paso: con NEXUS, la oportunidad elegida se convierte en un reto («¿Cómo podríamos…?») y un microproyecto de 4 a 8 semanas, con un responsable y un indicador sencillo.
- Alertas informativas (no son sanciones): Ley 2173 si el tamaño es «Mediana» o «No estoy seguro»; Seguridad y Salud en el Trabajo (SG-SST) y protección de datos personales (Ley 1581 de 2012) si esas prácticas están en etapa inicial o marcadas como «No aplica»; comunidades étnicas si el tamizaje marca comunidades indígenas o afrodescendientes cerca.
- Análisis inteligente: una interpretación con IA (Gemini) de los resultados que ya calculó la plataforma. No cambia el mapa, las categorías ni el orden de la matriz.
- Informe en PDF: «Descargar informe (PDF)» con el mapa, las fortalezas, la matriz, las alertas y, si está listo, el análisis inteligente.
- Cada diagnóstico queda guardado en el espacio de la empresa para comparar el avance de un año al siguiente.

# Glosario
- rse: Responsabilidad Social Empresarial: la forma en que una empresa cuida a sus trabajadores, sus clientes, el ambiente y la comunidad mientras hace su negocio.
- ingresos anuales: Todo el dinero que la empresa recibe en un año por sus ventas o servicios, antes de descontar gastos e impuestos.
- vinculadas: El tipo de relación que tiene cada persona con la empresa: contrato laboral, prestación de servicios, socio o familiar, por temporada, entre otras.
- su operación: Los lugares donde la empresa produce, guarda, transporta o vende: su sede, planta, local, bodega, finca o punto de venta.
- actividad comercial: Lo que la empresa hace para ganar dinero: producir, vender o prestar sus servicios.
- recursos: Lo que se necesita para hacer algo: dinero, tiempo, personas, materiales o espacios.
- dignidad: El valor que tiene toda persona y que exige tratarla con respeto, sin humillaciones, abusos ni malos tratos.
- proveedores: Personas o empresas que le venden a su empresa los materiales, productos o servicios que necesita para trabajar.
- condiciones de trabajo: Lo que se acuerda con cada persona: salario, horario, funciones, descansos, prestaciones y el lugar donde trabaja.
- acciones ambientales: Lo que hace la empresa para disminuir su impacto en la naturaleza: ahorrar agua y energía, manejar bien los residuos o evitar la contaminación.
- residuos: Lo que sobra o se desecha en la operación: empaques, papel, plástico, restos de comida o de materiales, aceites o chatarra.
- corrupción: Usar un cargo o una posición para obtener un beneficio indebido; por ejemplo, pagar o recibir un soborno para conseguir un contrato o agilizar un trámite.
- conflictos de interés: Cuando alguien de la empresa debe tomar una decisión en la que también gana él, un familiar o un amigo; por ejemplo, comprarle a la empresa de un primo.
- transparencia: Actuar de forma clara y abierta: que las decisiones, los pagos y los acuerdos se puedan explicar y revisar sin esconder nada.
- competir de manera honesta: Ganar clientes por la calidad, el servicio y el precio, sin engañar, sin desprestigiar a otros y sin ponerse de acuerdo con la competencia para fijar precios.
- entidades públicas: Organismos del Estado, como alcaldías, gobernaciones, ministerios, la DIAN u hospitales y colegios oficiales.
- información personal: Datos que identifican a una persona: nombre, cédula, teléfono, correo o dirección. En Colombia su manejo está protegido por la Ley 1581 de 2012.
- consumidor final: La persona que compra un producto o un servicio para usarlo ella misma o su familia, y no para revenderlo o usarlo en otro negocio.
- reclamo: Una queja expresa una inconformidad con la atención; un reclamo pide corregir un problema con lo que se compró, por ejemplo hacer válida una garantía.
- donaciones: Entregar dinero, productos o servicios sin esperar nada a cambio.
- patrocinios: Apoyo en dinero o en especie a un evento, un equipo o una actividad, a cambio de que aparezca el nombre de la empresa.
- empleo local: Contratar a personas que viven en el barrio, la vereda o el municipio donde opera la empresa.
- voluntariado: Cuando las personas de la empresa donan su tiempo o su conocimiento para apoyar una causa de la comunidad.
"""
