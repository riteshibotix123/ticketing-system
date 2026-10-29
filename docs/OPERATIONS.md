# Operations

This document is for whoever deploys and runs the backend. For backups and the restore drill, see [BACKUP-RESTORE.md](BACKUP-RESTORE.md). For security controls, see [SECURITY.md](SECURITY.md).

## Processes

| Process | Command | Notes |
|---|---|---|
| API | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-access-log` | The image's default command. Stateless, so you can run several replicas. The app writes its own JSON access log, so Uvicorn's access log is off. |
| Worker | `python -m app.worker` | Runs SLA scans, reminders, auto-close, protected-action expiry, housekeeping and outgoing email. Jobs use row locks and unique keys, so a second worker is safe but not needed. |
| Migrations | `alembic upgrade head` | A separate one-shot command, run as the schema owner. The API never migrates at start-up. |

All three use the same image (`Dockerfile`: `python:3.12-slim`, non-root user `ibotix` with uid 10001). The image contains no `.env` file and no secrets. All configuration comes from the environment.

## Environment variables

Every variable is read through `app/core/config.py`. `.env.example` lists them with their development defaults.

| Variable | Production value |
|---|---|
| `ENV` | `prod`. This disables `/docs` and makes the seed and `reset-db` refuse to run. |
| `DATABASE_URL` | `postgresql+psycopg://ibotix_app:<secret>@<host>:5432/ibotix`, using the non-owner application role (see below). |
| `JWT_SECRET` | at least 32 random characters, otherwise start-up fails |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` | 15 / 7 |
| `COOKIE_SECURE` | `true` (required in prod) |
| `COOKIE_SAMESITE` | `lax` when the frontend and API share a site; `none` when they are on different sites |
| `CORS_ORIGINS` | the exact frontend origins, comma-separated; a wildcard is refused |
| `ALLOWED_EMAIL_DOMAINS` | `ibotix.ai` |
| `FRONTEND_BASE_URL` | the public frontend URL, used to build links in emails |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | the company mail relay |
| `ATTACHMENT_DIR` | a persistent volume shared by the API and the worker (`/app/var/attachments` in the image) |
| `MAX_UPLOAD_BYTES`, `MAX_FILES_PER_TICKET`, `ALLOWED_CONTENT_TYPES` | defaults: 10 MiB, 5, PDF, PNG, JPEG, text, DOCX, XLSX |
| `TIMEZONE` | `Asia/Kolkata` |
| `WORKER_TICK_SECONDS` | `15` |
| `SLA_TIME_SCALE` | exactly `1.0` (required in prod) |
| `MFA_REQUIRED_ROLES` | empty turns MFA off; for example `super_admin,admin,spoke` |
| `FIELD_ENCRYPTION_KEY` | Fernet key, required as soon as MFA is used. Generate it with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Losing this key makes every MFA secret unreadable. |

## Database roles

The schema is owned by a **migrator** role, for example `ibotix`. The app connects as **`ibotix_app`**, which owns nothing. That role cannot change `audit_log` or `ticket_events`, which a database trigger also protects, and it cannot run DDL. After every migration, run this as the owner:

```sql
SELECT 'CREATE ROLE ibotix_app LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ibotix_app') \gexec
ALTER ROLE ibotix_app WITH LOGIN PASSWORD '<secret>';
GRANT CONNECT ON DATABASE ibotix TO ibotix_app;
GRANT USAGE ON SCHEMA public TO ibotix_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ibotix_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ibotix_app;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log, ticket_events FROM ibotix_app;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON alembic_version FROM ibotix_app;
```

The statements are idempotent. `docker-compose.full.yml` runs them in the one-shot `db-roles` service after `migrate`. Run them again after any migration that adds a table. Owner-only commands are `alembic upgrade head`, `python -m app.cli reset-db` (dev and test only) and backups.

## First deployment

1. Provision PostgreSQL 16, the migrator role, the `ibotix` database and a persistent attachment volume.
2. Set the environment above with `ENV=prod` and `SLA_TIME_SCALE=1.0`. Keep secrets in the platform's secret store, never in the image.
3. Run the migrations as the owner: `alembic upgrade head`.
4. Apply the role SQL above.
5. Create the first Super Admin. The password comes from `ADMIN_PASSWORD`, or from a prompt if that is unset:
   `python -m app.cli create-super-admin --email first.admin@ibotix.ai --name "First Admin"`
   Create a second Super Admin the same way. Protected actions need two.
6. Start the API and the worker. Check `GET /health/ready` and `GET /health/worker`.
7. The Super Admins create departments, Spokes, escalation contacts and categories in the portal. Never run `seed` in production; it refuses when `ENV=prod`.

To recover an MFA enrolment, run `python -m app.cli mfa-reset --email <user>`. It clears the user's TOTP secret and recovery codes and writes an audit entry.

## Local full stack

```bash
docker compose -f docker-compose.full.yml up -d --build
docker compose -f docker-compose.full.yml run --rm api python -m app.cli seed
```

- API: http://localhost:8000 (OpenAPI at `/openapi.json`)
- Mailpit: http://localhost:8026
- Accounts: see `docs/FRONTEND-INTEGRATION.md` (password `Ibotix2026Demo`)
- Stop with `docker compose -f docker-compose.full.yml down`. Add `-v` to delete the data volumes.

This stack uses its own project name (`ibotix-full`) and volumes, and it does not publish PostgreSQL, so it runs next to the development `docker-compose.yml`. Only port 8000 must be free.

## Monitoring

| Signal | Source | Alert when |
|---|---|---|
| Liveness | `GET /health/live` (also the image `HEALTHCHECK`) | non-200 |
| Database readiness | `GET /health/ready` | non-200 |
| Worker heartbeat | `GET /health/worker`: `ok` if the `worker_heartbeat` row is newer than three ticks, otherwise 503 `{"status":"stale"}`. The row's `details` record each job's count and list any failed jobs. | 503 for more than five minutes |
| Outbox failures | `SELECT count(*) FROM email_outbox WHERE status = 'failed'` | greater than 0, or growing |
| Outbox backlog | `SELECT count(*) FROM email_outbox WHERE status = 'pending' AND next_attempt_at < now() - interval '10 minutes'` | greater than 0 |
| Error rate | `app.access` log lines with `status_code` ≥ 500, and `app.errors` lines | above 1% of requests over 5 minutes |
| Latency | `duration_ms` in `app.access` | p95 above 2 s for `/api/v1/tickets` |

### Logs

Every process writes JSON lines to stdout.

- `app.access` (one line per request): `request_id`, `method`, `path` (the route template, for example `/api/v1/tickets/{id}`, so ids and query strings never appear), `status_code`, `duration_ms`, `user_id`. Logs never contain emails, tokens, passwords or request bodies.
- `app.errors`: unhandled exceptions with `request_id`. Clients get only `server_error` and the request id.
- `app.worker`: `job <name> processed <n> items in <ms> ms`, plus failures with stack traces.

To trace one request, search for its `request_id`. That is the `X-Request-ID` response header, which also appears in every error body.

## Upgrades

1. Take a backup (see `BACKUP-RESTORE.md`).
2. Build and push the new image.
3. Run `alembic upgrade head` as the owner, then the role SQL. Migrations only move forward and each release adds new revisions. Already-released revisions are never edited.
4. Restart the worker, then roll the API replicas. Avoid releases that drop a column the old code still reads.
5. Check `/health/ready`, `/health/worker` and the error rate.
6. Rollback: redeploy the previous image. If a migration must be undone, restore the pre-upgrade backup rather than running a downgrade on production data.
