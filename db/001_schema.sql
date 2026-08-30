-- =====================================================================
-- NEXUS 360°  ·  Esquema PostgreSQL para el prototipo "RSE express"  (v3)
-- Diagnósticos: ISO 26000 (Formato 01) y Ley 2173 (Formato 02)
-- Basado en el frontend N360-Prototype (src/types.ts, data/*, engine/scoring.ts)
--
-- v3 corrige, respecto a v2:
--   [ROJO] usuario_empresa no tenía RLS -> cualquier usuario podía
--          auto-vincularse a una empresa ajena conociendo su UUID.
--          Ahora tiene RLS: solo un admin (o el trigger interno de
--          auto-alta) puede insertar filas ahí.
--   [ROJO] usuario no tenía RLS -> cualquier usuario podía hacer
--          UPDATE usuario SET rol='admin' WHERE usuario_id = el suyo.
--          Ahora tiene RLS + la columna rol queda revocada del rol de
--          aplicación; cambiar de rol exige la función
--          cambiar_rol_usuario(), que solo un admin puede ejecutar.
--   [AMARILLO->RESUELTO] alta de la primera empresa (huevo y gallina):
--          la política de empresa se separó en SELECT/UPDATE (exige
--          empresa_visible) e INSERT (solo exige sesión autenticada);
--          un trigger AFTER INSERT crea automáticamente el vínculo en
--          usuario_empresa para quien la creó.
--   [NUEVO] sistema de login/registro completo: tabla usuario ampliada
--          (password_hash, bloqueo por intentos fallidos), tabla sesion
--          (tokens de sesión, nunca en texto plano), y funciones
--          registrar_usuario / iniciar_sesion / cerrar_sesion /
--          validar_sesion / cambiar_rol_usuario, todas SECURITY DEFINER.
--
-- Todo lo de v2 (triggers de suma de pesos, índices únicos parciales,
-- FK a nivel_escala, evidencia_nivel3, ON DELETE) se conserva sin
-- cambios: fue probado y confirmado correcto.
-- =====================================================================
-- Convenciones:
--   * Soft delete: archivado_en TIMESTAMPTZ (NULL = vigente).
--   * valor de respuesta: 0-4 (escala de madurez) o NULL = "NA".
--   * DISEÑO DE SEGURIDAD CLAVE: usuario, usuario_empresa y sesion
--     tienen RLS habilitado pero SIN FORCE. Esto es intencional: las
--     funciones SECURITY DEFINER de autenticación (registrar_usuario,
--     iniciar_sesion, el trigger de auto-vinculación) son dueñas de la
--     tabla y así "atraviesan" el RLS para hacer su trabajo interno sin
--     necesitar privilegios adicionales -- pero el rol de aplicación
--     (no dueño) sigue 100% sujeto a las políticas cuando consulta esas
--     tablas directamente. Las tablas de negocio (empresa, diagnostico,
--     respuesta, evidencia) sí llevan FORCE, porque nada necesita
--     atravesarlas por dentro.
-- =====================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS nexus360;
SET search_path TO nexus360;

CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- crypt(), gen_salt(), gen_random_bytes(), digest()

-- ---------------------------------------------------------------------
-- 0. ROL DE APLICACIÓN
-- ---------------------------------------------------------------------
-- El backend NUNCA debe conectarse como el dueño de las tablas (quien
-- corre este script). Debe conectarse como nexus360_app, que queda
-- sujeto a RLS y a los REVOKE de columnas/tablas de más abajo.
-- Fija la contraseña por fuera de este script (ALTER ROLE ... PASSWORD).

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexus360_app') THEN
        CREATE ROLE nexus360_app LOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA nexus360 TO nexus360_app;

-- ---------------------------------------------------------------------
-- 1. CATÁLOGOS
-- ---------------------------------------------------------------------

CREATE TABLE sector (
    sector_id       TEXT PRIMARY KEY,
    nombre          TEXT NOT NULL
);

INSERT INTO sector (sector_id, nombre) VALUES
    ('industrial',     'Industrial'),
    ('servicios',      'Servicios'),
    ('agroindustrial', 'Agroindustrial'),
    ('comercio',        'Comercio'),
    ('energia',        'Energía / Combustibles'),
    ('movilidad',      'Movilidad');

CREATE TABLE arquetipo (
    arquetipo_id    CHAR(1) PRIMARY KEY,
    nombre          TEXT NOT NULL,
    verbo           TEXT NOT NULL
);

INSERT INTO arquetipo (arquetipo_id, nombre, verbo) VALUES
    ('A', 'Estructura',   'Formalizar'),
    ('B', 'Línea base',   'Calcular y certificar'),
    ('C', 'Trámite',      'Radicar'),
    ('D', 'Instrumento',  'Formular'),
    ('E', 'Ejecución',    'Ejecutar y registrar');

CREATE TABLE nivel_escala (
    valor           SMALLINT PRIMARY KEY CHECK (valor BETWEEN 0 AND 4),
    etiqueta        TEXT NOT NULL
);

INSERT INTO nivel_escala (valor, etiqueta) VALUES
    (0, 'Sin gestión'),
    (1, 'Informal'),
    (2, 'Planificado'),
    (3, 'Implementado y medido'),
    (4, 'Mejora continua');

CREATE TABLE ancla (
    arquetipo_id    CHAR(1) NOT NULL REFERENCES arquetipo(arquetipo_id) ON DELETE CASCADE,
    valor           SMALLINT NOT NULL REFERENCES nivel_escala(valor) ON DELETE CASCADE,
    texto           TEXT NOT NULL,
    PRIMARY KEY (arquetipo_id, valor)
);

-- ---------------------------------------------------------------------
-- 2. USUARIOS, SESIONES (login / registro)
-- ---------------------------------------------------------------------

CREATE TABLE usuario (
    usuario_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               CITEXT NOT NULL,
    nombre              TEXT NOT NULL,
    rol                 TEXT NOT NULL CHECK (rol IN ('empresa', 'admin')),
    password_hash       TEXT NOT NULL,
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    email_verificado_en TIMESTAMPTZ,
    intentos_fallidos   SMALLINT NOT NULL DEFAULT 0,
    bloqueado_hasta     TIMESTAMPTZ,
    ultimo_login_en     TIMESTAMPTZ,
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    archivado_en        TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_usuario_email ON usuario (email) WHERE archivado_en IS NULL;

-- Tokens de sesión: solo se guarda el HASH del token, nunca el token
-- crudo (igual que la contraseña). El token real solo lo tiene el
-- cliente (cookie/localStorage) entre iniciar_sesion() y cerrar_sesion().
CREATE TABLE sesion (
    sesion_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id      UUID NOT NULL REFERENCES usuario(usuario_id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_en       TIMESTAMPTZ NOT NULL,
    revocado_en     TIMESTAMPTZ,
    ip_origen       INET,
    user_agent      TEXT
);

CREATE UNIQUE INDEX uq_sesion_token ON sesion (token_hash);
CREATE INDEX idx_sesion_usuario ON sesion (usuario_id) WHERE revocado_en IS NULL;

-- Relación N:M usuario<->empresa. empresa_id se agrega como FK real más
-- abajo, una vez que la tabla empresa existe.
CREATE TABLE usuario_empresa (
    usuario_id      UUID NOT NULL REFERENCES usuario(usuario_id) ON DELETE CASCADE,
    empresa_id      UUID NOT NULL,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (usuario_id, empresa_id)
);

-- ---------------------------------------------------------------------
-- 3. EMPRESA Y TAMIZAJE (paso 1 y 2 del frontend)
-- ---------------------------------------------------------------------

CREATE TABLE empresa (
    empresa_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    razon_social    TEXT NOT NULL,
    nit             VARCHAR(15) NOT NULL,
    dv              CHAR(1)     NOT NULL,
    sector_id       TEXT NOT NULL REFERENCES sector(sector_id) ON DELETE RESTRICT,
    municipio       TEXT NOT NULL,
    departamento    TEXT,
    extranjera      BOOLEAN NOT NULL DEFAULT FALSE,
    -- [ROJO-fix] quién la creó. Resuelve un problema real encontrado en
    -- pruebas: INSERT ... RETURNING exige que la fila nueva TAMBIÉN pase
    -- la política de SELECT para poder devolverla, y en ese instante el
    -- trigger que vincula usuario_empresa (AFTER INSERT) todavía no ha
    -- corrido -- los triggers AFTER se disparan al terminar la sentencia,
    -- después de que RETURNING ya se evaluó. Con creado_por, la política
    -- de SELECT/UPDATE de "empresa" se resuelve leyendo la propia fila,
    -- sin depender de que el trigger ya haya escrito en otra tabla.
    creado_por      UUID REFERENCES usuario(usuario_id) ON DELETE SET NULL,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    archivado_en    TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_empresa_nit ON empresa (nit, dv) WHERE archivado_en IS NULL;

ALTER TABLE usuario_empresa
    ADD CONSTRAINT fk_usuario_empresa_empresa
        FOREIGN KEY (empresa_id) REFERENCES empresa(empresa_id) ON DELETE CASCADE;

CREATE OR REPLACE FUNCTION nexus360.calcular_dv(p_nit TEXT)
RETURNS CHAR(1) AS $$
DECLARE
    limpio   TEXT := regexp_replace(p_nit, '\D', '', 'g');
    pesos    INT[] := ARRAY[3,7,13,17,19,23,29,37,41,43,47,53,59,67,71];
    suma     INT := 0;
    i        INT;
    r        INT;
BEGIN
    IF length(limpio) < 5 OR length(limpio) > 15 THEN
        RETURN NULL;
    END IF;
    FOR i IN 1..length(limpio) LOOP
        suma := suma + substr(reverse(limpio), i, 1)::INT * pesos[i];
    END LOOP;
    r := suma % 11;
    RETURN (CASE WHEN r > 1 THEN 11 - r ELSE r END)::TEXT;
END;
$$ LANGUAGE plpgsql IMMUTABLE SET search_path = nexus360, extensions, pg_temp;

ALTER TABLE empresa
    ADD CONSTRAINT chk_empresa_dv CHECK (dv = nexus360.calcular_dv(nit));

CREATE TABLE ciclo_tamizaje (
    ciclo_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id          UUID NOT NULL REFERENCES empresa(empresa_id) ON DELETE RESTRICT,
    anio                SMALLINT NOT NULL,
    tamano              TEXT NOT NULL CHECK (tamano IN ('micro','pequena','mediana','grande')),
    empleados           INTEGER NOT NULL CHECK (empleados > 0),
    areas_de_vida       TEXT NOT NULL CHECK (areas_de_vida IN ('si','no','nose')),
    ciclo_previo        BOOLEAN NOT NULL,
    comunidades_etnicas BOOLEAN NOT NULL,
    consumidor_final    BOOLEAN NOT NULL,
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_ciclo_empresa_anio UNIQUE (empresa_id, anio)
);

-- ---------------------------------------------------------------------
-- 4. FORMATOS, DIMENSIONES, SECCIONES, PREGUNTAS (catálogo normativo)
-- ---------------------------------------------------------------------

CREATE TABLE formato (
    formato_id      TEXT PRIMARY KEY,
    codigo          TEXT NOT NULL,
    nombre          TEXT NOT NULL,
    norma           TEXT NOT NULL,
    naturaleza      TEXT NOT NULL,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    archivado_en    TIMESTAMPTZ
);

CREATE TABLE dimension (
    dimension_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    formato_id      TEXT NOT NULL REFERENCES formato(formato_id) ON DELETE RESTRICT,
    numero          TEXT NOT NULL,
    nombre          TEXT NOT NULL,
    abrev           TEXT NOT NULL,
    descripcion     TEXT,
    peso            NUMERIC(4,3) CHECK (peso IS NULL OR peso BETWEEN 0 AND 1),
    condicional     TEXT CHECK (condicional IS NULL OR condicional = 'requiereAreasDeVida'),
    archivado_en    TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_dimension ON dimension (formato_id, numero) WHERE archivado_en IS NULL;

CREATE TABLE seccion (
    seccion_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dimension_id    UUID NOT NULL REFERENCES dimension(dimension_id) ON DELETE CASCADE,
    nombre          TEXT,
    peso            NUMERIC(4,3) NOT NULL CHECK (peso BETWEEN 0 AND 1),
    condicional     TEXT CHECK (condicional IS NULL OR condicional = 'requiereAreasDeVida'),
    archivado_en    TIMESTAMPTZ
);

CREATE TABLE pregunta (
    pregunta_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo              TEXT NOT NULL,
    seccion_id          UUID NOT NULL REFERENCES seccion(seccion_id) ON DELETE CASCADE,
    arquetipo_id        CHAR(1) NOT NULL REFERENCES arquetipo(arquetipo_id) ON DELETE RESTRICT,
    texto               TEXT NOT NULL,
    peso                NUMERIC(4,3) NOT NULL CHECK (peso BETWEEN 0 AND 1),
    evidencia_nivel3    TEXT,
    accion              TEXT NOT NULL,
    archivado_en        TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_pregunta_codigo ON pregunta (seccion_id, codigo) WHERE archivado_en IS NULL;

CREATE TABLE peso_sector_materia (
    sector_id       TEXT NOT NULL REFERENCES sector(sector_id) ON DELETE RESTRICT,
    dimension_id    UUID NOT NULL REFERENCES dimension(dimension_id) ON DELETE CASCADE,
    peso            NUMERIC(4,3) NOT NULL CHECK (peso BETWEEN 0 AND 1),
    PRIMARY KEY (sector_id, dimension_id)
);

-- --- Triggers: Σ peso = 1.0 EXACTO por nivel (deferred, con tolerancia) ---

CREATE OR REPLACE FUNCTION nexus360.validar_suma_pesos_secciones()
RETURNS TRIGGER AS $$
DECLARE
    v_dimension_id UUID := COALESCE(NEW.dimension_id, OLD.dimension_id);
    total NUMERIC;
BEGIN
    SELECT COALESCE(SUM(peso),0) INTO total FROM nexus360.seccion
    WHERE dimension_id = v_dimension_id AND archivado_en IS NULL;
    IF total <> 0 AND abs(total - 1.0) > 0.001 THEN
        RAISE EXCEPTION 'Las secciones vigentes de la dimensión % suman % (debe ser 1.0)', v_dimension_id, total;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SET search_path = nexus360, extensions, pg_temp;

CREATE CONSTRAINT TRIGGER trg_suma_pesos_secciones
    AFTER INSERT OR UPDATE OR DELETE ON seccion
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION nexus360.validar_suma_pesos_secciones();

CREATE OR REPLACE FUNCTION nexus360.validar_suma_pesos_preguntas()
RETURNS TRIGGER AS $$
DECLARE
    v_seccion_id UUID := COALESCE(NEW.seccion_id, OLD.seccion_id);
    total NUMERIC;
BEGIN
    SELECT COALESCE(SUM(peso),0) INTO total FROM nexus360.pregunta
    WHERE seccion_id = v_seccion_id AND archivado_en IS NULL;
    IF total <> 0 AND abs(total - 1.0) > 0.001 THEN
        RAISE EXCEPTION 'Las preguntas vigentes de la sección % suman % (debe ser 1.0)', v_seccion_id, total;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SET search_path = nexus360, extensions, pg_temp;

CREATE CONSTRAINT TRIGGER trg_suma_pesos_preguntas
    AFTER INSERT OR UPDATE OR DELETE ON pregunta
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION nexus360.validar_suma_pesos_preguntas();

CREATE OR REPLACE FUNCTION nexus360.validar_suma_pesos_dimension()
RETURNS TRIGGER AS $$
DECLARE
    v_formato_id TEXT := COALESCE(NEW.formato_id, OLD.formato_id);
    total   NUMERIC;
    n_null  INT;
BEGIN
    SELECT COALESCE(SUM(peso),0), COUNT(*) FILTER (WHERE peso IS NULL)
      INTO total, n_null
      FROM nexus360.dimension
     WHERE formato_id = v_formato_id AND archivado_en IS NULL;
    IF n_null = 0 AND total <> 0 AND abs(total - 1.0) > 0.001 THEN
        RAISE EXCEPTION 'Las dimensiones vigentes del formato % suman % (debe ser 1.0)', v_formato_id, total;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SET search_path = nexus360, extensions, pg_temp;

CREATE CONSTRAINT TRIGGER trg_suma_pesos_dimension
    AFTER INSERT OR UPDATE OR DELETE ON dimension
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION nexus360.validar_suma_pesos_dimension();

CREATE OR REPLACE FUNCTION nexus360.validar_suma_pesos_sector()
RETURNS TRIGGER AS $$
DECLARE
    v_sector_id TEXT := COALESCE(NEW.sector_id, OLD.sector_id);
    total NUMERIC;
BEGIN
    SELECT COALESCE(SUM(peso),0) INTO total FROM nexus360.peso_sector_materia
    WHERE sector_id = v_sector_id;
    IF total <> 0 AND abs(total - 1.0) > 0.001 THEN
        RAISE EXCEPTION 'Los pesos de materia del sector % suman % (debe ser 1.0)', v_sector_id, total;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SET search_path = nexus360, extensions, pg_temp;

CREATE CONSTRAINT TRIGGER trg_suma_pesos_sector
    AFTER INSERT OR UPDATE OR DELETE ON peso_sector_materia
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION nexus360.validar_suma_pesos_sector();

-- ---------------------------------------------------------------------
-- 5. DIAGNÓSTICO, RESPUESTA, EVIDENCIA
-- ---------------------------------------------------------------------

CREATE TABLE diagnostico (
    diagnostico_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id      UUID NOT NULL REFERENCES empresa(empresa_id) ON DELETE RESTRICT,
    ciclo_id        UUID NOT NULL REFERENCES ciclo_tamizaje(ciclo_id) ON DELETE RESTRICT,
    formato_id      TEXT NOT NULL REFERENCES formato(formato_id) ON DELETE RESTRICT,
    estado          TEXT NOT NULL DEFAULT 'borrador'
                        CHECK (estado IN ('borrador','completado','archivado')),
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completado_en   TIMESTAMPTZ,
    archivado_en    TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_diagnostico_borrador
    ON diagnostico (empresa_id, ciclo_id, formato_id)
    WHERE estado = 'borrador';

CREATE TABLE respuesta (
    respuesta_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    diagnostico_id  UUID NOT NULL REFERENCES diagnostico(diagnostico_id) ON DELETE CASCADE,
    pregunta_id     UUID NOT NULL REFERENCES pregunta(pregunta_id) ON DELETE RESTRICT,
    valor           SMALLINT REFERENCES nivel_escala(valor),
    es_na           BOOLEAN NOT NULL DEFAULT FALSE,
    respondido_en   TIMESTAMPTZ NOT NULL DEFAULT now(),
    respondido_por  UUID REFERENCES usuario(usuario_id) ON DELETE SET NULL,
    CONSTRAINT uq_respuesta UNIQUE (diagnostico_id, pregunta_id),
    CONSTRAINT chk_valor_o_na CHECK (
        (es_na = TRUE  AND valor IS NULL) OR
        (es_na = FALSE AND valor IS NOT NULL)
    )
);

CREATE TABLE evidencia (
    evidencia_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    respuesta_id    UUID NOT NULL REFERENCES respuesta(respuesta_id) ON DELETE CASCADE,
    ruta_archivo    TEXT NOT NULL,
    hash_sha256     CHAR(64) NOT NULL,
    cargado_en      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 6. ÍNDICES DE APOYO
-- ---------------------------------------------------------------------

CREATE INDEX idx_empresa_nit           ON empresa (nit);
CREATE INDEX idx_ciclo_empresa         ON ciclo_tamizaje (empresa_id);
CREATE INDEX idx_dimension_formato     ON dimension (formato_id) WHERE archivado_en IS NULL;
CREATE INDEX idx_seccion_dimension     ON seccion (dimension_id) WHERE archivado_en IS NULL;
CREATE INDEX idx_pregunta_seccion      ON pregunta (seccion_id) WHERE archivado_en IS NULL;
CREATE INDEX idx_diagnostico_empresa   ON diagnostico (empresa_id, ciclo_id);
CREATE INDEX idx_respuesta_diagnostico ON respuesta (diagnostico_id);
CREATE INDEX idx_usuario_empresa_emp   ON usuario_empresa (empresa_id);

-- =======================================================================
-- 7. FUNCIONES DE APOYO A RLS (deben crearse ANTES que las políticas)
-- =======================================================================

-- Lee el usuario autenticado de la sesión de base de datos actual. El
-- backend debe ejecutar, tras validar el token con validar_sesion():
--   SET app.current_usuario_id = '<uuid>';
CREATE OR REPLACE FUNCTION nexus360.current_usuario_id()
RETURNS UUID
LANGUAGE sql STABLE
AS $$
    SELECT NULLIF(current_setting('app.current_usuario_id', true), '')::UUID;
$$;

-- [ROJO-usuario] SECURITY DEFINER + dueño de la tabla + usuario SIN
-- FORCE ROW LEVEL SECURITY = esta función lee el rol real sin pasar por
-- la política de "usuario" (evita la recursión de que la política de
-- usuario dependa de una consulta a usuario) y sin que el rol de
-- aplicación necesite privilegios directos sobre la tabla.
CREATE OR REPLACE FUNCTION nexus360.rol_usuario_actual()
RETURNS TEXT
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
    SELECT rol FROM nexus360.usuario
     WHERE usuario_id = nexus360.current_usuario_id()
       AND activo AND archivado_en IS NULL;
$$;

REVOKE ALL ON FUNCTION nexus360.rol_usuario_actual() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION nexus360.rol_usuario_actual() TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.current_usuario_id() TO nexus360_app;

ALTER TABLE empresa ALTER COLUMN creado_por SET DEFAULT nexus360.current_usuario_id();

-- ¿El usuario en sesión puede ver/editar esta empresa? Admin ve todo;
-- el resto solo si existe su vínculo en usuario_empresa. Se ejecuta con
-- los privilegios del invocador (no SECURITY DEFINER): la subconsulta a
-- usuario_empresa queda sujeta a la política de esa tabla, pero como
-- ahí solo se pregunta "¿existe un vínculo con MI propio usuario_id?",
-- la propia política de usuario_empresa (ver más abajo) ya lo permite.
CREATE OR REPLACE FUNCTION nexus360.empresa_visible(p_empresa_id UUID)
RETURNS BOOLEAN
LANGUAGE sql STABLE
SET search_path = nexus360, extensions, pg_temp
AS $$
    SELECT nexus360.rol_usuario_actual() = 'admin'
        OR EXISTS (
            SELECT 1 FROM nexus360.empresa e
             WHERE e.empresa_id = p_empresa_id
               AND e.creado_por = nexus360.current_usuario_id()
        )
        OR EXISTS (
            SELECT 1 FROM nexus360.usuario_empresa ue
             WHERE ue.usuario_id = nexus360.current_usuario_id()
               AND ue.empresa_id = p_empresa_id
        );
$$;

GRANT EXECUTE ON FUNCTION nexus360.empresa_visible(UUID) TO nexus360_app;

-- =======================================================================
-- 8. RLS: usuario, sesion, usuario_empresa
--    [ROJO] estas tres tablas NO llevaban RLS en v2. Son las que
--    deciden "quién es quién" y "quién ve qué empresa" -- el hueco más
--    sensible. Nota: NO llevan FORCE (ver comentario de diseño arriba).
-- =======================================================================

ALTER TABLE usuario         ENABLE ROW LEVEL SECURITY;
ALTER TABLE sesion          ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuario_empresa ENABLE ROW LEVEL SECURITY;

-- usuario: cada quien ve/edita su propia fila; admin ve/edita todas.
-- No hay política de INSERT ni DELETE -> quedan denegados por defecto
-- para nexus360_app; el alta real ocurre solo vía registrar_usuario().
CREATE POLICY usuario_select_pol ON usuario
    FOR SELECT
    USING (usuario_id = nexus360.current_usuario_id() OR nexus360.rol_usuario_actual() = 'admin');

CREATE POLICY usuario_update_pol ON usuario
    FOR UPDATE
    USING (usuario_id = nexus360.current_usuario_id() OR nexus360.rol_usuario_actual() = 'admin')
    WITH CHECK (usuario_id = nexus360.current_usuario_id() OR nexus360.rol_usuario_actual() = 'admin');

-- sesion: sin políticas de ningún tipo -> nexus360_app no puede leer ni
-- escribir esta tabla directamente jamás. Solo las funciones SECURITY
-- DEFINER (dueñas de la tabla, sin FORCE) pueden tocarla.

-- usuario_empresa: cada quien ve sus propios vínculos; admin ve todos.
-- [ROJO-fix clave] INSERT y DELETE exigen admin explícitamente. La
-- auto-vinculación al crear una empresa NO pasa por esta política: la
-- hace un trigger SECURITY DEFINER (sección 9) que, al ser dueño de la
-- tabla y no haber FORCE, la atraviesa igual que las funciones de auth.
CREATE POLICY usuario_empresa_select_pol ON usuario_empresa
    FOR SELECT
    USING (usuario_id = nexus360.current_usuario_id() OR nexus360.rol_usuario_actual() = 'admin');

CREATE POLICY usuario_empresa_insert_pol ON usuario_empresa
    FOR INSERT
    WITH CHECK (nexus360.rol_usuario_actual() = 'admin');

CREATE POLICY usuario_empresa_delete_pol ON usuario_empresa
    FOR DELETE
    USING (nexus360.rol_usuario_actual() = 'admin');

-- --- Blindaje a nivel de privilegios (defensa en profundidad, no solo RLS) ---

REVOKE ALL ON usuario, sesion, usuario_empresa FROM nexus360_app;
GRANT SELECT ON usuario TO nexus360_app;
-- [ROJO-fix clave, corregido tras pruebas] En Postgres, GRANT UPDATE a
-- nivel de TABLA no se puede "recortar" después con REVOKE UPDATE (columna):
-- son ACL independientes, y el REVOKE de columna solo afecta privilegios
-- de columna otorgados explícitamente -- nunca al grant de tabla completa.
-- (Esto se probó: con GRANT SELECT,UPDATE ON usuario + REVOKE UPDATE(rol),
-- un usuario común pudo hacer UPDATE usuario SET rol='admin' igual.)
-- La forma correcta es otorgar UPDATE solo sobre las columnas permitidas,
-- nunca a nivel de tabla completa. rol, password_hash, intentos_fallidos,
-- bloqueado_hasta y ultimo_login_en quedan fuera: esas solo cambian via
-- cambiar_rol_usuario() / registrar_usuario() / iniciar_sesion(), todas
-- SECURITY DEFINER.
GRANT UPDATE (email, nombre, activo, archivado_en) ON usuario TO nexus360_app;
GRANT SELECT, INSERT, DELETE ON usuario_empresa TO nexus360_app;
-- (sesion: nada de nada para nexus360_app; todo pasa por las funciones)

-- =======================================================================
-- 9. TABLAS DE NEGOCIO: RLS con FORCE (empresa, ciclo, diagnóstico...)
-- =======================================================================

ALTER TABLE empresa        ENABLE ROW LEVEL SECURITY;
ALTER TABLE ciclo_tamizaje ENABLE ROW LEVEL SECURITY;
ALTER TABLE diagnostico    ENABLE ROW LEVEL SECURITY;
ALTER TABLE respuesta      ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidencia      ENABLE ROW LEVEL SECURITY;

ALTER TABLE empresa        FORCE ROW LEVEL SECURITY;
ALTER TABLE ciclo_tamizaje FORCE ROW LEVEL SECURITY;
ALTER TABLE diagnostico    FORCE ROW LEVEL SECURITY;
ALTER TABLE respuesta      FORCE ROW LEVEL SECURITY;
ALTER TABLE evidencia      FORCE ROW LEVEL SECURITY;

-- [AMARILLO-fix clave] empresa separa INSERT de SELECT/UPDATE: crear una
-- empresa solo exige tener sesión (no exige ya pertenecer a ella, porque
-- todavía no puede pertenecer a nada). Ver/editar exige ser quien la creó,
-- ser admin, o tener un vínculo en usuario_empresa.
--
-- Nota de diseño: aquí SÍ referenciamos la columna creado_por de la
-- propia fila en vez de llamar a empresa_visible() (que internamente
-- consulta la tabla empresa) -- llamar a esa función desde la propia
-- política de empresa sería una subconsulta recursiva sobre la misma
-- tabla. Comparar la columna de la fila candidata no lo es.
CREATE POLICY empresa_select_pol ON empresa
    FOR SELECT
    USING (
        creado_por = nexus360.current_usuario_id()
        OR nexus360.rol_usuario_actual() = 'admin'
        OR EXISTS (
            SELECT 1 FROM nexus360.usuario_empresa ue
             WHERE ue.usuario_id = nexus360.current_usuario_id()
               AND ue.empresa_id = empresa.empresa_id
        )
    );

CREATE POLICY empresa_update_pol ON empresa
    FOR UPDATE
    USING (
        creado_por = nexus360.current_usuario_id()
        OR nexus360.rol_usuario_actual() = 'admin'
        OR EXISTS (
            SELECT 1 FROM nexus360.usuario_empresa ue
             WHERE ue.usuario_id = nexus360.current_usuario_id()
               AND ue.empresa_id = empresa.empresa_id
        )
    )
    WITH CHECK (
        creado_por = nexus360.current_usuario_id()
        OR nexus360.rol_usuario_actual() = 'admin'
        OR EXISTS (
            SELECT 1 FROM nexus360.usuario_empresa ue
             WHERE ue.usuario_id = nexus360.current_usuario_id()
               AND ue.empresa_id = empresa.empresa_id
        )
    );

-- current_usuario_id() IS NOT NULL ya no es suficiente por sí solo: se
-- exige además que la fila declare como creador a quien la está
-- insertando (el DEFAULT de la columna ya lo hace automáticamente; esto
-- bloquea que alguien intente forzar creado_por a otro usuario).
CREATE POLICY empresa_insert_pol ON empresa
    FOR INSERT
    WITH CHECK (
        nexus360.current_usuario_id() IS NOT NULL
        AND creado_por = nexus360.current_usuario_id()
    );
-- (sin política de DELETE: se archiva, nunca se borra en duro desde la app)

CREATE POLICY ciclo_visible_pol ON ciclo_tamizaje
    USING (nexus360.empresa_visible(empresa_id))
    WITH CHECK (nexus360.empresa_visible(empresa_id));

CREATE POLICY diagnostico_visible_pol ON diagnostico
    USING (nexus360.empresa_visible(empresa_id))
    WITH CHECK (nexus360.empresa_visible(empresa_id));

CREATE POLICY respuesta_visible_pol ON respuesta
    USING (EXISTS (
        SELECT 1 FROM nexus360.diagnostico d
         WHERE d.diagnostico_id = respuesta.diagnostico_id
           AND nexus360.empresa_visible(d.empresa_id)
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM nexus360.diagnostico d
         WHERE d.diagnostico_id = respuesta.diagnostico_id
           AND nexus360.empresa_visible(d.empresa_id)
    ));

CREATE POLICY evidencia_visible_pol ON evidencia
    USING (EXISTS (
        SELECT 1 FROM nexus360.respuesta r
          JOIN nexus360.diagnostico d ON d.diagnostico_id = r.diagnostico_id
         WHERE r.respuesta_id = evidencia.respuesta_id
           AND nexus360.empresa_visible(d.empresa_id)
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM nexus360.respuesta r
          JOIN nexus360.diagnostico d ON d.diagnostico_id = r.diagnostico_id
         WHERE r.respuesta_id = evidencia.respuesta_id
           AND nexus360.empresa_visible(d.empresa_id)
    ));

GRANT SELECT, INSERT, UPDATE ON empresa, ciclo_tamizaje, diagnostico, respuesta, evidencia TO nexus360_app;
-- creado_por se fija solo al crear (vía DEFAULT); nadie puede reescribirlo
-- después, ni siquiera el propio creador o un admin por esta vía.
REVOKE UPDATE (creado_por) ON empresa FROM nexus360_app;

-- [AMARILLO-fix clave] trigger de auto-alta: crea el vínculo en
-- usuario_empresa apenas se crea la empresa, resolviendo el huevo y la
-- gallina sin abrir usuario_empresa a inserciones libres.
CREATE OR REPLACE FUNCTION nexus360.auto_vincular_usuario_empresa()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
BEGIN
    IF nexus360.current_usuario_id() IS NOT NULL THEN
        INSERT INTO nexus360.usuario_empresa (usuario_id, empresa_id)
        VALUES (nexus360.current_usuario_id(), NEW.empresa_id)
        ON CONFLICT DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_auto_vincular_usuario_empresa
    AFTER INSERT ON empresa
    FOR EACH ROW EXECUTE FUNCTION nexus360.auto_vincular_usuario_empresa();

-- =======================================================================
-- 10. LOGIN / REGISTRO
-- =======================================================================

-- Alta de cuenta nueva. El rol queda SIEMPRE fijo en 'empresa': el
-- endpoint de registro no admite ni recibe un parámetro de rol, así que
-- es estructuralmente imposible auto-registrarse como admin. Un admin
-- solo se crea llamando cambiar_rol_usuario() desde otra cuenta admin.
CREATE OR REPLACE FUNCTION nexus360.registrar_usuario(
    p_email    CITEXT,
    p_password TEXT,
    p_nombre   TEXT
)
RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
DECLARE
    v_usuario_id UUID;
BEGIN
    IF p_password IS NULL OR length(p_password) < 8 THEN
        RAISE EXCEPTION 'La contraseña debe tener al menos 8 caracteres';
    END IF;
    IF p_email IS NULL OR p_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' THEN
        RAISE EXCEPTION 'Correo electrónico inválido';
    END IF;

    INSERT INTO nexus360.usuario (email, nombre, rol, password_hash)
    VALUES (p_email, p_nombre, 'empresa', crypt(p_password, gen_salt('bf', 10)))
    RETURNING usuario_id INTO v_usuario_id;

    RETURN v_usuario_id;
EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION 'Ya existe una cuenta registrada con ese correo';
END;
$$;

-- Login: valida credenciales, aplica bloqueo tras 5 intentos fallidos
-- (15 minutos), y emite un token de sesión de 12 horas. Devuelve el
-- token EN CLARO una sola vez (el backend se lo entrega al cliente);
-- en la tabla sesion solo queda su hash SHA-256.
CREATE OR REPLACE FUNCTION nexus360.iniciar_sesion(
    p_email      CITEXT,
    p_password   TEXT,
    p_ip         INET DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL
)
RETURNS TABLE (usuario_id UUID, rol TEXT, token TEXT, expira_en TIMESTAMPTZ, error TEXT)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
DECLARE
    v_usuario  nexus360.usuario%ROWTYPE;
    v_token    TEXT;
    v_expira   TIMESTAMPTZ := now() + interval '12 hours';
BEGIN
    -- IMPORTANTE: esta función NUNCA usa RAISE EXCEPTION para "credenciales
    -- inválidas" ni "cuenta bloqueada". Si lo hiciera, el RAISE abortaría
    -- TODA la transacción de este statement, deshaciendo también el UPDATE
    -- de intentos_fallidos que se acababa de ejecutar un instante antes
    -- (así se descubrió en pruebas: el contador nunca pasaba de 0). En vez
    -- de eso, se devuelve una fila con columnas en NULL + 'error' explicando
    -- el motivo, y esa fila sí queda dentro de la transacción exitosa.
    SELECT * INTO v_usuario FROM nexus360.usuario u
     WHERE u.email = p_email AND u.archivado_en IS NULL;

    IF NOT FOUND THEN
        RETURN QUERY SELECT NULL::UUID, NULL::TEXT, NULL::TEXT, NULL::TIMESTAMPTZ, 'credenciales_invalidas'::TEXT;
        RETURN;
    END IF;

    IF v_usuario.bloqueado_hasta IS NOT NULL AND v_usuario.bloqueado_hasta > now() THEN
        RETURN QUERY SELECT NULL::UUID, NULL::TEXT, NULL::TEXT, NULL::TIMESTAMPTZ, 'cuenta_bloqueada'::TEXT;
        RETURN;
    END IF;

    IF NOT v_usuario.activo OR v_usuario.password_hash <> crypt(p_password, v_usuario.password_hash) THEN
        UPDATE nexus360.usuario u
           SET intentos_fallidos = u.intentos_fallidos + 1,
               bloqueado_hasta = CASE WHEN u.intentos_fallidos + 1 >= 5
                                      THEN now() + interval '15 minutes'
                                      ELSE u.bloqueado_hasta END
         WHERE u.usuario_id = v_usuario.usuario_id;
        RETURN QUERY SELECT NULL::UUID, NULL::TEXT, NULL::TEXT, NULL::TIMESTAMPTZ, 'credenciales_invalidas'::TEXT;
        RETURN;
    END IF;

    UPDATE nexus360.usuario u
       SET intentos_fallidos = 0, bloqueado_hasta = NULL, ultimo_login_en = now()
     WHERE u.usuario_id = v_usuario.usuario_id;

    v_token := encode(gen_random_bytes(32), 'hex');

    INSERT INTO nexus360.sesion (usuario_id, token_hash, expira_en, ip_origen, user_agent)
    VALUES (v_usuario.usuario_id, encode(digest(v_token, 'sha256'), 'hex'), v_expira, p_ip, p_user_agent);

    RETURN QUERY SELECT v_usuario.usuario_id, v_usuario.rol, v_token, v_expira, NULL::TEXT;
END;
$$;

-- El backend llama esto en cada request (con el token de la cookie/
-- header) para resolver el usuario_id, y luego hace:
--   SET app.current_usuario_id = '<uuid devuelto>';
-- en la conexión/transacción que atienda esa request.
CREATE OR REPLACE FUNCTION nexus360.validar_sesion(p_token TEXT)
RETURNS UUID
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
    SELECT s.usuario_id FROM nexus360.sesion s
     WHERE s.token_hash = encode(digest(p_token, 'sha256'), 'hex')
       AND s.revocado_en IS NULL
       AND s.expira_en > now();
$$;

CREATE OR REPLACE FUNCTION nexus360.cerrar_sesion(p_token TEXT)
RETURNS VOID
LANGUAGE sql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
    UPDATE nexus360.sesion
       SET revocado_en = now()
     WHERE token_hash = encode(digest(p_token, 'sha256'), 'hex')
       AND revocado_en IS NULL;
$$;

-- Único camino válido para promover/degradar un usuario. Revisa el rol
-- de quien llama usando la MISMA función que usan las políticas
-- (rol_usuario_actual), así que hereda su resistencia a recursión.
CREATE OR REPLACE FUNCTION nexus360.cambiar_rol_usuario(p_usuario_id UUID, p_nuevo_rol TEXT)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = nexus360, extensions, pg_temp
AS $$
BEGIN
    IF nexus360.rol_usuario_actual() <> 'admin' THEN
        RAISE EXCEPTION 'Solo un administrador puede cambiar roles';
    END IF;
    IF p_nuevo_rol NOT IN ('empresa', 'admin') THEN
        RAISE EXCEPTION 'Rol inválido: %', p_nuevo_rol;
    END IF;
    UPDATE nexus360.usuario SET rol = p_nuevo_rol WHERE usuario_id = p_usuario_id;
END;
$$;

REVOKE ALL ON FUNCTION nexus360.registrar_usuario(CITEXT, TEXT, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.iniciar_sesion(CITEXT, TEXT, INET, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.validar_sesion(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.cerrar_sesion(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION nexus360.cambiar_rol_usuario(UUID, TEXT) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION nexus360.registrar_usuario(CITEXT, TEXT, TEXT)  TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.iniciar_sesion(CITEXT, TEXT, INET, TEXT) TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.validar_sesion(TEXT) TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.cerrar_sesion(TEXT) TO nexus360_app;
GRANT EXECUTE ON FUNCTION nexus360.cambiar_rol_usuario(UUID, TEXT) TO nexus360_app;

COMMIT;
