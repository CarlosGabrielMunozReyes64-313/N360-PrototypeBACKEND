-- 008_foto_perfil.sql
-- Foto de perfil por usuario.
--
-- Cada cuenta tiene SIEMPRE una foto "predeterminada": no se guarda en la
-- base, la dibuja el front a partir del nombre (iniciales) y del
-- usuario_id (color estable). Esta tabla solo guarda la foto cuando el
-- usuario sube una propia; sin fila aquí = foto predeterminada.
--
-- Tabla aparte (y no una columna BYTEA en `usuario`) a propósito:
--   * `usuario` se lee en cada login, /me y en toda la lista del panel de
--     admin; meter ahí unos KB de imagen por fila encarecería todas esas
--     lecturas sin necesidad.
--   * Los privilegios quedan limpios: nexus360_app no gana UPDATE sobre
--     ninguna columna nueva de `usuario` (ver el blindaje de columnas en
--     001_schema.sql).
--
-- La imagen llega ya normalizada por el backend (re-codificada, cuadrada,
-- máx. 512 px, sin metadatos EXIF/GPS), así que el límite de tamaño de
-- abajo es solo una red de seguridad.
--
-- Aplicar UNA vez, con el rol dueño del esquema (NO nexus360_app):
--   psql "<conexión>" -f db/008_foto_perfil.sql

BEGIN;
SET search_path TO nexus360;

CREATE TABLE IF NOT EXISTS nexus360.usuario_foto (
    usuario_id      UUID PRIMARY KEY
                    REFERENCES nexus360.usuario(usuario_id) ON DELETE CASCADE,
    imagen          BYTEA NOT NULL,
    mime            TEXT  NOT NULL
                    CHECK (mime IN ('image/webp', 'image/jpeg', 'image/png')),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_usuario_foto_tamano CHECK (octet_length(imagen) BETWEEN 1 AND 1048576)
);

COMMENT ON TABLE nexus360.usuario_foto IS
    'Foto de perfil subida por el usuario. Sin fila = foto predeterminada (iniciales, la dibuja el front).';
COMMENT ON COLUMN nexus360.usuario_foto.actualizado_en IS
    'Versión de la foto: el front la usa para invalidar su caché cuando cambia.';

-- ---------------------------------------------------------------------
-- RLS con FORCE, como las tablas de negocio: ninguna función SECURITY
-- DEFINER necesita atravesarla. El borrado en cascada desde `usuario`
-- (borrado físico en admin_eliminar_usuario) no se ve afectado: las
-- acciones de integridad referencial de Postgres ignoran RLS.
-- ---------------------------------------------------------------------
ALTER TABLE nexus360.usuario_foto ENABLE ROW LEVEL SECURITY;
ALTER TABLE nexus360.usuario_foto FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS usuario_foto_select_pol ON nexus360.usuario_foto;
DROP POLICY IF EXISTS usuario_foto_insert_pol ON nexus360.usuario_foto;
DROP POLICY IF EXISTS usuario_foto_update_pol ON nexus360.usuario_foto;
DROP POLICY IF EXISTS usuario_foto_delete_pol ON nexus360.usuario_foto;

-- Ver: la propia foto, o cualquiera si es admin (lista de usuarios).
CREATE POLICY usuario_foto_select_pol ON nexus360.usuario_foto
    FOR SELECT TO nexus360_app
    USING (usuario_id = nexus360.current_usuario_id()
           OR nexus360.rol_usuario_actual() = 'admin');

-- Cambiar o quitar: SOLO la propia. Ni siquiera un admin puede poner o
-- borrar la foto de otra persona.
CREATE POLICY usuario_foto_insert_pol ON nexus360.usuario_foto
    FOR INSERT TO nexus360_app
    WITH CHECK (usuario_id = nexus360.current_usuario_id());

CREATE POLICY usuario_foto_update_pol ON nexus360.usuario_foto
    FOR UPDATE TO nexus360_app
    USING (usuario_id = nexus360.current_usuario_id())
    WITH CHECK (usuario_id = nexus360.current_usuario_id());

CREATE POLICY usuario_foto_delete_pol ON nexus360.usuario_foto
    FOR DELETE TO nexus360_app
    USING (usuario_id = nexus360.current_usuario_id());

REVOKE ALL ON nexus360.usuario_foto FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON nexus360.usuario_foto TO nexus360_app;

COMMIT;
