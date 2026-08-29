-- Fija la contraseña del rol de aplicación creado por 001_schema.sql.
-- El script del schema crea el rol SIN password a propósito (ver su
-- comentario: "Fija la contraseña por fuera de este script").
--
-- SOLO PARA DESARROLLO LOCAL / DOCKER. En un entorno real, corre este
-- ALTER ROLE manualmente con una contraseña fuerte y NO lo dejes en un
-- archivo versionado ni lo repitas aquí.
ALTER ROLE nexus360_app WITH PASSWORD 'dev_only_change_me';
