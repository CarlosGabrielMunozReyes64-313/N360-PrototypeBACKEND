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
  routers/auth.py # POST /register, /login, /logout, GET /me
  routers/admin.py # /admin/usuarios (listar, estado, rol, password,
                   #   DELETE eliminar, POST restaurar) y /admin/sesiones
db/
  001_schema.sql          # copia de nexus360_schema.sql
  002_role_password.sql   # fija password del rol nexus360_app (dev)
  003_cambiar_password.sql        # cambio de contraseña por el propio usuario
  004_admin.sql                   # desbloqueo, reset de password, sesiones
  005_admin_eliminar_usuario.sql  # eliminar/restaurar cuentas + validar_sesion
                                  #   endurecida (mira activo y archivado_en)
  006_historial_sesiones.sql      # motivo de cierre de sesión, resumen por
                                  #   usuario y SELECT sobre `formato`
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
psql nexus360 -f db/006_historial_sesiones.sql
```

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
