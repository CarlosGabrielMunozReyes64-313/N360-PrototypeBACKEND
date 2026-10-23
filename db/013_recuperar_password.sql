-- 013_recuperar_password.sql
-- Recuperación de contraseña por correo («¿Olvidaste tu contraseña?»).
--
-- Flujo:
--   1. POST /auth/recuperar-password {email} -> solicitar_recuperacion_password()
--      genera un token aleatorio de un solo uso y el backend lo manda por
--      correo dentro de un enlace. La respuesta HTTP es SIEMPRE la misma,
--      exista o no el correo (no se revela qué correos tienen cuenta).
--   2. El enlace abre el front en #/restablecer?token=...; el front pregunta
--      si sigue vigente (verificar_token_recuperacion) y muestra el formulario.
--   3. POST /auth/restablecer-password {token, password_nueva} ->
--      restablecer_password() cambia la contraseña, gasta el token, anula los
--      demás pendientes, desbloquea la cuenta y CIERRA TODAS sus sesiones.
--
-- Mismo diseño de seguridad que `sesion` (ver 001_schema.sql):
--   * En la tabla solo queda el HASH SHA-256 del token, nunca el token: con
--     una copia de la base no se puede usar ningún enlace pendiente.
--   * RLS habilitado SIN políticas y sin ningún GRANT: nexus360_app no puede
--     leer ni escribir la tabla. Todo pasa por funciones SECURITY DEFINER.
--   * Los tokens vencen (30 min por defecto), sirven una sola vez, y quedan
--     anulados si la cuenta cambia de contraseña o de correo por cualquier
--     otro camino (trigger de la sección 4).
--
-- Aplicar UNA vez, con el rol dueño del esquema (NO nexus360_app):
--   psql "<conexión>" -f db/013_recuperar_password.sql
-- Es idempotente: se puede volver a correr sin romper nada.

BEGIN;
SET search_path TO nexus360;

-- ---------------------------------------------------------------------
-- 1. Tabla de solicitudes de recuperación
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS nexus360.recuperacion_password (
    recuperacion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id      UUID NOT NULL REFERENCES nexus360.usuario(usuario_id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_en       TIMESTAMPTZ NOT NULL,
    -- Se usó para cambiar la contraseña.
    usado_en        TIMESTAMPTZ,
    -- Quedó sin efecto sin usarse: se pidió otro enlace, o la contraseña o
    -- el correo cambiaron por otro camino.
    anulado_en      TIMESTAMPTZ,
    ip_origen       INET,
    user_agent      TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_recuperacion_token
    ON nexus360.recuperacion_password (token_hash);
CREATE INDEX IF NOT EXISTS idx_recuperacion_usuario
    ON nexus360.recuperacion_password (usuario_id, creado_en DESC);
CREATE INDEX IF NOT EXISTS idx_recuperacion_ip
    ON nexus360.recuperacion_password (ip_origen, creado_en DESC);

COMMENT ON TABLE nexus360.recuperacion_password IS
    'Enlaces de recuperación de contraseña. Solo guarda el hash SHA-256 del token. '
    'Sin acceso directo para nexus360_app: todo pasa por funciones SECURITY DEFINER.';

ALTER TABLE nexus360.recuperacion_password ENABLE ROW LEVEL SECURITY;
-- Sin políticas a propósito (igual que `sesion`): el rol de aplicación no
-- ve ninguna fila aunque alguien le diera un GRANT por error.
REVOKE ALL ON nexus360.recuperacion_password FROM PUBLIC;
REVOKE ALL ON nexus360.recuperacion_password FROM nexus360_app;

-- ---------------------------------------------------------------------
-- 2. Nuevo motivo de cierre de sesión: 'recuperacion'
-- ---------------------------------------------------------------------
-- Para que el historial de sesiones del panel de admin muestre que una
-- sesión se cerró porque el usuario restableció su contraseña por correo.
ALTER TABLE nexus360.sesion DROP CONSTRAINT IF EXISTS sesion_revocado_motivo_check;
ALTER TABLE nexus360.sesion ADD CONSTRAINT sesion_revocado_motivo_check
    CHECK (revocado_motivo IN ('logout', 'admin', 'eliminacion', 'recuperacion'));

COMMENT ON COLUMN nexus360.sesion.revocado_motivo IS
    'Por qué se cerró: logout = el usuario salió; admin = un admin la revocó; '
    'eliminacion = se eliminó la cuenta; recuperacion = se restableció la contraseña '
    'por correo. NULL = cerrada antes de 006, o sigue viva.';

-- ---------------------------------------------------------------------
-- 3. Funciones
-- ---------------------------------------------------------------------

-- Crea un enlace de recuperación. Devuelve el token EN CLARO una sola vez
-- (el backend lo mete en el correo) junto con el correo y el nombre del
-- destinatario. Devuelve CERO filas, sin error, cuando no corresponde
-- enviar nada:
--   * el correo no tiene cuenta, o la cuenta está inactiva o eliminada;
--   * la cuenta ya pidió 3 enlaces en la última hora (evita llenar de
--     correos a alguien);
--   * esa IP ya generó 10 enlaces en la última hora.
-- En todos esos casos el endpoint responde exactamente lo mismo que cuando
-- sí se envía: quien llama no puede distinguirlos.
CREATE OR REPLACE FUNCTION nexus360.solicitar_recuperacion_password(
    p_email      CITEXT,
    p_ip         INET    DEFAULT NULL,
    p_user_agent TEXT    DEFAULT NULL,
    p_minutos    INTEGER DEFAULT 30
)
RETURNS TABLE (token TEXT, email TEXT, nombre TEXT, expira_en TIMESTAMPTZ)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
DECLARE
    v_usuario nexus360.usuario%ROWTYPE;
    v_token   TEXT;
    v_expira  TIMESTAMPTZ;
    v_minutos INTEGER := LEAST(GREATEST(COALESCE(p_minutos, 30), 5), 120);
BEGIN
    -- Limpieza perezosa: las solicitudes de hace más de 30 días ya no
    -- sirven ni para el límite por hora ni para auditoría reciente.
    DELETE FROM nexus360.recuperacion_password r
     WHERE r.creado_en < now() - interval '30 days';

    SELECT * INTO v_usuario
      FROM nexus360.usuario u
     WHERE u.email = p_email
       AND u.archivado_en IS NULL
       AND u.activo;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    -- Bloquea la fila del usuario: dos solicitudes simultáneas para la misma
    -- cuenta se atienden en fila y el límite por hora no se puede saltar.
    PERFORM 1 FROM nexus360.usuario u WHERE u.usuario_id = v_usuario.usuario_id FOR UPDATE;

    IF (SELECT count(*) FROM nexus360.recuperacion_password r
         WHERE r.usuario_id = v_usuario.usuario_id
           AND r.creado_en > now() - interval '1 hour') >= 3 THEN
        RETURN;
    END IF;

    IF p_ip IS NOT NULL AND (SELECT count(*) FROM nexus360.recuperacion_password r
                              WHERE r.ip_origen = p_ip
                                AND r.creado_en > now() - interval '1 hour') >= 10 THEN
        RETURN;
    END IF;

    -- Solo el enlace más reciente sirve: los anteriores quedan anulados.
    UPDATE nexus360.recuperacion_password r
       SET anulado_en = now()
     WHERE r.usuario_id = v_usuario.usuario_id
       AND r.usado_en IS NULL
       AND r.anulado_en IS NULL;

    -- 32 bytes aleatorios de pgcrypto (256 bits): imposible de adivinar.
    v_token  := encode(gen_random_bytes(32), 'hex');
    v_expira := now() + make_interval(mins => v_minutos);

    INSERT INTO nexus360.recuperacion_password
        (usuario_id, token_hash, expira_en, ip_origen, user_agent)
    VALUES
        (v_usuario.usuario_id, encode(digest(v_token, 'sha256'), 'hex'), v_expira,
         p_ip, left(p_user_agent, 500));

    RETURN QUERY SELECT v_token, v_usuario.email::TEXT, v_usuario.nombre, v_expira;
END;
$$;

-- ¿El enlace todavía sirve? La usa el front para avisar «este enlace ya
-- venció» ANTES de que la persona escriba la contraseña nueva. No gasta el
-- token ni revela de quién es.
CREATE OR REPLACE FUNCTION nexus360.verificar_token_recuperacion(p_token TEXT)
RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
    SELECT EXISTS (
        SELECT 1
          FROM nexus360.recuperacion_password r
          JOIN nexus360.usuario u ON u.usuario_id = r.usuario_id
         WHERE r.token_hash = encode(digest(p_token, 'sha256'), 'hex')
           AND r.usado_en IS NULL
           AND r.anulado_en IS NULL
           AND r.expira_en > now()
           AND u.activo
           AND u.archivado_en IS NULL
    );
$$;

-- Cambia la contraseña con un token válido. Todo ocurre en una sola
-- transacción: si algo falla, no cambia nada y el token sigue sin usarse.
-- Devuelve correo y nombre para el aviso «tu contraseña cambió».
CREATE OR REPLACE FUNCTION nexus360.restablecer_password(
    p_token          TEXT,
    p_password_nueva TEXT
)
RETURNS TABLE (usuario_id UUID, email TEXT, nombre TEXT)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
DECLARE
    v_recuperacion nexus360.recuperacion_password%ROWTYPE;
    v_usuario      nexus360.usuario%ROWTYPE;
BEGIN
    -- FOR UPDATE: si el formulario se envía dos veces a la vez, la segunda
    -- espera a la primera y luego encuentra el token ya usado.
    SELECT r.* INTO v_recuperacion
      FROM nexus360.recuperacion_password r
     WHERE r.token_hash = encode(digest(coalesce(p_token, ''), 'sha256'), 'hex')
       AND r.usado_en IS NULL
       AND r.anulado_en IS NULL
       AND r.expira_en > now()
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El enlace de recuperación no es válido o ya expiró';
    END IF;

    SELECT u.* INTO v_usuario
      FROM nexus360.usuario u
     WHERE u.usuario_id = v_recuperacion.usuario_id
       AND u.activo
       AND u.archivado_en IS NULL
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El enlace de recuperación no es válido o ya expiró';
    END IF;

    -- Misma regla que registrar_usuario() y cambiar_password_usuario().
    IF p_password_nueva IS NULL OR length(p_password_nueva) < 8 THEN
        RAISE EXCEPTION 'La contraseña debe tener al menos 8 caracteres';
    END IF;

    -- Se marca usado ANTES de cambiar la contraseña: así el trigger de la
    -- sección 4 (que anula los pendientes al cambiar password_hash) no lo
    -- toca, y queda registrado como «usado», no como «anulado».
    UPDATE nexus360.recuperacion_password r
       SET usado_en = now()
     WHERE r.recuperacion_id = v_recuperacion.recuperacion_id;

    -- Abrir el enlace prueba que la persona controla el buzón: se marca el
    -- correo como verificado si aún no lo estaba. También se levanta el
    -- bloqueo por intentos fallidos: quien olvidó la contraseña suele haber
    -- llegado aquí justamente por eso.
    UPDATE nexus360.usuario u
       SET password_hash       = crypt(p_password_nueva, gen_salt('bf', 10)),
           intentos_fallidos   = 0,
           bloqueado_hasta     = NULL,
           email_verificado_en = COALESCE(u.email_verificado_en, now())
     WHERE u.usuario_id = v_usuario.usuario_id;

    -- Si alguien más tenía la contraseña vieja y una sesión abierta, la
    -- pierde aquí. La persona vuelve a entrar con la contraseña nueva.
    UPDATE nexus360.sesion s
       SET revocado_en     = now(),
           revocado_motivo = 'recuperacion'
     WHERE s.usuario_id = v_usuario.usuario_id
       AND s.revocado_en IS NULL;

    RETURN QUERY SELECT v_usuario.usuario_id, v_usuario.email::TEXT, v_usuario.nombre;
END;
$$;

REVOKE ALL ON FUNCTION nexus360.solicitar_recuperacion_password(CITEXT, INET, TEXT, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.verificar_token_recuperacion(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.restablecer_password(TEXT, TEXT) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION nexus360.solicitar_recuperacion_password(CITEXT, INET, TEXT, INTEGER) TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.verificar_token_recuperacion(TEXT) TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.restablecer_password(TEXT, TEXT) TO nexus360_app;

-- ---------------------------------------------------------------------
-- 4. Si la contraseña o el correo cambian por otro camino, los enlaces
--    pendientes dejan de servir
-- ---------------------------------------------------------------------
-- Casos que cubre: la persona pidió un enlace pero luego recordó la
-- contraseña y la cambió desde «Mi cuenta» (cambiar_password_usuario); un
-- admin se la restableció (admin_restablecer_password); o cambió su correo
-- (PATCH /auth/me) y el enlace había salido hacia el buzón anterior.
-- SECURITY DEFINER porque el UPDATE de correo lo hace nexus360_app, que no
-- tiene ningún acceso a recuperacion_password.
CREATE OR REPLACE FUNCTION nexus360.anular_recuperaciones_pendientes()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
BEGIN
    UPDATE nexus360.recuperacion_password r
       SET anulado_en = now()
     WHERE r.usuario_id = NEW.usuario_id
       AND r.usado_en IS NULL
       AND r.anulado_en IS NULL;
    RETURN NULL;
END;
$$;

REVOKE ALL ON FUNCTION nexus360.anular_recuperaciones_pendientes() FROM PUBLIC;

DROP TRIGGER IF EXISTS trg_anular_recuperaciones ON nexus360.usuario;
CREATE TRIGGER trg_anular_recuperaciones
    AFTER UPDATE OF password_hash, email ON nexus360.usuario
    FOR EACH ROW
    WHEN (OLD.password_hash IS DISTINCT FROM NEW.password_hash
          OR OLD.email IS DISTINCT FROM NEW.email)
    EXECUTE FUNCTION nexus360.anular_recuperaciones_pendientes();

COMMIT;
