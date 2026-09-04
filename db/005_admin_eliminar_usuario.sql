-- 005_admin_eliminar_usuario.sql
-- Eliminación de usuarios desde el panel de administración.
--
-- Sigue la regla de borrado del modelo v3.1 (la misma que ya rige el
-- catálogo): el borrado FÍSICO solo procede cuando la fila no dejó
-- rastro; en cualquier otro caso se archiva (archivado_en = now()).
-- Para un usuario, "rastro" significa que ya está vinculado a alguna
-- empresa, que creó una empresa, o que respondió preguntas de un
-- diagnóstico. Si se borrara físicamente en esos casos, empresa.creado_por
-- y respuesta.respondido_por quedarían en NULL (ON DELETE SET NULL) y se
-- perdería la trazabilidad de quién autoevaluó qué — justo lo que un
-- diagnóstico normativo no puede permitirse.
--
-- Consecuencias del archivado, todas ya previstas por 001_schema.sql:
--   - uq_usuario_email es parcial (WHERE archivado_en IS NULL), así que
--     al archivar se LIBERA el correo y esa persona puede volver a
--     registrarse sin chocar con su cuenta vieja.
--   - iniciar_sesion() ya filtra archivado_en IS NULL, así que la cuenta
--     archivada no puede volver a entrar.
--
-- Aplicar UNA vez, con el rol dueño del esquema (NO nexus360_app):
--   psql "<conexión>" -f db/005_admin_eliminar_usuario.sql

BEGIN;
SET search_path TO nexus360;

-- ---------------------------------------------------------------------
-- 1. Eliminar (archivar o borrar) un usuario
-- ---------------------------------------------------------------------
-- Devuelve 'fisico' o 'archivado' para que el backend pueda decirle al
-- admin qué fue lo que realmente pasó, en vez de dar un "listo" opaco.
--
-- p_conservar_historial = TRUE fuerza el archivado incluso cuando la
-- cuenta está limpia (útil si se quiere dejar constancia de que existió).
CREATE OR REPLACE FUNCTION nexus360.admin_eliminar_usuario(
    p_usuario_id          UUID,
    p_conservar_historial BOOLEAN DEFAULT FALSE
)
RETURNS TEXT
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
DECLARE
    v_llamante     UUID := nexus360.current_usuario_id();
    v_usuario      nexus360.usuario%ROWTYPE;
    v_otros_admins INT;
    v_tiene_rastro BOOLEAN;
BEGIN
    IF nexus360.rol_usuario_actual() <> 'admin' THEN
        RAISE EXCEPTION 'Solo un administrador puede eliminar cuentas';
    END IF;

    SELECT * INTO v_usuario FROM nexus360.usuario u WHERE u.usuario_id = p_usuario_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'El usuario no existe';
    END IF;

    IF v_usuario.archivado_en IS NOT NULL THEN
        RAISE EXCEPTION 'La cuenta ya fue eliminada';
    END IF;

    -- Mismo criterio que cambiar_rol_usuario en el router: un admin no se
    -- borra a sí mismo (no se puede deshacer desde su propia sesión).
    IF p_usuario_id = v_llamante THEN
        RAISE EXCEPTION 'No puedes eliminar tu propia cuenta';
    END IF;

    -- Nunca dejar el sistema sin administración.
    IF v_usuario.rol = 'admin' THEN
        SELECT count(*) INTO v_otros_admins
          FROM nexus360.usuario u
         WHERE u.rol = 'admin'
           AND u.archivado_en IS NULL
           AND u.activo
           AND u.usuario_id <> p_usuario_id;

        IF v_otros_admins = 0 THEN
            RAISE EXCEPTION 'No se puede eliminar al último administrador activo';
        END IF;
    END IF;

    SELECT EXISTS (SELECT 1 FROM nexus360.empresa e         WHERE e.creado_por     = p_usuario_id)
        OR EXISTS (SELECT 1 FROM nexus360.usuario_empresa ue WHERE ue.usuario_id    = p_usuario_id)
        OR EXISTS (SELECT 1 FROM nexus360.respuesta r        WHERE r.respondido_por = p_usuario_id)
      INTO v_tiene_rastro;

    -- En los dos caminos se cierran las sesiones vivas. En el físico el
    -- ON DELETE CASCADE de `sesion` lo haría igual, pero dejarlo explícito
    -- evita que una sesión siga siendo válida un instante durante el
    -- archivado (validar_sesion mira la sesión, no el estado del usuario).
    UPDATE nexus360.sesion s
       SET revocado_en = now()
     WHERE s.usuario_id = p_usuario_id
       AND s.revocado_en IS NULL;

    IF p_conservar_historial OR v_tiene_rastro THEN
        UPDATE nexus360.usuario u
           SET archivado_en      = now(),
               activo            = FALSE,
               intentos_fallidos = 0,
               bloqueado_hasta   = NULL
         WHERE u.usuario_id = p_usuario_id;

        RETURN 'archivado';
    END IF;

    -- Cuenta sin rastro: se borra de verdad. usuario_empresa y sesion
    -- caen por CASCADE.
    DELETE FROM nexus360.usuario u WHERE u.usuario_id = p_usuario_id;

    RETURN 'fisico';
END;
$$;

-- ---------------------------------------------------------------------
-- 2. Restaurar una cuenta archivada
-- ---------------------------------------------------------------------
-- El borrado suave sin vuelta atrás es una trampa: si el admin se
-- equivoca de fila, la cuenta queda inaccesible para siempre. Esto
-- deshace el archivado, salvo que el correo ya lo haya tomado una cuenta
-- nueva (uq_usuario_email lo impediría con un error críptico).
CREATE OR REPLACE FUNCTION nexus360.admin_restaurar_usuario(p_usuario_id UUID)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
DECLARE
    v_usuario nexus360.usuario%ROWTYPE;
BEGIN
    IF nexus360.rol_usuario_actual() <> 'admin' THEN
        RAISE EXCEPTION 'Solo un administrador puede restaurar cuentas';
    END IF;

    SELECT * INTO v_usuario FROM nexus360.usuario u WHERE u.usuario_id = p_usuario_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'El usuario no existe';
    END IF;

    IF v_usuario.archivado_en IS NULL THEN
        RAISE EXCEPTION 'La cuenta no está eliminada';
    END IF;

    IF EXISTS (
        SELECT 1 FROM nexus360.usuario u
         WHERE u.email = v_usuario.email
           AND u.archivado_en IS NULL
    ) THEN
        RAISE EXCEPTION 'Ya existe una cuenta activa con ese correo';
    END IF;

    UPDATE nexus360.usuario u
       SET archivado_en      = NULL,
           activo            = TRUE,
           intentos_fallidos = 0,
           bloqueado_hasta   = NULL
     WHERE u.usuario_id = p_usuario_id;
END;
$$;

-- ---------------------------------------------------------------------
-- 3. validar_sesion(): que el estado de la cuenta cuente en cada request
-- ---------------------------------------------------------------------
-- Misma firma y mismo contrato de retorno; solo se le agrega la
-- verificación del usuario. Sin esto, desactivar o archivar una cuenta no
-- surtía efecto hasta que expirara su token (12 h), porque validar_sesion
-- solo miraba la tabla `sesion`. Los GRANT/REVOKE se conservan al hacer
-- CREATE OR REPLACE, pero se repiten abajo para que este archivo pueda
-- correrse por sí solo sin dejar dudas.
CREATE OR REPLACE FUNCTION nexus360.validar_sesion(p_token TEXT)
RETURNS UUID
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
    SELECT s.usuario_id
      FROM nexus360.sesion s
      JOIN nexus360.usuario u ON u.usuario_id = s.usuario_id
     WHERE s.token_hash = encode(digest(p_token, 'sha256'), 'hex')
       AND s.revocado_en IS NULL
       AND s.expira_en > now()
       AND u.activo
       AND u.archivado_en IS NULL;
$$;

REVOKE ALL ON FUNCTION nexus360.admin_eliminar_usuario(UUID, BOOLEAN) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.admin_restaurar_usuario(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.validar_sesion(TEXT) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION nexus360.admin_eliminar_usuario(UUID, BOOLEAN) TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.admin_restaurar_usuario(UUID) TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.validar_sesion(TEXT) TO nexus360_app;

COMMIT;
