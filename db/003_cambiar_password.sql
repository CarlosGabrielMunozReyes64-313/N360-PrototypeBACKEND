-- 003_cambiar_password.sql
-- Agrega la función para que un usuario cambie su propia contraseña.
--
-- password_hash está deliberadamente fuera del GRANT UPDATE directo sobre
-- `usuario` (ver el comentario en 001_schema.sql, sección de privilegios):
-- solo puede cambiar vía una función SECURITY DEFINER, igual que
-- registrar_usuario() e iniciar_sesion() ya hacen con el resto de la
-- lógica sensible.
--
-- Aplicar UNA vez, con el mismo rol que corrió 001_schema.sql (el dueño
-- del esquema, NO nexus360_app):
--   psql "<conexión>" -f db/003_cambiar_password.sql

BEGIN;
SET search_path TO nexus360;

CREATE OR REPLACE FUNCTION nexus360.cambiar_password_usuario(
    p_password_actual TEXT,
    p_password_nueva  TEXT
)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
DECLARE
    v_usuario_id UUID := nexus360.current_usuario_id();
    v_hash       TEXT;
BEGIN
    IF v_usuario_id IS NULL THEN
        RAISE EXCEPTION 'No hay una sesión activa';
    END IF;

    IF p_password_nueva IS NULL OR length(p_password_nueva) < 8 THEN
        RAISE EXCEPTION 'La contraseña debe tener al menos 8 caracteres';
    END IF;

    SELECT password_hash INTO v_hash
      FROM nexus360.usuario
     WHERE usuario_id = v_usuario_id;

    IF v_hash IS NULL OR v_hash <> crypt(p_password_actual, v_hash) THEN
        RAISE EXCEPTION 'La contraseña actual no es correcta';
    END IF;

    UPDATE nexus360.usuario
       SET password_hash = crypt(p_password_nueva, gen_salt('bf', 10))
     WHERE usuario_id = v_usuario_id;
END;
$$;

REVOKE ALL ON FUNCTION nexus360.cambiar_password_usuario(TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION nexus360.cambiar_password_usuario(TEXT, TEXT) TO nexus360_app;

COMMIT;
