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
db/
  001_schema.sql          # copia de nexus360_schema.sql
  002_role_password.sql   # fija password del rol nexus360_app (dev)
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
