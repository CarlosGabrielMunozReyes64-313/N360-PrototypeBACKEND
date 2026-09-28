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
`http://localhost:5173`.

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

`pytest` (48 pruebas: contrato de rutas, validaciones del tamizaje y las
etapas, y errores con CORS y mensaje de migración pendiente). La migración se probó sobre una base con datos del instrumento
anterior (dos corridas, conservación de cuentas, respaldo) y sobre una
instalación desde cero con todas las migraciones.
