#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
PSQL="${PSQL:-psql}"
PG_RESTORE="${PG_RESTORE:-pg_restore}"
ADMIN_DATABASE="${ADMIN_DATABASE:-postgres}"

source_dir="${1:-$(find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)}"
if [ -z "${source_dir}" ] || [ ! -f "${source_dir}/database.dump" ]; then
    echo "restore check: no backup found in ${BACKUP_DIR}" >&2
    exit 1
fi

scratch="restore_check_$(date -u +%Y%m%d%H%M%S)"

cleanup() {
    ${PSQL} --dbname="${ADMIN_DATABASE}" -v ON_ERROR_STOP=1 -qc "DROP DATABASE IF EXISTS ${scratch}" >/dev/null
}
trap cleanup EXIT

echo "restore check: verifying checksums in ${source_dir}"
(cd "${source_dir}" && sha256sum --check --quiet SHA256SUMS)

echo "restore check: listing attachment archive"
listing="$(tar -tzf - < "${source_dir}/attachments.tar.gz")"
files="$(printf '%s\n' "${listing}" | grep -c -v -e '/$' -e '^$' || true)"

echo "restore check: restoring into ${scratch}"
${PSQL} --dbname="${ADMIN_DATABASE}" -v ON_ERROR_STOP=1 -qc "CREATE DATABASE ${scratch}"
${PG_RESTORE} --no-owner --no-privileges --exit-on-error --dbname="${scratch}" < "${source_dir}/database.dump"

query() {
    ${PSQL} --dbname="${scratch}" -v ON_ERROR_STOP=1 -tAc "$1"
}

revision="$(query "SELECT version_num FROM alembic_version")"
users="$(query "SELECT count(*) FROM users")"
tickets="$(query "SELECT count(*) FROM tickets")"
events="$(query "SELECT count(*) FROM ticket_events")"
audit="$(query "SELECT count(*) FROM audit_log")"
linked="$(query "SELECT count(*) FROM attachments WHERE ticket_id IS NOT NULL")"

echo "restore check: revision=${revision} users=${users} tickets=${tickets} events=${events} audit=${audit} attachments=${linked} files=${files}"

if [ -z "${revision}" ] || [ "${users}" -eq 0 ]; then
    echo "restore check: FAILED (missing schema revision or users)" >&2
    exit 1
fi
if [ "${files}" -lt "${linked}" ]; then
    echo "restore check: FAILED (archive has fewer files than linked attachments)" >&2
    exit 1
fi
echo "restore check: passed"
