#!/bin/sh
# Creates the two database roles and the databases they use.
#
#   orderdesk_owner  owns the schema and runs migrations
#   orderdesk_app    the role the application connects as: not a superuser,
#                    owns nothing, cannot bypass row-level security
#
# The same script is used in three places so the roles are always identical:
#   - Docker Compose: mounted into /docker-entrypoint-initdb.d
#   - CI: run against the PostgreSQL service container
#   - Local development without Docker
#
# Outside Docker, point it at a server with the usual PGHOST / PGPORT /
# PGPASSWORD variables. It is safe to run more than once.
set -eu

: "${ORDERDESK_OWNER_PASSWORD:?ORDERDESK_OWNER_PASSWORD is required}"
: "${ORDERDESK_APP_PASSWORD:?ORDERDESK_APP_PASSWORD is required}"
ORDERDESK_DATABASES="${ORDERDESK_DATABASES:-orderdesk}"

psql -v ON_ERROR_STOP=1 --no-psqlrc \
    --username "${POSTGRES_USER:-postgres}" --dbname postgres \
    -v owner_password="$ORDERDESK_OWNER_PASSWORD" \
    -v app_password="$ORDERDESK_APP_PASSWORD" \
    -v databases="$ORDERDESK_DATABASES" <<'SQL'
SELECT format(
    'CREATE ROLE orderdesk_owner LOGIN PASSWORD %L '
    'NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS',
    :'owner_password'
)
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'orderdesk_owner') \gexec

SELECT format(
    'CREATE ROLE orderdesk_app LOGIN PASSWORD %L '
    'NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS',
    :'app_password'
)
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'orderdesk_app') \gexec

SELECT format('CREATE DATABASE %I OWNER orderdesk_owner', name)
FROM unnest(string_to_array(:'databases', ' ')) AS name
WHERE name <> ''
  AND NOT EXISTS (SELECT FROM pg_database WHERE datname = name) \gexec

SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', name)
FROM unnest(string_to_array(:'databases', ' ')) AS name
WHERE name <> '' \gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO orderdesk_app', name)
FROM unnest(string_to_array(:'databases', ' ')) AS name
WHERE name <> '' \gexec
SQL
