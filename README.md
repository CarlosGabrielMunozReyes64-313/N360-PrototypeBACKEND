# NEXUS 360° — Backend

API FastAPI que implementa `/api/auth/*` para el frontend NEXUS 360°, sobre
el esquema PostgreSQL `nexus360_schema.sql`. El backend **no reimplementa**
hashing de contraseñas ni lógica de bloqueo: llama directamente a las
funciones `SECURITY DEFINER` que ya trae el schema
(`registrar_usuario`, `iniciar_sesion`, `cerrar_sesion`, `validar_sesion`),
para no duplicar (y potencialmente romper) esa seguridad.

## Estructura

```
app/
  main.py        # app FastAPI, CORS, manejo de errores, lifespan del pool
  config.py       # settings desde variables de entorno / .env
  db.py           # pool asyncpg + helper para RLS (app.current_usuario_id)
  security.py     # extracción del Bearer token
  schemas.py      # modelos Pydantic (mismo contrato que src/auth/types.ts del front)
  errors.py       # ApiError uniforme {codigo, mensaje}
  imagenes.py     # normalización de fotos de perfil (Pillow)
  routers/auth.py # POST /register, /login, /logout, GET /me,
                  #   PUT/DELETE /me/foto
  routers/usuarios.py # GET /usuarios/{id}/foto
  routers/admin.py # /admin/usuarios (listar, estado, rol, password,
                   #   DELETE eliminar, POST restaurar) y /admin/sesiones
  routers/empresa.py # /empresa/mio, respuestas del autodiagnóstico y
                     #   POST …/analisis-ia (análisis inteligente)
  ia/schemas.py      # contratos del análisis IA (entrada del motor, salida de Gemini)
  ia/prompts.py      # prompt de Gemini, contexto enviado y huella
  ia/gemini_service.py # cliente google-genai, validación, reintentos, errores
  ia/analisis.py     # guardar/reutilizar, límite por hora, llamadas simultáneas
db/
  001_schema.sql          # copia de nexus360_schema.sql
  002_role_password.sql   # fija password del rol nexus360_app (dev)
  003_cambiar_password.sql        # cambio de contraseña por el propio usuario
  004_admin.sql                   # desbloqueo, reset de password, sesiones
  005_admin_eliminar_usuario.sql  # eliminar/restaurar cuentas + validar_sesion
                                  #   endurecida (mira activo y archivado_en)
  005_catalogo.sql                # catálogo (formatos, dimensiones, preguntas)
  006_grants_catalogo.sql         # SELECT del catálogo para nexus360_app
  006_historial_sesiones.sql      # motivo de cierre de sesión, resumen por
                                  #   usuario y SELECT sobre `formato`
  007_estadisticas_catalogo.sql   # estadísticas del panel
  008_foto_perfil.sql             # tabla usuario_foto (foto de perfil) + RLS
  009_rse_express.sql             # Autodiagnóstico RSE Express: respaldo y
                                  #   reinicio de tamizajes/diagnósticos, tamizaje
                                  #   nuevo, respuestas abiertas y catálogo nuevo
  010_analisis_ia.sql             # tabla diagnostico_analisis_ia (análisis
                                  #   inteligente con Gemini) + RLS
  011_consentimiento_datos.sql    # prueba de la autorización de tratamiento
                                  #   de datos (Ley 1581) + RLS
main.py           # `uvicorn main:app` (reexporta app/main.py)
```

## 1. Levantar PostgreSQL

**Opción rápida (Docker):**

```bash
docker compose up -d
```

Esto crea Postgres 16, corre `001_schema.sql` (crea el esquema `nexus360`,
tablas, RLS y las funciones de auth) y `002_role_password.sql` (fija la
contraseña del rol de aplicación) automáticamente **la primera vez**.

**Opción manual (Postgres ya instalado):**

```bash
createdb nexus360
psql nexus360 -f db/001_schema.sql
psql nexus360 -f db/002_role_password.sql   # o corre tu propio ALTER ROLE
psql nexus360 -f db/003_cambiar_password.sql
psql nexus360 -f db/004_admin.sql
psql nexus360 -f db/005_admin_eliminar_usuario.sql
psql nexus360 -f db/005_catalogo.sql
psql nexus360 -f db/006_grants_catalogo.sql
psql nexus360 -f db/006_historial_sesiones.sql
psql nexus360 -f db/007_estadisticas_catalogo.sql
psql nexus360 -f db/008_foto_perfil.sql
psql nexus360 -f db/009_rse_express.sql
psql nexus360 -f db/010_analisis_ia.sql
psql nexus360 -f db/011_consentimiento_datos.sql
```

> ⚠️ Si actualizas una base que ya existía, aplica **008 antes de desplegar**
> esta versión del backend: /me, el login y la lista del admin leen
> `usuario_foto`, y sin esa tabla responden 500.

> ⚠️ `002_role_password.sql` trae una contraseña de ejemplo
> (`dev_only_change_me`) solo para desarrollo. En cualquier entorno real,
> cambia esa contraseña y no la subas a un repo.

## 2. Configurar el backend

```bash
cp .env.example .env
```

Ajusta `DATABASE_URL` si tu Postgres no corre en `localhost:5432` o usaste
otra contraseña, y `ALLOWED_ORIGINS` si el front no corre en
`http://localhost:5173`. Para el análisis inteligente, pon tu clave en
`GEMINI_API_KEY` (ver la sección «Análisis inteligente con Gemini (010)»);
si la dejas vacía, todo funciona igual salvo esa sección.

## 3. Instalar dependencias y correr

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Prueba: `curl http://localhost:8000/health` debe responder
`{"estado":"ok","db":"ok"}`.

## 4. Conectar el front

En el proyecto del front (`N360-Prototype`), su `.env`:

```
VITE_API_URL=http://localhost:8000/api
```

Con eso, el login/registro que ya está implementado en el front habla
directo con estos endpoints:

| Método | Ruta                | Descripción |
|--------|---------------------|-------------|
| POST   | `/api/auth/register`| Crea cuenta (siempre rol `empresa`) e inicia sesión de una vez |
| POST   | `/api/auth/login`   | Inicia sesión, devuelve `{token, expira_en, usuario}` |
| POST   | `/api/auth/logout`  | Revoca el token (`Authorization: Bearer <token>`) |
| GET    | `/api/auth/me`      | Devuelve el usuario de la sesión activa |
| PUT    | `/api/auth/me/foto` | Sube/reemplaza la foto de perfil (cuerpo = imagen en binario) |
| DELETE | `/api/auth/me/foto` | Quita la foto: vuelve a la predeterminada |
| GET    | `/api/usuarios/{id}/foto` | Devuelve la foto (la propia, o cualquiera si es admin) |

## Notas de seguridad heredadas del schema

- Las contraseñas nunca se manejan en Python: `registrar_usuario()` las
  hashea con `pgcrypto` (`crypt(...,gen_salt('bf',10))`) dentro de Postgres.
- Los tokens de sesión se generan en Postgres (`gen_random_bytes(32)`); en
  la tabla `sesion` solo se guarda su hash SHA-256. El backend solo ve el
  token en claro en la respuesta de `iniciar_sesion()`, para devolvérselo
  al cliente una vez.
- Tras 5 intentos fallidos, la cuenta se bloquea 15 minutos
  (`bloqueado_hasta`); el backend traduce eso a `423 CUENTA_BLOQUEADA`.
- Por diseño del schema, `iniciar_sesion()` **no distingue** "cuenta
  inactiva" de "contraseña incorrecta" en su respuesta (para no revelar si
  un correo existe o no) — ambas llegan al front como
  `401 CREDENCIALES_INVALIDAS`.
- Cada request que necesita leer `usuario` fija
  `SET LOCAL app.current_usuario_id = '<uuid>'` (vía `set_config`) dentro
  de la misma transacción, tal como exige el Row Level Security del
  schema — así cada quien solo puede leer su propia fila.
- El backend se conecta como `nexus360_app` (rol de aplicación, sujeto a
  RLS), nunca como el dueño del esquema.

## Siguiente paso natural

Estos cuatro endpoints ya cubren el login/register real. El resto del
esquema (empresa, ciclo_tamizaje, diagnostico, respuesta, evidencia) queda
listo para exponerse en nuevos routers cuando avances con esa parte del
front — mismo patrón: RLS + `fijar_usuario_actual()` en cada request.


## Eliminación de cuentas (005)

`DELETE /api/admin/usuarios/{id}` no siempre borra. Sigue la regla de
borrado del modelo v3.1:

- **Borrado físico** si la cuenta no dejó rastro: nunca creó una empresa,
  no está vinculada a ninguna, y no respondió preguntas.
- **Archivado** (`archivado_en = now()`, `activo = false`) en cualquier
  otro caso, para no dejar en NULL `empresa.creado_por` ni
  `respuesta.respondido_por` y perder la trazabilidad de quién
  autoevaluó qué.

La respuesta trae `modo: 'fisico' | 'archivado'` para que el panel diga
qué pasó de verdad. `?conservar_historial=true` fuerza el archivado.

Guardas: solo admin; nadie se elimina a sí mismo; no se puede eliminar al
último administrador activo; y una cuenta ya eliminada responde 409.

Al eliminar (en ambos modos) se revocan las sesiones vivas del usuario.
Además, 005 reemplaza `validar_sesion()` para que también exija que el
usuario esté activo y no archivado: antes, desactivar una cuenta no
surtía efecto hasta que expirara su token (12 h).

`POST /api/admin/usuarios/{id}/restaurar` deshace un archivado, salvo que
otra cuenta activa ya haya tomado ese correo (el archivado lo libera).


## Actividad de un usuario (006)

`GET /api/admin/usuarios/{id}/actividad` devuelve, en un solo viaje, todo
lo que el sistema sabe del paso de esa persona por la plataforma:

- **sesiones**: cuándo entró, cuándo se cerró y por qué. 006 agrega
  `sesion.revocado_motivo` con tres valores — `logout` (el usuario salió),
  `admin` (se la revocaron) y `eliminacion` (se eliminó la cuenta) —
  porque antes las tres cosas escribían la misma marca en `revocado_en`.
  Las sesiones cerradas antes de la migración quedan en `NULL`: el dato no
  existe y no se inventa.
- **empresas** a las que está vinculada, marcando cuáles creó.
- **tamizajes**: los ciclos de sus empresas. El esquema guarda solo
  `creado_en`, así que no hay historial de ediciones ni autor del cambio.
- **diagnosticos**: Formato 01 y 02 con estado, apertura, cierre y cuántas
  de las respuestas son suyas frente al total del diagnóstico.

`GET /api/admin/sesiones/resumen` da el conteo por usuario (total, activas,
última entrada) para la lista, sin traer las sesiones completas.

Mientras no existan los endpoints que guardan empresa, tamizaje y
diagnósticos, esas tres secciones responden vacías: las tablas están, pero
nadie escribe en ellas todavía.


## Foto de perfil (008)

Cada usuario tiene **siempre** una foto: si no subió ninguna, el front
dibuja la predeterminada (sus iniciales sobre un color que sale de su
`usuario_id`, así que es estable). No se guarda nada para eso.

Cuando sube una, queda en la tabla `usuario_foto` (aparte de `usuario`,
para no hacer más pesadas las lecturas de login, /me y la lista del
admin). `UsuarioOut` y `UsuarioAdminOut` traen `foto_actualizada_en`:
`null` = foto predeterminada; si no, es la versión de la foto, que el
front usa para su caché.

- **Subir** — `PUT /api/auth/me/foto` con la imagen en el cuerpo (no
  multipart). El backend no confía en el cliente: la vuelve a decodificar
  y codificar con Pillow (`app/imagenes.py`). Así rechaza lo que no es
  una imagen de verdad (SVG incluido), topa el tamaño (5 MB de entrada,
  40 MP) contra "bombas" de descompresión, aplica la orientación EXIF y
  **quita los metadatos (incluida la ubicación GPS)**. Guarda un cuadrado
  de máx. 512 px en WebP (~20–40 KB). La conexión a la base no se retiene
  mientras sube el archivo: se valida la sesión, se suelta la conexión, y
  se toma otra solo para escribir.
- **Leer** — `GET /api/usuarios/{id}/foto` exige sesión (la foto no es
  pública). Quién ve qué lo decide el RLS de `usuario_foto`: cada quien la
  suya y el admin todas. "No tiene foto" y "no puedes verla" responden
  igual (404), para no revelar qué cuentas existen. Con `?v=<versión>` se
  marca como caché inmutable; también responde `304` con `If-None-Match`.
- **Quitar** — `DELETE /api/auth/me/foto`, idempotente.

RLS con FORCE: nadie, ni un admin, puede poner o borrar la foto de otra
persona. El borrado físico de una cuenta (`admin_eliminar_usuario`) borra
su foto en cascada; el archivado la conserva, por si se restaura.


## Autodiagnóstico RSE Express (009)

Reemplaza el Formato 01 (ISO 26000, 21 preguntas) y el Formato 02 (Ley
2173, 26 preguntas) por el Autodiagnóstico RSE Express del Anexo 1 del
*Protocolo de Validación NEXUS RSE Express + RSE por Retos* (v2, sept. 2026):
7 materias, 21 preguntas abiertas y un tamizaje nuevo.

### Aplicarlo en una base que ya tiene usuarios

Con el rol dueño del esquema (no `nexus360_app`), **antes** de desplegar
esta versión del backend:

```bash
psql "$DATABASE_URL_OWNER" -f db/009_rse_express.sql
```

Todo corre en una sola transacción: si algo falla, no cambia nada.

- **Se conserva** todo lo de la cuenta: usuarios (nombre, correo,
  contraseña, rol, foto, sesiones) y empresas (razón social, NIT, DV,
  sector, municipio, departamento) con sus vínculos.
- **Se respalda y se retira** lo del instrumento anterior: tamizajes,
  diagnósticos, respuestas, evidencias y pesos por sector se copian al
  esquema `nexus360_respaldo` (tablas `*_v1`) y se borran de las tablas
  vivas. La aplicación no lee ese esquema. Cuando ya no se necesite:
  `DROP SCHEMA nexus360_respaldo CASCADE;`
- Los formatos `iso26000` y `ley2173` quedan archivados (no borrados).
- Es idempotente: si se corre dos veces, la segunda no respalda ni borra
  nada (detecta que el tamizaje ya tiene la estructura nueva).

Al volver a entrar, `GET /api/empresa/mio` devuelve la empresa con
`tamizaje: null` y el front pide el tamizaje nuevo con el perfil ya lleno.

### Tamizaje nuevo (`ciclo_tamizaje`)

T1 `tamano` (micro | pequena | mediana | nose) + `ingresos_rango` opcional;
T2 `personas` y `vinculacion[]` (laboral | servicios | socios | temporada |
otra) + detalle; T5 `zonas[]` (barrios | veredas | rural | indigenas | afro |
otras) y/o `territorio`; T6 `clientes` (personas | empresas | publicas |
mezcla) + detalle. Se retiran empleados, Áreas de Vida, ciclo previo,
comunidades étnicas y consumidor final.

### Respuesta abierta (`respuesta`, `respuesta_materia`, `diagnostico`)

Cada respuesta guarda `texto`, `ejemplos[]`, `otro_texto` y la etapa:
`valor` 0–4 (lectura interna de la sección 6.3), `es_na` («No aplica») o
`es_diferente` («Hacemos algo diferente», sin valor hasta que NEXUS la
clasifica en `valor_clasificado`; un trigger impide que alguien que no sea
admin escriba esa columna). `respuesta_materia` guarda «¿Qué le gustaría
fortalecer?» por materia, y `diagnostico` la pregunta final
(`comentario_final`) y la matriz de priorización (`priorizacion` JSONB).

### Rutas

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/empresa/mio` | perfil + tamizaje vigente + autodiagnóstico (404 solo si no hay empresa) |
| PUT | `/api/empresa/mio` | crea/actualiza perfil y tamizaje (actualiza el ciclo vigente) |
| PUT | `/api/empresa/mio/diagnosticos/rse_express/respuestas` | guarda el autodiagnóstico; solo reescribe lo que cambió. Los formatos retirados responden 410 |
| GET | `/api/admin/empresas/{empresa_id}/diagnostico` | lo que respondió una empresa |
| PUT | `/api/admin/respuestas/{respuesta_id}/clasificacion` | NEXUS clasifica (0–4 o `null`) una respuesta «Hacemos algo diferente» |
| GET | `/api/admin/estadisticas` | ahora con `empresas_por_cliente`, `respuestas_por_etapa` e `indicadores` (sección 10) |
| GET | `/api/admin/empresas` | ahora con el tamizaje nuevo, `perfil_piloto` (10–50 personas) y el avance del autodiagnóstico |

El catálogo de 009 se generó a partir del mismo archivo que
`src/data/rseExpress.ts` del frontend: si cambia una pregunta, hay que
cambiarla en los dos lados.

### Si el panel dice «No se pudo conectar con el servidor» o las estadísticas no cargan

Casi siempre es que la base no tiene aplicada `009_rse_express.sql` (el log
del backend muestra `column "clientes" does not exist` o
`column "actualizado_en" does not exist`). Desde esta versión:

- Al arrancar, el backend lo detecta y escribe en el log
  `ESQUEMA DESACTUALIZADO: falta …` con la instrucción.
- `GET /health` responde 503 con `"esquema": "falta_009"` y la lista de lo
  que falta.
- Las rutas responden 503 `ESQUEMA_DESACTUALIZADO` con un mensaje claro, que
  el panel muestra tal cual. Antes salía un 500 sin cabeceras CORS y el
  navegador lo reportaba como error de conexión.

Solución: aplicar la migración con el rol dueño del esquema y reiniciar.

```bash
psql "postgresql://postgres:<clave>@localhost:5432/nexus360" -f db/009_rse_express.sql
# verificar:
psql "postgresql://postgres:<clave>@localhost:5432/nexus360" \
  -c "select column_name from information_schema.columns where table_schema='nexus360' and table_name='ciclo_tamizaje' and column_name='clientes'"
curl http://localhost:8000/health    # debe decir "esquema": "ok"
```

### Estadísticas del RSE Express (`GET /api/admin/estadisticas`)

Además de las anteriores: `empresas_por_personas` (rangos de T2; 10–50 es el
perfil del piloto), `etapas_por_materia` (respuestas por materia y etapa,
para la gráfica «Etapas»), `practicas_por_materia`, `retos_por_materia`
(materia de la oportunidad elegida en la matriz de priorización) y
`alertas` (empresas con cada alerta informativa: SG-SST, datos personales,
Ley 2173 y comunidades étnicas, con las mismas reglas que ve la empresa).

### Datos de demostración (opcional)

Como 009 reinicia los diagnósticos, el panel queda casi vacío hasta que las
empresas vuelvan a responder. Para ver las estadísticas y gráficas con
datos, hay un juego de demostración: 12 empresas ficticias cuyo nombre
empieza por «DEMO · », con tamizaje, respuestas abiertas, prácticas
propias (algunas ya clasificadas), «qué le gustaría fortalecer» y matriz de
priorización. No toca usuarios ni empresas reales.

```bash
psql "<conexión del dueño>" -f db/demo/demo_rse_express.sql   # crear (se puede repetir)
psql "<conexión del dueño>" -f db/demo/borrar_demo.sql        # quitar
```

### Pruebas

`pytest` (85 pruebas: contrato de rutas, validaciones del tamizaje y las
etapas, errores con CORS y mensaje de migración pendiente, análisis IA y
registro con autorización de datos; 7 más de integración con la base,
opcionales — ver «Pruebas del análisis IA»). La migración se probó sobre una base con datos del instrumento
anterior (dos corridas, conservación de cuentas, respaldo) y sobre una
instalación desde cero con todas las migraciones.


## Análisis inteligente con Gemini (010)

Los resultados del autodiagnóstico ahora traen una sección **«Análisis
inteligente»**: un resumen ejecutivo, fortalezas, áreas de oportunidad,
prioridades, recomendaciones, acciones a corto y mediano plazo y una
conclusión, generados con la Gemini API de Google. También van en el PDF.

### Dos capas, separadas

1. **Diagnóstico** (lo de siempre): niveles, categorías, fortalezas,
   oportunidades, prioridades y alertas los calcula el motor del front
   (`src/engine/scoring.ts`). Esta integración no lo toca ni lo duplica.
2. **IA** (nuevo): Gemini recibe esos resultados ya calculados y los
   **interpreta**. Nunca los recalcula: su respuesta es un JSON estructurado
   sin ningún campo numérico, validado con Pydantic
   (`app/ia/schemas.py::AnalisisIA`), así que no tiene dónde escribir ni
   cambiar un puntaje.

```
React (motor existente) → resultados estructurados → FastAPI
  → ¿hay análisis guardado con la misma huella? → sí: se devuelve
                                                → no: Gemini → validar → guardar
  → React (pantalla) → PDF
```

### Configuración

1. Crea una clave en https://aistudio.google.com/apikey (el nivel gratuito
   basta para un piloto).
2. Ponla **solo** en el `.env` del backend (que está en `.gitignore`):

   ```
   GEMINI_API_KEY=tu_clave_aqui
   ```

   Nunca en el frontend, ni en variables `VITE_*`, ni en el código. El
   navegador jamás la ve: solo habla con este backend.
3. Aplica la migración (con el rol dueño del esquema). Con Docker desde cero
   corre sola, como las demás:

   ```bash
   psql "<conexión del dueño>" -f db/010_analisis_ia.sql
   ```
4. Instala la dependencia nueva (`google-genai`, el SDK oficial) y reinicia:

   ```bash
   pip install -r requirements.txt
   uvicorn main:app --reload --port 8000
   ```

Variables opcionales (con sus valores por defecto): `GEMINI_MODEL`
(`gemini-3.5-flash-lite`, estable y recomendado por Google para proyectos
nuevos; para más profundidad, `gemini-3.8-flash`), `GEMINI_TIMEOUT_SEGUNDOS`
(90: espera máxima **total** por análisis, sumando intentos), `GEMINI_INTENTOS`
(2) e `IA_MAX_GENERACIONES_POR_HORA` (6 por usuario).
Los modelos disponibles y los límites del nivel gratuito cambian con
frecuencia: revísalos en Google AI Studio.

### Cómo probarlo

```bash
curl http://localhost:8000/health
# "analisis_ia": {"tabla": "ok", "gemini": "configurado"}
```

Luego, en el front: completa el autodiagnóstico y abre **Resultados**. Verás
«Analizando resultados…» y, en unos segundos, el análisis. Recarga la
página: aparece al instante (se reutilizó el guardado; en el log no hay una
llamada nueva). Cambia una respuesta y vuelve a Resultados: se regenera.

### Si `/health` dice `"gemini": "sin_sdk"` o `"sin_clave"`

- `sin_sdk`: falta el paquete `google-genai` en el entorno virtual (pasa si
  se actualiza el código sin reinstalar dependencias). El backend arranca
  igual y avisa en el log. Solución: con el `.venv` activado,
  `pip install -r requirements.txt` y reiniciar uvicorn. Funciona con
  Python 3.12 a 3.14 (todas sus dependencias traen ruedas precompiladas).
- `sin_clave`: falta `GEMINI_API_KEY` en el `.env` del backend.

En ambos casos el diagnóstico, los resultados y el PDF funcionan normal;
solo la sección «Análisis inteligente» muestra que no está habilitada.

### Ruta

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/api/empresa/mio/diagnosticos/rse_express/analisis-ia` | cuerpo `{resultados}` (lo que calculó el motor). Devuelve `{diagnostico_id, analisis, generado_en, modelo, version_prompt, reutilizado}` |

Errores, siempre con `{codigo, mensaje}` y un mensaje apto para el usuario:
`503 IA_NO_CONFIGURADA` (no hay clave), `503 IA_NO_DISPONIBLE` (Gemini
falló, no respondió a tiempo, devolvió algo que no cumple el esquema, o
falta la migración 010), `429 IA_LIMITE` (tope por hora). Los formatos
retirados responden 410, como en `…/respuestas`.

### Qué pasa cuando Gemini no está disponible

Nada se rompe. El front muestra un aviso amable (con «Reintentar» cuando
tiene sentido), el mapa de prácticas, la matriz y las alertas siguen igual, y
el botón **Descargar informe (PDF)** genera el informe completo sin la
sección de IA. El backend registra el motivo (código de Gemini, tipo de
error), nunca la clave ni el texto de la empresa. Si ya existía un análisis
guardado para esos mismos resultados, se sigue mostrando aunque hoy no haya
clave o Gemini esté caído.

### Qué se le envía a Gemini

Sector, tamaño, número de personas, tipo de vinculación y de clientes,
municipio y territorio, más los resultados del motor: la etapa y categoría de
cada práctica, lo que la empresa escribió que hace hoy (la respuesta abierta
completa, hasta 1.500 caracteres, con los ejemplos marcados y «Hacemos algo
diferente»), lo que quiere fortalecer (completo), las oportunidades en el
orden del motor, las alertas y el comentario final. La pantalla y el PDF
siguen mostrando el resumen corto de cada respuesta.

**No** se envía: razón social, NIT, correos, nombres de usuario, tokens ni
claves. Tampoco la lectura numérica interna 0–4: el protocolo no le muestra
un puntaje a la empresa, y si Gemini la recibiera podría escribirlo en el
informe. El prompt (`app/ia/prompts.py`) le exige no modificar resultados,
no inventar, fundamentar cada recomendación y tratar los textos de la
empresa como datos, no como instrucciones.

> **Privacidad en el nivel gratuito.** Según las condiciones de la Gemini
> API, en el nivel gratuito Google puede usar el contenido enviado para
> mejorar sus productos. Si las empresas del piloto comparten información
> sensible en sus respuestas abiertas, evalúa usar el nivel de pago
> (revisa las condiciones vigentes en https://ai.google.dev/gemini-api/terms).

### Cuándo se llama a Gemini (control de costo)

- **Una vez por resultado.** La tabla `diagnostico_analisis_ia` guarda un
  análisis por diagnóstico con su `huella` (SHA-256 de lo enviado + versión
  del prompt). Mismo resultado → se reutiliza. Cambian los resultados
  (una respuesta, o NEXUS clasifica una práctica propia) → se regenera la
  próxima vez que se abran los resultados.
- **Peticiones simultáneas** iguales (doble montaje de React en desarrollo,
  dos pestañas) comparten una sola llamada.
- **Tope por usuario** de análisis nuevos por hora (en memoria, por proceso).
- Solo se reintentan los fallos rápidos y pasajeros (500/502/503, sin
  conexión, respuesta inválida), una vez y solo si quedan al menos 15 s del
  total. No se reintenta un tiempo agotado (`ReadTimeout` o `504
  DEADLINE_EXCEEDED`): solo duplicaría la espera. Tampoco un 429 de cuota.
- La terminal muestra cuánto tardó cada análisis («Análisis IA generado con
  … en 23.4 s») o por qué falló. Si aparece seguido «Gemini no respondió a
  tiempo», suba `GEMINI_TIMEOUT_SEGUNDOS`.
- Cambiar el prompt exige subir `VERSION_PROMPT`: los análisis viejos se
  regeneran solos. La v3 (`rse-express-v3`) mantiene las reglas de la v2 y
  acota la extensión de cada campo: respuestas más cortas se generan más
  rápido (con la v2 algunos análisis pasaban de 40 s).

### Prompt v2 (`rse-express-v2`)

Tras revisar informes reales, el prompt exige: justificar cada recomendación
con evidencia de la empresa (código de la práctica, etapa y lo que contó), no
con su posición en la matriz; construir sobre lo que la empresa escribió en
«¿Qué le gustaría fortalecer?»; no copiar las alternativas de la matriz;
llamar «fortaleza» solo a lo que el motor marcó como tal; tener en cuenta las
alertas (p. ej. comunidades étnicas) y no usar jerga interna como
«concluyente». Los análisis guardados con v1 se regeneran la próxima vez que
se abren los resultados. Para más profundidad, `GEMINI_MODEL=gemini-3.8-flash`.

### Tabla `diagnostico_analisis_ia` (010)

`diagnostico_id` (PK, FK a `diagnostico` con `ON DELETE CASCADE`),
`contenido` JSONB, `huella`, `modelo`, `version_prompt`, `generado_en`,
`generado_por`. RLS con FORCE y la misma política que `respuesta_materia`:
cada empresa ve solo lo suyo; el admin, todo. Sin la migración el backend
arranca igual, avisa en el log y el análisis responde «no disponible».

### Pruebas del análisis IA

```bash
pytest                                   # incluye tests/test_analisis_ia.py (sin red ni base)
N360_PRUEBAS_DB=1 pytest tests/test_analisis_ia_integracion.py   # con la base (crea cuentas de prueba)
```

`test_analisis_ia.py` usa el SDK real de `google-genai` con un transporte
HTTP simulado: verifica la petición exacta que saldría hacia Google (modelo,
clave solo en cabecera, JSON Schema, prompt), JSON válido e inválido,
reintentos, cuota agotada, sin conexión, sin clave y que la clave nunca
llegue a los logs. La de integración prueba contra PostgreSQL la
reutilización, la regeneración, el RLS entre empresas, Gemini caído, la
ausencia de clave y la falta de la migración 010 (esta última requiere
`N360_DB_DUENO=<conexión del dueño>`). Ninguna llama a Google ni gasta cuota.


## Autorización de tratamiento de datos (011)

El registro (`POST /api/auth/register`) exige la autorización previa, expresa
e informada de la Ley 1581 de 2012. El cuerpo lleva dos campos nuevos:

```json
{ "acepta_politica_datos": true, "politica_datos_version": "2026-09-29" }
```

- Sin `acepta_politica_datos: true` responde 422 «Para crear la cuenta debe
  autorizar el tratamiento de sus datos personales». Un front viejo que no
  manda el campo recibe el mismo mensaje.
- Si la versión no es la vigente (`app/schemas.py::POLITICA_DATOS_VERSION`)
  responde 422 pidiendo recargar la página: nadie puede aceptar un texto viejo.
- La prueba de la autorización (versión, fecha, IP y navegador) se guarda en
  `consentimiento_datos` **en la misma transacción** que crea la cuenta: si no
  se puede guardar, la cuenta tampoco se crea.

La tabla tiene RLS con FORCE: cada quien ve su autorización y el admin todas;
el rol de aplicación puede insertar y leer, no modificar ni borrar (es
evidencia). Si una cuenta se borra físicamente, su autorización se va con ella.

**Aplicarla** con el rol dueño, antes de desplegar esta versión:

```bash
psql "<conexión del dueño>" -f db/011_consentimiento_datos.sql
```

Sin ella, el backend arranca, lo escribe en el log y `/health` muestra
`"consentimiento_datos": "falta_011"`; el login y todo lo demás funcionan,
pero el **registro de cuentas nuevas responde 503** hasta aplicarla (no se
crean cuentas sin prueba de autorización).

**Si cambia la política:** sube la versión aquí y en
`src/data/politicaDatos.ts` del front, a la vez. Las cuentas existentes
conservan la versión que aceptaron; pedirles la nueva al iniciar sesión
todavía no está implementado.
