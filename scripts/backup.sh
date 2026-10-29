#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
ATTACHMENT_DIR="${ATTACHMENT_DIR:-./var/attachments}"
PG_DUMP="${PG_DUMP:-pg_dump}"
ATTACHMENT_TAR="${ATTACHMENT_TAR:-tar -C ${ATTACHMENT_DIR} -czf - .}"
DATABASE="${PGDATABASE:-ibotix}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${BACKUP_DIR}/${stamp}"
mkdir -p "${target}"

echo "backup ${stamp}: dumping database ${DATABASE}"
${PG_DUMP} --format=custom --no-owner --dbname="${DATABASE}" > "${target}/database.dump"

echo "backup ${stamp}: archiving attachments"
${ATTACHMENT_TAR} > "${target}/attachments.tar.gz"

(cd "${target}" && sha256sum database.dump attachments.tar.gz > SHA256SUMS)

if [ ! -s "${target}/database.dump" ]; then
    echo "backup ${stamp}: database dump is empty" >&2
    exit 1
fi

echo "backup ${stamp}: pruning backups older than ${RETENTION_DAYS} days"
find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -exec rm -rf {} +

echo "backup ${stamp}: done (${target})"
