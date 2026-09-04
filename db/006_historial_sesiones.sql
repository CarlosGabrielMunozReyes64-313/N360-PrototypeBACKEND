-- 006_historial_sesiones.sql
-- Historial de sesiones legible: por qué se cerró cada una.
--
-- Hasta ahora `sesion.revocado_en` decía CUÁNDO se cerró una sesión pero
-- no QUIÉN la cerró: cerrar_sesion() (el usuario saliendo), 
-- admin_revocar_sesion() (un admin echándolo) y admin_eliminar_usuario()
-- escribían exactamente la misma marca. En un panel de auditoría esa
-- diferencia es justamente lo que se quiere ver, así que se agrega una
-- columna con el motivo.
--
-- Las sesiones cerradas ANTES de aplicar esta migración quedan con
-- revocado_motivo = NULL: el dato no existe y no se inventa. El panel
-- las muestra como "cerrada" sin atribuir causa.
--
-- Aplicar UNA vez, con el rol dueño del esquema (NO nexus360_app):
--   psql "<conexión>" -f db/006_historial_sesiones.sql

BEGIN;
SET search_path TO nexus360;

ALTER TABLE nexus360.sesion
    ADD COLUMN IF NOT EXISTS revocado_motivo TEXT
        CHECK (revocado_motivo IN ('logout', 'admin', 'eliminacion'));

COMMENT ON COLUMN nexus360.sesion.revocado_motivo IS
    'Por qué se cerró: logout = el usuario salió; admin = un admin la revocó; '
    'eliminacion = se eliminó la cuenta. NULL = cerrada antes de 006, o sigue viva.';

-- ---------------------------------------------------------------------
-- 1. Las tres funciones que cierran sesiones, ahora dejando el motivo
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION nexus360.cerrar_sesion(p_token TEXT)
RETURNS VOID
LANGUAGE sql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
    UPDATE nexus360.sesion
       SET revocado_en = now(),
           revocado_motivo = 'logout'
     WHERE token_hash = encode(digest(p_token, 'sha256'), 'hex')
       AND revocado_en IS NULL;
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
       SET revocado_en = now(),
           revocado_motivo = 'admin'
     WHERE sesion_id = p_sesion_id
       AND revocado_en IS NULL;
END;
$$;

-- Misma función de 005, con el motivo agregado en el UPDATE de sesiones.
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

    IF p_usuario_id = v_llamante THEN
        RAISE EXCEPTION 'No puedes eliminar tu propia cuenta';
    END IF;

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

    UPDATE nexus360.sesion s
       SET revocado_en = now(),
           revocado_motivo = 'eliminacion'
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

    DELETE FROM nexus360.usuario u WHERE u.usuario_id = p_usuario_id;

    RETURN 'fisico';
END;
$$;

-- ---------------------------------------------------------------------
-- 2. Listado de sesiones con el motivo
-- ---------------------------------------------------------------------
-- CREATE OR REPLACE no puede cambiar el tipo de retorno de una función
-- que devuelve TABLE, así que hay que soltarla y volverla a crear. El
-- GRANT se pierde con el DROP y se rehace abajo.
DROP FUNCTION IF EXISTS nexus360.admin_listar_sesiones(UUID);

CREATE FUNCTION nexus360.admin_listar_sesiones(p_usuario_id UUID DEFAULT NULL)
RETURNS TABLE (
    sesion_id       UUID,
    usuario_id      UUID,
    creado_en       TIMESTAMPTZ,
    expira_en       TIMESTAMPTZ,
    revocado_en     TIMESTAMPTZ,
    revocado_motivo TEXT,
    ip_origen       INET,
    user_agent      TEXT
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
           s.revocado_motivo, s.ip_origen, s.user_agent
      FROM nexus360.sesion s
     WHERE p_usuario_id IS NULL OR s.usuario_id = p_usuario_id
     ORDER BY s.creado_en DESC
     LIMIT 200;
END;
$$;

-- ---------------------------------------------------------------------
-- 3. Resumen de sesiones por usuario (para la lista del panel)
-- ---------------------------------------------------------------------
-- Evita que el front traiga las 200 sesiones solo para contar cuántas
-- tiene cada quien.
CREATE OR REPLACE FUNCTION nexus360.admin_resumen_sesiones()
RETURNS TABLE (
    usuario_id     UUID,
    total          BIGINT,
    activas        BIGINT,
    ultima_sesion  TIMESTAMPTZ
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
BEGIN
    IF nexus360.rol_usuario_actual() <> 'admin' THEN
        RAISE EXCEPTION 'Solo un administrador puede ver las sesiones';
    END IF;

    RETURN QUERY
    SELECT s.usuario_id,
           count(*)::BIGINT,
           count(*) FILTER (WHERE s.revocado_en IS NULL AND s.expira_en > now())::BIGINT,
           max(s.creado_en)
      FROM nexus360.sesion s
     GROUP BY s.usuario_id;
END;
$$;

-- ---------------------------------------------------------------------
-- 4. Lectura del catálogo de formatos
-- ---------------------------------------------------------------------
-- 001_schema.sql nunca le dio SELECT sobre las tablas de catálogo a
-- nexus360_app (solo sobre usuario, usuario_empresa y las de negocio).
-- Se descubrió al leer la actividad de un usuario: mostrar "Formato 01 ·
-- ISO 26000" en vez del id crudo exige leer `formato`, y la consulta
-- moría con "permission denied for table formato".
--
-- `formato` es catálogo de referencia, sin RLS y sin datos de nadie:
-- darle SELECT no expone nada. Las demás tablas del catálogo
-- (dimension, seccion, pregunta, ancla...) van a necesitar lo mismo
-- cuando existan los endpoints que guardan diagnósticos; se deja para
-- esa migración, no se otorga por adelantado.
GRANT SELECT ON nexus360.formato TO nexus360_app;

REVOKE ALL ON FUNCTION nexus360.cerrar_sesion(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.admin_revocar_sesion(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.admin_eliminar_usuario(UUID, BOOLEAN) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.admin_listar_sesiones(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.admin_resumen_sesiones() FROM PUBLIC;

GRANT EXECUTE ON FUNCTION nexus360.cerrar_sesion(TEXT) TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.admin_revocar_sesion(UUID) TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.admin_eliminar_usuario(UUID, BOOLEAN) TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.admin_listar_sesiones(UUID) TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.admin_resumen_sesiones() TO nexus360_app;

COMMIT;
