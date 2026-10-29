# Backup and restore

A complete backup has two parts: the PostgreSQL database, and the attachment directory (`ATTACHMENT_DIR`). Take both together, because attachment rows point to files by storage key.

## Targets (to be confirmed by the infrastructure team)

| Item | Value |
|---|---|
| Recovery point objective (RPO) | `<TBD by infrastructure>`. The daily backup alone gives up to 24 hours. Add WAL archiving or point-in-time recovery to lower it. |
| Recovery time objective (RTO) | `<TBD by infrastructure>`. Measure it in the quarterly drill. |
| Schedule | daily at 02:00 IST, outside business hours |
| Retention | 14 daily backups (`RETENTION_DAYS`); keep monthly copies off-site for 12 months |
| Storage | encrypted, off-host, with restricted access. A backup contains personal data and confidential tickets. |

## Daily backup: `scripts/backup.sh`

The script writes `BACKUP_DIR/<UTC timestamp>/` containing three files:

- `database.dump`: `pg_dump --format=custom --no-owner`
- `attachments.tar.gz`: the attachment directory
- `SHA256SUMS`: checksums of both files

It then deletes backup folders older than `RETENTION_DAYS`. Run it as the schema owner, or as any role that can read every table. The non-owner `ibotix_app` role is enough to read, but owner credentials are simpler.

On a host that has the PostgreSQL client tools:

```bash
PGHOST=db.internal PGUSER=ibotix PGPASSWORD=... PGDATABASE=ibotix \
ATTACHMENT_DIR=/srv/ibotix/attachments BACKUP_DIR=/backups/ibotix \
scripts/backup.sh
```

Against `docker-compose.full.yml`, the dump and the archive run inside the containers:

```bash
C="docker compose -f docker-compose.full.yml"
PGDATABASE=ibotix BACKUP_DIR=./backups \
PG_DUMP="$C exec -T db pg_dump -U ibotix" \
ATTACHMENT_TAR="$C exec -T api tar -C /app/var/attachments -czf - ." \
scripts/backup.sh
```

On Windows Git Bash, export `MSYS_NO_PATHCONV=1` first so that container paths such as `/app/var/attachments` are not rewritten.

Schedule the backup with cron or the platform scheduler, and alert on a non-zero exit code. Copy each new folder off-host once it has been written.

## Restore drill: `scripts/restore_check.sh`

Run the drill at least once a quarter, and after any change to the schema or the backup process. The script runs these steps:

1. Verify `SHA256SUMS`.
2. List the attachment archive.
3. Restore `database.dump` into a temporary database named `restore_check_<timestamp>`.
4. Check that the Alembic revision is present, count users, tickets, events, audit entries and linked attachments, and check that the archive holds at least as many files as there are linked attachment rows.
5. Drop the temporary database, even on failure.

```bash
PGHOST=db.internal PGUSER=ibotix PGPASSWORD=... BACKUP_DIR=/backups/ibotix scripts/restore_check.sh
C="docker compose -f docker-compose.full.yml"
BACKUP_DIR=./backups PSQL="$C exec -T db psql -U ibotix" PG_RESTORE="$C exec -T db pg_restore -U ibotix" \
scripts/restore_check.sh
```

The script takes an optional backup folder as its first argument. Without one, it uses the newest folder. Record the duration and the printed counts in the drill log; the duration is the measured RTO for the database part.

## Full restore (disaster recovery)

1. Stop the API and the worker so that nothing writes during the restore.
2. Create an empty database owned by the migrator role:
   `createdb -O ibotix ibotix`
3. Restore the dump:
   `pg_restore --no-owner --role=ibotix --exit-on-error -d ibotix database.dump`
4. Apply the role SQL from `OPERATIONS.md` so that `ibotix_app` gets its grants back.
5. Restore the attachments into an empty `ATTACHMENT_DIR`:
   `tar -C "$ATTACHMENT_DIR" -xzf attachments.tar.gz`
   Make sure uid 10001 owns the files in the container image.
6. Run `alembic upgrade head`, in case the running release is newer than the backup.
7. Start the API, then the worker. Check `/health/ready` and `/health/worker`, sign in as a Super Admin, and open a ticket with an attachment.
8. Expect the worker to catch up on SLA escalations, reminders and auto-close for the period of the outage. Jobs are idempotent and record only the latest escalation level, so the restore does not flood users with notifications.
