# Ibotix Ticketing Portal: Backend

FastAPI + PostgreSQL backend for the Ibotix internal helpdesk. The API contract is Appendix A of
`Backend_Build_Guide_v2.md`; `contract/routes.txt` lists every route.

## Requirements

- Python 3.12
- Docker (PostgreSQL 16 and Mailpit)

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows (Git Bash); use .venv/bin/activate on Linux/macOS
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d db mailpit
```

The database init script creates `ibotix` and `ibotix_test`. Mailpit receives mail on SMTP port
1025 and shows it at http://localhost:8025.

## Run

```bash
uvicorn app.main:app --reload
```

- Liveness: `GET /health/live`
- Readiness: `GET /health/ready`
- Business API: `/api/v1/...`
- OpenAPI: http://localhost:8000/openapi.json (interactive docs at `/docs` outside `prod`)

- Worker: `python -m app.worker` (heartbeat at `GET /health/worker`)

## Gate (run after every part)

```bash
ruff check .
ruff format --check .
mypy app
mypy tests scripts alembic/env.py alembic/versions
pytest -q
alembic upgrade head
alembic check
python scripts/check_contract.py --full
```

`check_contract.py` fails when the app exposes an `/api/v1` route missing from
`contract/routes.txt`, or when that file has malformed or duplicate lines. With `--full` it also
fails when a listed route is not implemented.

## CLI

```bash
python -m app.cli seed                      # Appendix S demo data (refused when ENV=prod)
python -m app.cli reset-db                  # recreate the schema (dev and test only)
python -m app.cli create-super-admin --email E --name N   # password from ADMIN_PASSWORD or a prompt
python -m app.cli mfa-reset --email E       # clear a user's MFA enrolment (audited)
python -m app.cli export-openapi PATH
python -m scripts.perf_seed                 # 50,000 tickets and 200,000 events for load checks
```

## Full stack in Docker

```bash
docker compose -f docker-compose.full.yml up -d --build      # db, migrate, db-roles, api, worker, mailpit
docker compose -f docker-compose.full.yml run --rm api python -m app.cli seed
```

The API is on http://localhost:8000 and Mailpit on http://localhost:8026. Migrations run in the
one-shot `migrate` service, never at API start. The app connects as the non-owner role
`ibotix_app`.

## Documentation

- `docs/OPERATIONS.md`: deployment, environment, database roles, monitoring, upgrades
- `docs/BACKUP-RESTORE.md`: daily backup, retention, restore drill (`scripts/backup.sh`,
  `scripts/restore_check.sh`)
- `docs/SECURITY.md`: security controls and performance results
- `docs/FRONTEND-INTEGRATION.md`: running the frontend against this backend

## Configuration

All settings are read from the environment (or `.env`) through `app/core/config.py`; see
`.env.example`. In `prod`, `JWT_SECRET` must be at least 32 characters, `COOKIE_SECURE` must be
true, and `SLA_TIME_SCALE` must be exactly 1.0, or startup fails.
