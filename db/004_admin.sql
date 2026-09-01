-- 004_admin.sql
-- Funciones necesarias para las funciones de administrador:
--   - desbloquear una cuenta (limpia intentos_fallidos/bloqueado_hasta,
--     columnas fuera del GRANT UPDATE normal, por diseño del schema)
--   - restablecer la contraseña de un usuario sin conocer la actual
--     (a diferencia de cambiar_password_usuario, que sí la exige)
--   - listar y revocar sesiones (la tabla `sesion` no tiene NINGUNA
--     política RLS ni GRANT para nexus360_app — todo pasa por funciones
--     SECURITY DEFINER, igual que iniciar_sesion/cerrar_sesion)
--
-- cambiar_rol_usuario() ya existe desde 001_schema.sql — no se toca aquí.
--
-- Aplicar UNA vez, con el rol dueño del esquema (NO nexus360_app):
--   psql "<conexión>" -f db/004_admin.sql

BEGIN;
SET search_path TO nexus360;

CREATE OR REPLACE FUNCTION nexus360.admin_desbloquear_usuario(p_usuario_id UUID)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
BEGIN
    IF nexus360.rol_usuario_actual() <> 'admin' THEN
        RAISE EXCEPTION 'Solo un administrador puede desbloquear cuentas';
    END IF;

    UPDATE nexus360.usuario
       SET intentos_fallidos = 0,
           bloqueado_hasta   = NULL
     WHERE usuario_id = p_usuario_id;
END;
$$;

CREATE OR REPLACE FUNCTION nexus360.admin_restablecer_password(
    p_usuario_id      UUID,
    p_password_nueva  TEXT
)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
BEGIN
    IF nexus360.rol_usuario_actual() <> 'admin' THEN
        RAISE EXCEPTION 'Solo un administrador puede restablecer contraseñas';
    END IF;
    IF p_password_nueva IS NULL OR length(p_password_nueva) < 8 THEN
        RAISE EXCEPTION 'La contraseña debe tener al menos 8 caracteres';
    END IF;

    UPDATE nexus360.usuario
       SET password_hash = crypt(p_password_nueva, gen_salt('bf', 10))
     WHERE usuario_id = p_usuario_id;
END;
$$;

CREATE OR REPLACE FUNCTION nexus360.admin_listar_sesiones(p_usuario_id UUID DEFAULT NULL)
RETURNS TABLE (
    sesion_id    UUID,
    usuario_id   UUID,
    creado_en    TIMESTAMPTZ,
    expira_en    TIMESTAMPTZ,
    revocado_en  TIMESTAMPTZ,
    ip_origen    INET,
    user_agent   TEXT
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
BEGIN
    IF nexus360.rol_usuario_actual() <> 'admin' THEN
        RAISE EXCEPTION 'Solo un administrador puede ver las sesiones';
    END IF;

    RETURN QUERY
    SELECT s.sesion_id, s.usuario_id, s.creado_en, s.expira_en, s.revocado_en,
           s.ip_origen, s.user_agent
      FROM nexus360.sesion s
     WHERE p_usuario_id IS NULL OR s.usuario_id = p_usuario_id
     ORDER BY s.creado_en DESC
     LIMIT 200;
END;
$$;

CREATE OR REPLACE FUNCTION nexus360.admin_revocar_sesion(p_sesion_id UUID)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
BEGIN
    IF nexus360.rol_usuario_actual() <> 'admin' THEN
        RAISE EXCEPTION 'Solo un administrador puede revocar sesiones';
    END IF;

    UPDATE nexus360.sesion
       SET revocado_en = now()
     WHERE sesion_id = p_sesion_id
       AND revocado_en IS NULL;
END;
$$;

REVOKE ALL ON FUNCTION nexus360.admin_desbloquear_usuario(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.admin_restablecer_password(UUID, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.admin_listar_sesiones(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.admin_revocar_sesion(UUID) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION nexus360.admin_desbloquear_usuario(UUID) TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.admin_restablecer_password(UUID, TEXT) TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.admin_listar_sesiones(UUID) TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.admin_revocar_sesion(UUID) TO nexus360_app;

COMMIT;
