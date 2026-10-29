# Backend Build Guide v2: Ibotix Internal Ticketing Portal (FastAPI + PostgreSQL)

One self-contained file. It tells a code assistant how to build the backend, part by part, so that it implements exactly the API the frontend uses (Appendix A, which is identical in `Frontend_Change_Request_CR1.md`).

Sources: BRD v1.0; the decisions made in this project (section 3.1 and Appendix R); `IBOTIX_FRONTEND_SPEC.md` as amended by `Frontend_Change_Request_CR1.md`.

---

## 1. How to use this file

Put this file in the repository as `docs/BACKEND_GUIDE.md` (and the assistant rules from section 7 as `AGENTS.md` or `CLAUDE.md` at the repository root). For each part send one instruction:

> Build B05. Read section 3 (Context Pack), section 4 (gate), the Part B05 section, Appendix A, and the parts of Appendix R it names, plus the files it lists under Reads. Implement it, run the gate, fix failures, then stop and report.

Rules for you as the owner:
- One part per session. Review, commit, tag (`b05`), then the next part. Never start a part while the gate fails.
- If the assistant replies `CONTRACT_GAP:` or `RULE_GAP:`, decide, edit this file (Appendix A for the API, Appendix R for rules), and rerun the part.
- When the backend exists, run the frontend's `npm run gen:api` against `http://localhost:8000/openapi.json` and the frontend's E2E tests against the real backend (part B23).

If the assistant cannot read files from your repository, paste: section 3, section 4, the one part, Appendix A, the parts of Appendix R the part names, the file tree, `pyproject.toml`, and the files under **Reads**.

---

## 2. Build map

| Part | Name | Release | Depends on | Size |
|---|---|---|---|---|
| B01 | Scaffold, Docker, settings, health, contract route list | R1 | none | S |
| B02 | Database foundation, Alembic, test harness, clock | R1 | B01 | M |
| B03 | Identity, organization, and policy models | R1 | B02 | M |
| B04 | Ticket, SLA, notification models | R1 | B03 | L |
| B05 | Core: errors, paging, context, domain events, audit | R1 | B04 | M |
| B06 | Auth, sessions, public config, permission flags | R1 | B05 | L |
| B07 | Email outbox and worker skeleton | R1 | B05 | M |
| B08 | Signup, verification, approval chain, re-apply | R1 | B06, B07 | L |
| B09 | Users, Spoke mapping, administrators, protected actions | R1 | B08 | L |
| B10 | Departments, categories, grants, policy | R1 | B09 | L |
| B11 | Access policy: visibility and allowed actions | R1 | B10 | L |
| B12 | SLA engine: timers, levels, escalation recipients | R1 | B11 | L |
| B13 | Ticket reads: list, detail, timeline | R1 | B12 | L |
| B14 | Attachments and ticket creation | R1 | B13 | L |
| B15 | Workflow A: acknowledge, assign, status, hold, ETA, priority | R1 | B14 | L |
| B16 | Workflow B: resolve, confirm, reopen, cancel, close, transfer | R1 | B15 | L |
| B17 | Comments and collaborators | R1 | B15 | M |
| B18 | Notifications: events, recipients, portal and email | R1 | B16, B17 | L |
| B19 | Scheduler: escalations, reminders, auto-close, housekeeping | R1 | B18 | L |
| B20 | Audit endpoint and dashboards | R1 | B16 | M |
| B21 | MFA (TOTP), enabled by configuration | R1 | B06 | M |
| B22 | Seed data and CLI | R1 | B20 | M |
| B23 | Contract conformance and frontend integration | R1 | B22 | M |
| B24 | Security hardening and performance | R1 | B23 | M |
| B25 | Operations: Docker, logging, backups, README | R1 | B24 | S |
| B26 | Integration, time-travel, and concurrency tests | R1 gate | B25 | L |
| R2-A | Dashboards and KPI queries | R2 | B26 | L |
| R2-B | Exports and saved views | R2 | R2-A | M |
| R2-C1 | Business calendar, holidays, SLA basis overrides | R2 | R2-B | M |
| R2-C2 | Notification preferences and digests | R2 | R2-C1 | S |

Release 1 is the BRD section 20 control loop. Release 2 parts begin with a contract update (section 4.2).

---

## 3. PART 0: CONTEXT PACK (every session reads this)

### 3.1 Product and decisions in brief
- An internal helpdesk: employees raise tickets to a department; department Spokes acknowledge with an ETA, assign within their department, and keep the requester updated; missed deadlines escalate automatically; everything is audited.
- **The backend owns every business rule** (workflow, permissions, confidential visibility, SLA timers, escalation, notifications, audit). The frontend renders what the API returns, including `allowed_actions`, `sla`, and `permissions`.
- Roles: `employee`, `admin`, `super_admin` (stored on the user) plus Spoke (a mapping of a user to departments). **There is no Resolver role**; an assignee is per ticket.
- Times are stored and sent in UTC; business-day logic uses IST (`Asia/Kolkata`).
- Nothing is hard-deleted, with two exceptions: unlinked temporary attachment uploads older than 24 hours, and expired tokens.
- The agreed decisions are D-1 to D-15 in Appendix R.1.

### 3.2 Stack and allowed packages (nothing else)

Python 3.12, FastAPI, Uvicorn, Pydantic v2, pydantic-settings, SQLAlchemy 2.0 (synchronous, typed `Mapped[]`), Alembic, `psycopg` 3 (binary), PostgreSQL 16, `argon2-cffi`, `PyJWT`, `pyotp`, `cryptography` (Fernet, for MFA secrets), `python-multipart`, `email-validator`, `jinja2`, `openpyxl` (XLSX export, Release 2), `reportlab` (PDF export, Release 2). Dev and test: `pytest`, `pytest-cov`, `httpx`, `ruff`, `mypy` (strict), `types-openpyxl`, `types-reportlab`.

Do not use: Celery, Redis, RQ, Django, Flask, SQLModel, Tortoise, passlib, python-jose, async SQLAlchemy, Pydantic v1 syntax, `requests`, `freezegun`, `slowapi`, or any package not listed. Part B01 locks exact versions in `pyproject.toml`; after that it is authoritative.

Why: synchronous SQLAlchemy avoids async pitfalls and is fast enough for about 500 employees; the scheduler is a plain worker process using PostgreSQL row locks, so no broker is needed; rate limits live in the database so they work across processes.

### 3.3 Hard rules for the assistant
1. **Contract first.** Every route, request body, response body, status code, error code, and enum value must match Appendix A exactly. Pydantic class names for response models must make sense, but field names and values are what matter. If Appendix A lacks something you need, reply `CONTRACT_GAP:` plus one line and stop.
2. **Rules first.** Business behavior comes from Appendix R. If a rule is missing, reply `RULE_GAP:` and stop. Never invent rules, enum values, error codes, or fields.
3. **Complete files only.** Write whole files, never partial diffs.
4. **No comments, no docstrings.** Clean, self-explanatory code.
5. **Strict typing.** `mypy --strict` clean; no `Any` except JSON values typed as `JsonValue` in `app/core/types.py`; no `# type: ignore`; no `cast` unless a part permits it.
6. **Layering.** Routers are thin (parse, call one service, return). Services hold business logic and never commit. Models hold no logic. All permission and visibility decisions live in `app/policy/`. SQL lives in services or `app/queries/`, never in routers.
7. **Transactions.** One transaction per request (the `get_db` dependency commits on success and rolls back on error). Worker jobs commit per unit of work. Services never call `commit()`.
8. **Time.** Use the injected `Clock`. `datetime.now()` and `datetime.utcnow()` are forbidden outside `SystemClock`. Services set timestamps explicitly from the clock.
9. **Concurrency.** Every ticket mutation first locks the ticket row (`SELECT ... FOR UPDATE`). Jobs use `FOR UPDATE SKIP LOCKED` and unique keys for idempotency.
10. **Security.** Never log or return passwords, tokens, hashes, or MFA secrets. ORM or bound parameters only. Never reveal whether an email exists. A confidential ticket must never appear in any list, count, search, notification, audit entry, email, or error message for a user who cannot see it. A ticket the caller may not see returns the same 404 as a ticket that does not exist.
11. **Stay inside the part.** Create or modify only the listed files.
12. **Ask once.** If something is ambiguous, ask all questions in one message before writing code.
13. **Stop rule.** If the gate still fails after two fix attempts with the same cause, stop and report the failure, what you tried, and your best hypothesis. Do not continue guessing.
14. **No placeholders.** No `TODO`, no `print`, no dead code.

### 3.4 Repository layout (fixed)

```
backend/
  pyproject.toml  alembic.ini  alembic/env.py  alembic/versions/
  contract/routes.txt
  docker-compose.yml  Dockerfile  .env.example
  app/
    main.py  cli.py
    core/        config.py db.py clock.py errors.py logging.py security.py pagination.py
                 request_context.py enums.py types.py events.py ids.py
    models/      base.py identity.py org.py policy.py ticket.py sla.py notification.py audit.py
    schemas/     auth.py users.py org.py tickets.py notifications.py audit.py dashboards.py common.py
    api/         deps.py  routers/ (one module per area)
    services/    one module per area; handlers/ for domain-event subscribers
    policy/      visibility.py allowed_actions.py flags.py relationships.py actors.py permissions.py
    queries/     reusable select builders
    integrations/ email/  storage/  scanner/
    worker/      main.py  jobs/
    seed/
    templates/email/
  scripts/       check_contract.py
  tests/         unit/ api/ integration/ scenarios/ security/ perf/ conftest.py factories.py
```

### 3.5 Conventions
- Python `snake_case`; API JSON `snake_case`; tables plural `snake_case`; foreign keys `<entity>_id`; booleans `is_` or `has_`.
- **Ids:** users, categories, grants, requests, notifications, attachments: UUID v4 generated by the application, exposed as strings. **Department id is the code** (primary key, `varchar(6)`). **A ticket's API id is its ticket number**; internally tickets also have a UUID primary key, but every ticket route and every response uses the number.
- **Enums:** lowercase `StrEnum` values exactly as Appendix A.2, stored as `varchar` with a `CHECK` constraint (SQLAlchemy `Enum(native_enum=False, create_constraint=True)`), never native PostgreSQL enums.
- **Pagination:** `page` from 1, `page_size` default 25 and 1 to 100; response `{items, total, page, page_size}`. Sorting uses a whitelist; unknown fields return `validation_error`.
- **Error envelope and codes:** exactly Appendix A.1.
- **Auth transport:** bearer access JWT (15 minutes); opaque refresh token in the httpOnly cookie `refresh_token`, rotated on every refresh, stored only as a SHA-256 hash.

### 3.6 Environment variables (all read through `app/core/config.py`)

`ENV` (dev, test, prod), `DATABASE_URL`, `TEST_DATABASE_URL`, `JWT_SECRET`, `ACCESS_TOKEN_MINUTES` (15), `REFRESH_TOKEN_DAYS` (7), `COOKIE_SECURE`, `COOKIE_SAMESITE`, `CORS_ORIGINS`, `ALLOWED_EMAIL_DOMAINS` (default `ibotix.ai`), `FRONTEND_BASE_URL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS`, `ATTACHMENT_DIR`, `MAX_UPLOAD_BYTES` (10485760), `MAX_FILES_PER_TICKET` (5), `ALLOWED_CONTENT_TYPES`, `TIMEZONE` (`Asia/Kolkata`), `WORKER_TICK_SECONDS` (15), `SLA_TIME_SCALE` (1.0), `MFA_REQUIRED_ROLES` (comma list of `super_admin,admin,spoke`; empty by default, which turns MFA enforcement off), `FIELD_ENCRYPTION_KEY` (Fernet key, required only when MFA is used). In `prod`: `JWT_SECRET` at least 32 random characters, `COOKIE_SECURE` true, `SLA_TIME_SCALE` exactly 1.0; otherwise startup fails.

`SLA_TIME_SCALE` multiplies every SLA duration given in hours (0.0166667 turns hours into minutes) so timers can be demonstrated and tested quickly. It does not apply to business-day auto-close.

### 3.7 Self-check list (answer yes/no at the end of every part)
1. Only listed files created or modified?
2. Only allowed packages used?
3. Every route matches Appendix A (path, method, body, response, status, error codes, lowercase enums)?
4. `ruff`, `mypy --strict`, `pytest` pass?
5. No comments, docstrings, `print`, TODO, `type: ignore`?
6. Services never commit; routers hold no business logic?
7. Permissions and visibility only through `app/policy/`?
8. Time only through `Clock`?
9. Audit rows written for every state change this part introduces?
10. Tests listed in the part written, including permission-denied and validation cases?

---

## 4. Gate and change protocol

### 4.1 Gate after every part

```
ruff check .
ruff format --check .
mypy app
pytest -q
alembic upgrade head
alembic check
python scripts/check_contract.py
```

`alembic check` must report no drift between models and migrations. `check_contract.py` (B01) fails when the app exposes an `/api/v1` route that is not in `contract/routes.txt`; with `--full` (used from B23) it also fails when a listed route is missing. Tag the commit `bNN`.

### 4.2 Contract change protocol
1. Appendix A is the contract and is mirrored in `Frontend_Change_Request_CR1.md`. Change both together.
2. If a part needs something Appendix A lacks, the assistant replies `CONTRACT_GAP:` and stops. You decide, edit Appendix A here and in the frontend file, and update `contract/routes.txt`.
3. Never change an endpoint in the backend only.

### 4.3 Migrations
One Alembic revision per part that changes models, named `bNN_short_description`, linear history. Never edit a migration after its part is tagged; add a new one.

---

## 5. THE PARTS

Each part: **Goal, Depends on, Reads, Creates, Modifies, Endpoints, Spec, Tests, Done when, Do not.** "Needs rules" names the Appendix R sections to read.

---

### B01: Scaffold, Docker, settings, health, contract route list (R1)

**Goal:** a runnable empty FastAPI project with PostgreSQL in Docker and strict tooling.
**Depends on:** none. **Reads:** Appendix A.4.
**Creates:** `pyproject.toml`, `.python-version`, `.env.example`, `.gitignore`, `docker-compose.yml`, `docker/initdb/01-create-test-db.sql`, `app/__init__.py`, `app/main.py`, `app/core/__init__.py`, `app/core/config.py`, `app/core/logging.py`, `app/core/types.py`, `app/api/__init__.py`, `app/api/routers/__init__.py`, `app/api/routers/health.py`, `contract/routes.txt`, `scripts/check_contract.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/api/test_health.py`, `tests/unit/test_config.py`, `README.md`.
**Spec:**
- `pyproject.toml`: exact pinned versions of the allowed packages; `ruff` (line length 100, rules `E,F,I,UP,B,SIM,ARG,C4,PT`, formatter on); `mypy` (`strict = true`); `pytest` (`testpaths = ["tests"]`, strict markers).
- `docker-compose.yml`: `db` (postgres:16, port 5432, volume, healthcheck, init script creating databases `ibotix` and `ibotix_test`) and `mailpit` (SMTP 1025, UI 8025).
- `config.py`: `Settings` (pydantic-settings) with every variable of section 3.6, typed, dev defaults, `get_settings()` cached, and a validator enforcing the `prod` rules.
- `logging.py`: JSON log formatter including `request_id`; never log request bodies.
- `main.py`: `create_app()` factory; business routes under `/api/v1`; health routes `/health/live` and `/health/ready` outside the prefix; CORS from settings (`allow_credentials=True`, explicit origins, no wildcard); GZip.
- `contract/routes.txt`: one line per Appendix A.4 route, `METHOD /api/v1/path` (with `{param}` names).
- `check_contract.py`: loads the app's OpenAPI paths and compares method and path set to `routes.txt`; prints a readable diff and exits 1 on any extra route (and on missing routes with `--full`). Health routes are exempt.
**Tests:** config defaults and prod validation failures; health live and ready.
**Done when:** gate passes; `docker compose up -d db mailpit` works.
**Do not:** add models, auth, or business routes; commit secrets.

---

### B02: Database foundation, Alembic, test harness, clock (R1)

**Goal:** sessions, migrations, clock, enums, and a real-PostgreSQL test harness.
**Depends on:** B01. **Reads:** `app/core/config.py`, `tests/conftest.py`, `pyproject.toml`.
**Creates:** `app/core/db.py`, `app/core/clock.py`, `app/core/enums.py`, `app/core/ids.py`, `app/models/__init__.py`, `app/models/base.py`, `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/b02_extensions.py`, `tests/unit/test_clock.py`, `tests/unit/test_db_session.py`. **Modifies:** `tests/conftest.py`, `app/main.py`.
**Spec:**
- `db.py`: sync engine (`pool_pre_ping=True`), `SessionLocal`, dependency `get_db()` that commits on success and rolls back on error.
- `base.py`: `Base` with a constraint naming convention; mixins `UuidPk` (application-generated UUID v4) and `Timestamps` (`created_at`, `updated_at`, `timestamptz`).
- `enums.py`: every enum of Appendix A.2 as lowercase `StrEnum`, plus `PRIORITY_RANK` (low 1, medium 2, high 3, critical 4).
- `clock.py`: `Clock` protocol (`now()` aware UTC); `SystemClock`; `FrozenClock` (`set`, `advance`); dependency `get_clock()`; `to_ist(dt)`.
- `ids.py`: ticket number formatting helper `format_ticket_no(code, year, seq)`.
- Alembic `env.py` reads `DATABASE_URL` (or `TEST_DATABASE_URL` when `ENV=test`), imports all models, `compare_type=True`. First revision enables `pg_trgm`.
- Test harness in `conftest.py`: a session-scoped fixture that recreates the test schema and runs `alembic upgrade head` once; a function-scoped `db` fixture using an outer transaction with `join_transaction_mode="create_savepoint"` rolled back after each test; `clock` fixture `FrozenClock` at `2026-10-27T04:30:00Z`; `client` fixture overriding `get_db` and `get_clock`; `committed_db` fixture (real commits, truncation afterward) for concurrency tests.
- Tests run on real PostgreSQL only; SQLite is forbidden.
**Tests:** clock; session commit and rollback; enums match Appendix A.2.
**Done when:** gate passes (`alembic check` clean).
**Do not:** create business tables.

---

### B03: Identity, organization, and policy models (R1)

**Goal:** tables for users, signup, tokens, Spokes, categories, grants, protected actions, policy versions, and rate limits.
**Depends on:** B02. **Reads:** `app/models/base.py`, `app/core/enums.py`.
**Creates:** `app/models/identity.py`, `app/models/org.py`, `app/models/policy.py`, `alembic/versions/b03_identity_org_policy.py`, `tests/unit/test_models_identity_org.py`, `tests/factories.py` (plain factory functions, no factory library). **Modifies:** `app/models/__init__.py`.
**Tables and rules:**
- `departments`: `id` (`varchar(6)` primary key, the code, check `^[A-Z]{2,6}$`), `name`, `is_active` (default false), `escalation_contact_user_id` (FK users, nullable), timestamps.
- `users`: `id`, `email` (stored lowercase; unique index on `lower(email)`), `name`, `title`, `password_hash`, `home_department_id` (FK, required), `global_role` (`employee`, `admin`, `super_admin`), `state` (AccountState), `email_verified_at`, `approved_by_id`, `approved_at`, `deactivated_by_id`, `deactivated_at`, `deactivation_reason`, `failed_login_count` (0), `locked_until`, `last_login_at`, `mfa_enabled` (false), `mfa_secret_encrypted`, `mfa_failed_count` (0), `theme`.
- `mfa_recovery_codes`: `user_id`, `code_hash`, `used_at`.
- `signup_requests`: `user_id`, `requested_role`, `requested_department_id`, `approved_role`, `approved_department_id`, `status` (`pending`, `approved`, `rejected`), `decided_by_id`, `decision_reason`, `decided_at`. Partial unique index: one `pending` request per user.
- `email_tokens`: `user_id`, `purpose` (`verify`, `reset`), `token_hash` (unique), `expires_at`, `used_at`.
- `refresh_tokens`: `user_id`, `family_id`, `token_hash` (unique), `expires_at`, `revoked_at`, `replaced_by_id`, `user_agent`, `ip_address`.
- `spoke_assignments`: `user_id`, `department_id`, `granted_by_id`, `granted_at`, `revoked_by_id`, `revoked_at`; partial unique (`user_id`, `department_id`) where `revoked_at` is null.
- `categories`: `department_id`, `name`, `is_confidential`, `is_active`; unique (`department_id`, `lower(name)`). One level only.
- `confidential_grants`: `user_id`, `category_id`, `granted_by_id`, `granted_at`, `revoked_by_id`, `revoked_at`; partial unique active (`user_id`, `category_id`).
- `protected_action_requests`: `kind`, `target_user_id`, `requested_by_id`, `status`, `decided_by_id`, `decided_at`, `reason`, `decision_reason`, `expires_at`.
- `policy_versions`: `version` (unique integer), `config` (jsonb holding the `PolicyConfig` of Appendix A.3), `created_by_id`, `created_at`. The migration inserts version 1 with the defaults of Appendix R.5. The current policy is the highest version.
- `rate_limit_hits`: `key`, `window_start`, `count`; unique (`key`, `window_start`).
- All foreign keys indexed; all datetimes `timestamptz`.
**Tests:** every unique and partial-unique constraint, checks, default policy present, factories.
**Done when:** gate passes.
**Do not:** add endpoints or services.

---

### B04: Ticket, SLA, and notification models (R1)

**Goal:** all ticket-domain tables.
**Depends on:** B03. **Reads:** `app/models/*`. **Needs rules:** R.4, R.5.
**Creates:** `app/models/ticket.py`, `app/models/sla.py`, `app/models/notification.py`, `alembic/versions/b04_tickets_sla_notifications.py`, `tests/unit/test_models_ticket.py`. **Modifies:** `tests/factories.py`, `app/models/__init__.py`.
**Tables:**
- `ticket_counters`: `department_code`, `year`, `last_value`; primary key (`department_code`, `year`).
- `tickets`: `id` (uuid), `ticket_no` (unique, the API id), `origin_department_code`, `department_id`, `category_id` (nullable), `title` (120), `description`, `requested_priority`, `priority`, `confidential`, `status`, `requester_id`, `owner_id`, `assignee_id`, `sla_started_at`, `acknowledged_at`, `eta`, `next_checkpoint_at`, `last_team_update_at`, `hold_reason`, `hold_review_date`, `awaiting_since`, `resolution_summary`, `resolved_at`, `closed_at`, `close_reason` (`confirmed`, `admin`, `auto`), `cancel_reason`, `reopen_count` (0), `feedback_rating` (check 1 to 5), `feedback_comment`, `escalation_level` (0 to 3, default 0), `update_overdue` (false), timestamps. Indexes: (`department_id`, `status`), `requester_id`, `owner_id`, `assignee_id`, (`escalation_level`, `priority`), `sla_started_at`, `eta`, `updated_at`; trigram indexes on `title` and `ticket_no`.
- `ticket_collaborators`: (`ticket_id`, `user_id`) primary key, `added_by_id`, `added_at`.
- `ticket_events`: `ticket_id`, `at`, `actor_id` (null for system), `kind` (`comment`, `internal_note`, `audit`), `action`, `detail`, `public_detail`, `body`, `is_public`, `data` (jsonb). Immutable.
- `attachments`: `ticket_id` (nullable until linked), `uploader_id`, `file_name`, `content_type`, `size_bytes`, `storage_key`, `sha256`, `scan_status`, `created_at`.
- `sla_timers`: `ticket_id`, `kind` (`initial_response`, `progress_update`, `eta`, `auto_close`, `requester_reminder`, `hold_review`), `cycle` (starts 1, incremented in place on restart), `started_at`, `warning_at`, `due_at`, `l3_at`, `paused_at`, `paused_seconds`, `level` (0 to 3), `met_at`, `stopped_at`; unique (`ticket_id`, `kind`); partial index on `due_at` for active timers.
- `escalation_events`: `ticket_id`, `timer_kind`, `cycle`, `level`, `step_key`, `at`, `recipient_ids` (uuid array); unique (`ticket_id`, `timer_kind`, `cycle`, `step_key`).
- `notifications`: `user_id`, `ticket_id` (nullable), `kind`, `text`, `critical`, `dedupe_key` (nullable), `created_at`, `read_at`; unique (`user_id`, `dedupe_key`) where not null; index (`user_id`, `read_at`, `created_at` descending).
- `email_outbox`: `notification_id`, `to_address`, `template`, `context` (jsonb), `subject`, `body_text`, `body_html`, `status` (`pending`, `sent`, `failed`), `attempts`, `next_attempt_at`, `last_error`, `sent_at`, `created_at`; index (`status`, `next_attempt_at`).
- `worker_heartbeat`: `name` (primary key), `last_seen_at`, `details` (jsonb).
**Tests:** unique keys (ticket number, timer per kind, escalation step, notification dedupe), rating check, factories for tickets in every status.
**Done when:** gate passes.
**Do not:** add services or routes.

---

### B05: Core: errors, paging, context, domain events, audit (R1)

**Goal:** the shared plumbing every later part uses.
**Depends on:** B04. **Reads:** `app/core/*`, `app/models/*`, `app/main.py`.
**Creates:** `app/core/errors.py`, `app/core/pagination.py`, `app/core/request_context.py`, `app/core/events.py`, `app/models/audit.py`, `app/services/audit.py`, `app/services/handlers/__init__.py`, `app/schemas/common.py`, `alembic/versions/b05_audit_log.py`, `tests/unit/test_errors.py`, `tests/unit/test_pagination.py`, `tests/unit/test_events.py`, `tests/unit/test_audit.py`, `tests/api/test_error_envelope.py`. **Modifies:** `app/main.py`, `app/api/routers/health.py`, `app/models/__init__.py`.
**Spec:**
- **Errors:** `ApiError(code, message, status_code, fields=None, details=None)` and helper constructors for every code in Appendix A.1. Exception handlers for `ApiError`, `RequestValidationError` (code `validation_error`, `fields` keyed by the last path segment), `StarletteHTTPException`, and unhandled exceptions (`server_error`, no stack trace). The response is always `{ "error": { code, message, fields?, details?, request_id } }`.
- **Request context:** middleware sets `request_id` (from `X-Request-ID` or generated), client IP, user agent in a context variable; the response echoes `X-Request-ID`.
- **Pagination:** dependency `PageParams` (page at least 1, `page_size` 1 to 100, default 25); helper to count and fetch a page; `parse_sort(sort, allowed)`; `schemas/common.py` holds the `Page` response base, `UserRef`, and the system actor object `{id:'system', name:'System'}`.
- **Audit:** table `audit_log` (`actor_id`, `action`, `object_type`, `object_id`, `old_value`, `new_value`, `reason`, `detail`, `ip_address`, `user_agent`, `created_at`, plus `ticket_id`, `department_id`, `is_security_limited`, `is_confidential_ticket`). A **database trigger raises an exception on UPDATE or DELETE** of `audit_log` and of `ticket_events`; the migration also revokes `UPDATE` and `DELETE` on both from `PUBLIC`, and `docs` (B25) will require the application to connect as a non-owner role. `AuditService.record(...)` writes a row from the request context and clock with JSON-safe values.
- **Domain events:** frozen dataclasses for every event in Appendix R.7; `publish(session, event)` calls registered handlers synchronously in the caller's transaction; `register(event_type, handler)`; `register_all()` (empty for now) is called in `create_app()` and by the worker.
**Tests:** every error code's envelope and status; validation shape; request id echo; pagination bounds and sort whitelist; the audit and event triggers block UPDATE and DELETE; serialization; handlers run in order and exceptions propagate.
**Done when:** gate passes.
**Do not:** add business routes; swallow handler exceptions.

---

### B06: Auth, sessions, public config, permission flags (R1)

**Goal:** login, refresh, logout, me, public config, forgot and reset password.
**Depends on:** B05. **Reads:** `app/core/*`, `app/models/identity.py`, `app/models/policy.py`. **Needs rules:** R.1 (D-8, D-14), R.11. **Endpoints:** `GET /public/config`, `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `GET /auth/me`, `POST /auth/forgot-password`, `/auth/reset-password`.
**Creates:** `app/core/security.py`, `app/schemas/auth.py`, `app/services/auth.py`, `app/services/policy.py` (read the current `PolicyConfig`), `app/services/rate_limit.py`, `app/services/me.py`, `app/policy/__init__.py`, `app/policy/flags.py`, `app/api/deps.py`, `app/api/routers/auth.py`, `app/api/routers/config.py`, `tests/api/test_auth.py`, `tests/unit/test_security.py`, `tests/unit/test_flags.py`. **Modifies:** `app/main.py`.
**Spec:**
- **Passwords:** argon2id; policy check (12 to 128 characters, lowercase, uppercase, digit).
- **Access token:** HS256 JWT (`sub`, `iat`, `exp`, `jti`), no role claims (the user is loaded from the database on every request so deactivation is immediate). Missing, invalid, or expired token gives 401 `unauthenticated`. A user whose state is not `active` gets `unauthenticated`.
- **`Actor`:** dataclass from `get_actor` (id, global role, home department, active Spoke department ids, name, email). `require_roles(*roles)` for coarse gating; fine decisions go through `app/policy/`.
- **Login order:** normalize email; unknown email still runs a dummy hash check and returns 401 `invalid_credentials`; if `locked_until` is in the future return 429 `too_many_attempts` with `details.retry_after_seconds`; wrong password increments `failed_login_count`, locks for 15 minutes at 5, returns 401 `invalid_credentials`; **only after a correct password** evaluate the account: any state other than `active` returns 403 `account_state` with `details.state` (and `details.rejection_reason` for `rejected`); on success reset the counter, set `last_login_at`, return `LoginSuccess` (the `LoginResult` MFA variants are added in B21).
- **Refresh:** 32 random bytes in the cookie `refresh_token` (httpOnly; `Secure` and `SameSite` from settings; path `/api/v1/auth`), stored as SHA-256; `refresh` rotates and returns a new access token; reuse of a rotated token revokes the whole family and returns 401 `unauthenticated`; expired returns 401 `unauthenticated`; `logout` revokes and clears the cookie (204 always). `refresh` and `logout` require the `Origin` header (when present) to be in `CORS_ORIGINS`, else 403 `forbidden`.
- **Forgot and reset:** forgot always returns 202 and, for an active user, enqueues a reset email with a 1-hour token (stored hashed, in `email_tokens`); reset checks the token (410 `token_expired` when expired, 422 when invalid), applies the password policy, sets the password, resets the lockout counter, and revokes all refresh tokens.
- **Rate limits** (database, fixed window): login 10 per minute per IP and per email; forgot 3 per hour per email; exceeding gives 429 `rate_limited` with `retry_after_seconds`.
- **`GET /auth/me`:** returns `Me` per Appendix A.3: `roles` (always `employee`, plus `spoke` if mapped, `admin`, `super_admin`), `department_id`, `spoke_departments`, `permissions` from `flags.py`, `mfa_enabled`, `theme`.
- **Flags:** `flags.py` computes `permissions` exactly as Appendix A.5 using the actor and the current policy (`admins_can_manage_departments`).
- **`GET /public/config`:** `PublicConfig` with the active departments, domain allowlist, attachment limits from settings, `password_min_length` 12, and `first_response_hours`. No auth; never returns 401.
- Audit: `login_succeeded`, `login_failed`, `account_locked`, `logout`, `refresh_reuse_detected`, `password_reset`.
**Tests:** every login outcome and error code; status revealed only after the correct password; lockout and expiry; rotation and reuse; cookie attributes; origin check; rate limits; expired and tampered JWT; deactivated user's token refused; reset flow; `Me` and flags for every role including the Admin toggle.
**Done when:** gate passes.
**Do not:** return 401 from public endpoints; put roles in the JWT; store tokens unhashed.

---

### B07: Email outbox and worker skeleton (R1)

**Goal:** reliable email from an outbox, and the worker process that hosts every scheduled job.
**Depends on:** B05. **Reads:** `app/models/notification.py`, `app/core/config.py`, `app/core/clock.py`.
**Creates:** `app/integrations/email/__init__.py`, `base.py`, `smtp.py`, `memory.py`, `app/services/email_outbox.py`, `app/services/email_templates.py`, `app/templates/email/` (`verify_email`, `account_exists_notice`, `signup_approved`, `signup_rejected`, `password_reset`, each `.txt.j2` and `.html.j2`), `app/worker/__init__.py`, `app/worker/main.py`, `app/worker/jobs/__init__.py`, `app/worker/jobs/send_outbox.py`, `tests/unit/test_email_templates.py`, `tests/integration/test_outbox.py`, `tests/integration/test_worker_loop.py`.
**Spec:**
- `enqueue_email(session, clock, to, template, context, notification_id=None)` renders and writes an `email_outbox` row in the caller's transaction. Links use `FRONTEND_BASE_URL`.
- `send_outbox` job: select up to 20 due `pending` rows with `FOR UPDATE SKIP LOCKED`; send; mark `sent`; on failure increment `attempts`, store `last_error`, back off (1, 5, 30, 120 minutes), mark `failed` after 5 attempts. Commit per batch.
- Worker: `python -m app.worker` loops every `WORKER_TICK_SECONDS`, runs the registered jobs, updates `worker_heartbeat`, handles `SIGTERM`, logs job counts and durations; a failing job logs and does not stop the loop.
- Senders: `SmtpSender` (STARTTLS optional), `InMemorySender` for tests (chosen when `ENV=test`).
- Templates never include a confidential ticket's title or description.
**Tests:** rendering per template; send success, retry with backoff, final failure; two concurrent workers never send a row twice; the loop survives a failing job and updates the heartbeat.
**Done when:** gate passes.
**Do not:** use a queue library; send email inside request handling.

---

### B08: Signup, verification, approval chain, re-apply (R1)

**Goal:** the signup lifecycle of decisions D-8 and D-11.
**Depends on:** B06, B07. **Reads:** `app/services/auth.py`, `app/services/email_outbox.py`, `app/api/deps.py`, `app/core/events.py`. **Needs rules:** R.1 (D-8), A.6. **Endpoints:** `POST /auth/signup`, `/auth/verify-email`, `/auth/resend-verification`, `/auth/reapply`, `GET /signup-requests`, `POST /signup-requests/{id}/approve`, `/signup-requests/{id}/reject`.
**Creates:** `app/policy/permissions.py` (signup functions: `can_decide_signup(actor, requested_role, approved_role, applicant_id)`), `app/schemas/signup.py`, `app/services/signup.py`, `app/api/routers/signup.py`, `tests/api/test_signup.py`, `tests/api/test_signup_approvals.py`, `tests/unit/test_permissions_signup.py`. **Modifies:** `app/main.py`.
**Spec:**
- **signup:** validate the email domain against `ALLOWED_EMAIL_DOMAINS` (422 `fields.email` listing the allowed domains), the password policy, an active department, and a role among `employee`, `admin`, `super_admin`. New email: create the user (`global_role=employee`, `state=pending_verification`, home department = requested department), a `pending` signup request, a 24-hour verification token (SHA-256), enqueue `verify_email`. Existing email: reveal nothing; if `pending_verification` behave like resend, otherwise enqueue `account_exists_notice`. Always 202 with the same message. Rate limit 5 per hour per IP and per email.
- **verify-email:** unknown or used token gives 422 (`fields.token`); expired gives 410 `token_expired`; success marks the token used, sets `email_verified_at`, moves the user to `pending_approval`, writes audit, publishes `SignupVerified`; response `{state:'pending_approval'}`.
- **resend-verification:** always 202; for a `pending_verification` user invalidate old tokens, issue and send a new one; rate limit 3 per hour per email.
- **reapply:** verify email and password with the login lockout rules; only a `rejected` user may reapply, otherwise 409 `conflict`; wrong password gives **403 `forbidden`** with `fields.password` (never 401); success creates a new `pending` request, updates the home department, sets the state to `pending_approval` (the email is already verified), publishes `SignupVerified`; 202.
- **GET /signup-requests:** Admin or Super Admin (`users.approve_employee`); `status` filter; only requests whose user is `pending_approval` appear under `pending`; default newest first; each item has `can_approve` from the policy function. Items use the `SignupRequest` shape (name, email, `email_verified`, requested and approved role and department, decision fields).
- **approve:** the actor needs authority for the higher of `requested_role` and `approved_role` (rank employee, admin, super_admin): Employee by any Admin or Super Admin; Admin by a Super Admin; Super Admin by a Super Admin who is not the applicant; never the applicant. Request must be `pending`. Effects: user `active` with the approved role (`global_role`) and department, `approved_by_id`, `approved_at`; request `approved`; enqueue `signup_approved`; audit (security limited); publish `SignupDecided`.
- **reject:** reason 5 to 1000 characters; same authority on the requested role; user `rejected`; request `rejected` with the reason; enqueue `signup_rejected`; audit; publish `SignupDecided`.
**Tests:** every branch above; the full approval-chain matrix (employee, admin, super_admin requests against employee-approvers, Admin, Super Admin, and self); identical generic responses for new and existing emails; domain rejection; expired and used tokens; rate limits; reapply paths; no public endpoint returns 401.
**Done when:** gate passes.
**Do not:** reveal account existence; return 401 from a public endpoint.

---

### B09: Users, Spoke mapping, administrators, protected actions (R1)

**Goal:** user administration and the Super Admin safeguards of D-9.
**Depends on:** B08. **Reads:** `app/policy/permissions.py`, `app/services/signup.py`, `app/models/identity.py`, `app/models/org.py`. **Needs rules:** R.1 (D-1, D-7, D-9). **Endpoints:** `GET /users`, `GET /users/lookup`, `GET /departments/{id}/members`, `PATCH /users/{id}/roles`, `POST /users/{id}/deactivate`, `POST /users/{id}/activate`, `GET /admins`, `POST /admins`, `DELETE /admins/{user_id}`, `GET /protected-actions`, `POST /protected-actions`, `POST /protected-actions/{id}/approve`, `/protected-actions/{id}/reject`.
**Creates:** `app/schemas/users.py`, `app/services/users.py`, `app/services/spokes.py`, `app/services/protected_actions.py`, `app/api/routers/users.py`, `app/api/routers/admins.py`, `app/api/routers/protected_actions.py`, `tests/api/test_users.py`, `tests/api/test_admins.py`, `tests/api/test_protected_actions.py`, `tests/unit/test_permissions_users.py`. **Modifies:** `app/policy/permissions.py`, `app/main.py`.
**Spec:**
- **GET /users:** flag `users.manage_roles` or `admins.manage`; excludes `pending_verification`; filters `q` (name or email contains), `role`, `state`, `department_id` (home or active Spoke mapping); `Paged<UserListItem>`.
- **GET /users/lookup:** any active user; `q` at least 2 characters else 422; active users only; maximum 20; `UserRef[]`.
- **GET /departments/{id}/members:** any active user; active users whose home department is `id` or who have an active Spoke mapping to it, by name; `UserRef[]`; 404 for an unknown department.
- **PATCH /users/{id}/roles:** body `{spoke_departments, reason}` (reason 5 to 1000); replaces the user's active Spoke mappings with the given set (adds and revokes); requires `users.manage_roles` (Super Admin, or Admin while the policy toggle is on); target must be `active`; audit every added and revoked mapping; returns `UserListItem`.
- **POST /users/{id}/deactivate:** reason required. Admin (needs `users.manage_roles`): employee targets only (including Spokes). Super Admin: any target; a Super Admin target creates a `deactivate_super_admin` protected action and returns `result='protected_request_created'` with its id. Never self. Direct deactivation: state `deactivated` with actor, time, reason; revoke refresh tokens; revoke Spoke mappings; clear the user as any department's escalation contact; `open_ticket_count` = tickets where the user is owner or assignee and the status is not `resolved`, `closed`, or `cancelled`; audit; publish `UserDeactivated`. Response `{result, open_ticket_count, protected_action_id}`.
- **POST /users/{id}/activate:** same authority as deactivate; target must be `deactivated` and previously approved (`approved_at` set), else 409; returns `UserListItem`.
- **Admins:** `GET /admins` (flag `admins.manage`) returns accounts with role `admin` or `super_admin` in any state; `POST /admins {user_id}` promotes an active employee to `admin`; `DELETE /admins/{user_id}` demotes an `admin` to `employee`; a `super_admin` target returns 409 `protected_action_blocked` (use a protected action). Audit as security limited.
- **Protected actions (flag `superadmins.protect`):** list with `status` filter and `can_decide` (pending, not expired, caller is neither requester nor target). Create: target must be an active Super Admin, not the caller, no pending request of the same kind for the target (409), and the action must not leave fewer than two active Super Admins (409 `protected_action_blocked`); `expires_at` is created plus 72 hours. Approve: caller differs from requester and target; request pending and not expired; lock the active Super Admin rows, **re-check the minimum of two**, then execute (`deactivate_super_admin` runs the deactivation effects; `demote_super_admin` sets the role to `admin`); mark `approved`; audit; publish `ProtectedActionDecided`. Reject: any other Super Admin with a reason. Super Admins are never deleted.
**Tests:** permission matrix per actor and target; every deactivation effect; protected-action rules (same person, target, third Super Admin, blocked at two, expiry, concurrent double approval); `open_ticket_count`; lookup and members return only `UserRef`; self-deactivation refused; Admin cannot touch Admin or Super Admin accounts.
**Done when:** gate passes.
**Do not:** let an Admin act on Admin or Super Admin accounts; hard-delete users; execute a protected action without a second Super Admin.

---

### B10: Departments, categories, grants, policy (R1)

**Goal:** organization configuration.
**Depends on:** B09. **Reads:** `app/models/org.py`, `app/models/policy.py`, `app/policy/permissions.py`, `app/services/policy.py`. **Needs rules:** R.1 (D-3, D-6, D-7), R.5, A.6. **Endpoints:** `GET /departments`, `POST /departments`, `PATCH /departments/{id}`, `POST /departments/{id}/spokes`, `DELETE /departments/{id}/spokes/{user_id}`, `PUT /departments/{id}/escalation`, `POST /departments/{id}/categories`, `PATCH /categories/{id}`, `DELETE /categories/{id}`, `GET /confidential-grants`, `POST /confidential-grants`, `DELETE /confidential-grants/{id}`, `GET /policy`, `PUT /policy`.
**Creates:** `app/schemas/org.py`, `app/schemas/policy.py`, `app/services/departments.py`, `app/services/categories.py`, `app/services/confidential_grants.py`, `app/services/policy_admin.py`, `app/api/routers/departments.py`, `app/api/routers/categories.py`, `app/api/routers/confidential_grants.py`, `app/api/routers/policy.py`, `tests/api/test_departments.py`, `tests/api/test_categories.py`, `tests/api/test_confidential_grants.py`, `tests/api/test_policy.py`. **Modifies:** `app/policy/permissions.py`, `app/main.py`.
**Spec:**
- **Departments:** `GET` returns `Department` with `spokes`, `escalation_contact`, flat `categories`, and `accepts_tickets` (active and at least one active Spoke); inactive departments only for callers with `departments.manage`. `POST {id, name}` needs `departments.manage`, validates the code pattern, 409 on a duplicate, starts inactive. `PATCH {name?, active?}`: activating requires at least one active Spoke (409). Spoke add and remove (`departments.manage`): add needs an `active` user and 409 on duplicates; remove sets `revoked_at`; removing the last Spoke of an active department is allowed and makes `accepts_tickets` false. `PUT /departments/{id}/escalation {contact_id}`: the contact must be an active member (home department or Spoke) or null.
- **Categories:** `POST {name, confidential}`; unique name within the department; `PATCH {name?, active?, confidential?}`; `DELETE` sets `active=false` (204). One level.
- **Grants (flag `confidential.manage`):** list with filters; create requires a confidential, active category and an `active` user (409 on duplicate); delete revokes (204); every change audited as security limited and publishes `ConfidentialGrantChanged`.
- **Policy:** `GET` for Admin and Super Admin returns the current `PolicyConfig`; `PUT` (`policy.manage`) validates every range and cross-field rule of A.6 (all four priorities present; `sla_mode` must be `calendar`, otherwise 422 `fields.sla_mode`), inserts a new `policy_versions` row (never updates), audits old and new, and returns the saved config. Tickets read the current version at the time of each calculation.
- Admins may use the department endpoints only while `admins_can_manage_departments` is true (Super Admin always).
**Tests:** each rule; authority per role and the toggle; accepts-tickets computation; activation guard; grant lifecycle; policy validation and versioning.
**Done when:** gate passes.
**Do not:** allow code edits, hard deletes, or per-department policies.

---

### B11: Access policy: visibility and allowed actions (R1)

**Goal:** the single place that decides who can see a ticket and which actions are available. This part carries the most security risk; test it exhaustively.
**Depends on:** B10. **Reads:** `app/policy/*`, `app/models/*`, `app/api/deps.py`. **Needs rules:** R.2, R.3.
**Creates:** `app/policy/relationships.py`, `app/policy/visibility.py`, `app/policy/allowed_actions.py`, `app/policy/actors.py` (`load_actor(session, user_id)` for notification recipients and the scheduler), `tests/unit/test_visibility.py`, `tests/unit/test_allowed_actions.py`, `tests/unit/test_relationships.py`.
**Spec:**
- Relationship flags for (actor, ticket): requester, owner, assignee, collaborator, Spoke of the ticket's department, confidential access (Super Admin, or an active grant on the ticket's category), admin, super admin.
- `visible_ticket_clause(actor)` returns one SQLAlchemy boolean clause implementing R.2 (used by every ticket query), and `can_view_ticket(session, actor, ticket)` returns the same decision for a loaded ticket. They must agree; add a test comparing them over a generated matrix.
- `compute_allowed_actions(actor_ctx, ticket, policy, now)` returns the lowercase `TicketAction` list from the R.3 table. `classify_denial(action, actor_ctx, ticket)` returns `forbidden` when the actor class never has the action and `invalid_transition` otherwise.
- Reopen availability uses the policy's `reopen_window_days` and `max_reopens`, measured from `resolved_at`.
- Policy code has no side effects and takes no HTTP objects.
**Tests (parametrized):** visibility for every actor class (requester, assignee, collaborator, Spoke with and without grant, Spoke of another department, Admin with and without grant, Super Admin, unrelated employee) against confidential and non-confidential tickets; allowed actions for every status times every actor class; reopen window edges; clause and loaded decisions agree; a confidential ticket is never visible to a Spoke or Admin without a grant.
**Done when:** gate passes and the matrix is complete.
**Do not:** duplicate this logic anywhere else.

---

### B12: SLA engine: timers, levels, escalation recipients (R1)

**Goal:** timer lifecycle, level computation, and escalation recipient logic. The scheduler (B19) only calls into this part.
**Depends on:** B11. **Reads:** `app/models/sla.py`, `app/models/ticket.py`, `app/core/events.py`, `app/core/clock.py`, `app/policy/*`, `app/services/policy.py`. **Needs rules:** R.4, R.5, R.6.
**Creates:** `app/services/sla/__init__.py`, `due_time.py`, `timers.py`, `levels.py`, `sla_object.py`, `escalation.py`, `app/services/handlers/sla_handlers.py`, `tests/unit/test_due_time.py`, `tests/unit/test_levels.py`, `tests/integration/test_sla_handlers.py`, `tests/integration/test_escalation_recipients.py`. **Modifies:** `app/services/handlers/__init__.py`.
**Spec:**
- `due_time.py`: `scaled_hours(hours)` (multiplies by `SLA_TIME_SCALE`); `calculate_due(start, hours)` for calendar mode (the signature takes the mode and raises for `business`); `add_business_days(start, n)` skipping Saturday and Sunday in IST (Friday 2026-10-30 10:00 IST plus 3 business days is Wednesday 2026-11-04 10:00 IST).
- `timers.py`: `start`, `restart` (increments `cycle`, resets `level` to 0), `pause`, `resume`, `mark_met`, `stop`, and `reconcile(ticket)` which, from the ticket's status and fields alone, makes the timer set correct (R.4). `reconcile` is idempotent.
- `levels.py`: pure `timer_level(timer, now)` implementing the thresholds of R.5 (`warning_at`, `due_at`, `l3_at`); `recompute_ticket(session, clock, ticket)` sets each timer's `level`, the ticket's `escalation_level` (maximum over active timers), and `update_overdue`.
- `sla_object.py`: builds the `SlaState` object of Appendix A.3 (governing timer, `paused`, `stopped`, `due_at`, label) per R.5.
- `escalation.py`: `resolve_recipients(session, ticket, level)` per R.6 including fallbacks, **filtering every recipient through the visibility policy** (confidential tickets only reach users who can see them, falling back to Super Admins); `record_step(...)` inserts into `escalation_events` with `ON CONFLICT DO NOTHING` and returns whether it was newly inserted.
- Event handlers (registered in `register_all`): `TicketCreated`, `TicketAcknowledged`, `TeamUpdateRecorded`, `TicketStatusChanged`, `TicketEtaChanged`, `TicketPriorityChanged`, `TicketResolved`, `TicketClosed`, `TicketCancelled`, `TicketReopened`, `TicketTransferred`; each maps to the timer operations in R.4, then calls `recompute_ticket`.
**Tests:** time travel with `FrozenClock` for every timer and threshold per priority; pause and resume; priority change recomputing; reopen and transfer restarting cycles; business-day examples; `SLA_TIME_SCALE`; recipient resolution with and without a contact, with confidential tickets, with no Admins; idempotent `record_step`; the `SlaState` object for every ticket status.
**Done when:** gate passes.
**Do not:** send notifications here, read wall-clock time, or loop over all tickets.

---

### B13: Ticket reads: list, detail, timeline (R1)

**Goal:** every ticket read, with the visibility filter on every query.
**Depends on:** B12. **Reads:** `app/policy/*`, `app/services/sla/sla_object.py`, `app/core/pagination.py`, `app/models/ticket.py`. **Needs rules:** R.2, R.3, R.8, R.9. **Endpoints:** `GET /tickets`, `GET /tickets/{id}`, `GET /tickets/{id}/timeline`.
**Creates:** `app/schemas/tickets.py`, `app/queries/tickets.py`, `app/services/ticket_reads.py`, `app/api/routers/tickets.py`, `tests/api/test_ticket_list.py`, `tests/api/test_ticket_detail.py`, `tests/api/test_ticket_timeline.py`. **Modifies:** `tests/factories.py`, `app/main.py`.
**Spec:**
- **GET /tickets:** `scope` `mine` (requester or collaborator), `assigned` (assignee is the caller), `queue` (caller must be a Spoke; tickets of all the caller's departments, narrowed by `department_id` if given and one of them, else 403), `all` (flag `tickets.view_all`, else 403). The visibility clause is **always** applied. Filters, `sla_state`, `status` (including `open`), `q`, sorting, and the default `urgency` order exactly as R.9. Eager-load department, category, people, collaborators, attachments, and timers (no N+1 queries). Response `Paged<Ticket>` with `sla` and `allowed_actions` on each item.
- **GET /tickets/{id}** (the id is the ticket number): `Ticket`. An unknown or non-visible ticket returns the identical 404 `not_found`.
- **GET /tickets/{id}/timeline:** `TimelineEvent[]` oldest first, built from `ticket_events`; requesters and collaborators receive only `is_public` events with `public_detail` where present; internal notes and staff-only events only for the responsible team and the assignee. Non-visible ticket: 404.
**Tests:** visibility through the API for every actor class and confidential case; each scope; each filter value; default order; sort whitelist; totals never include hidden tickets; constant query count as page size grows; detail and timeline redaction; 404 identical for missing and hidden.
**Done when:** gate passes.
**Do not:** compute SLA state in the read path beyond reading stored timers; reveal a hidden ticket in any message.

---

### B14: Attachments and ticket creation (R1)

**Goal:** upload files first, then create tickets that link them.
**Depends on:** B13. **Reads:** `app/services/ticket_reads.py`, `app/schemas/tickets.py`, `app/policy/*`, `app/core/events.py`. **Needs rules:** R.1 (D-5, D-12), R.10, A.6. **Endpoints:** `POST /attachments`, `GET /attachments/{id}/download`, `POST /tickets`.
**Creates:** `app/services/tickets.py`, `app/services/ticket_numbers.py`, `app/services/attachments.py`, `app/integrations/storage/__init__.py`, `base.py`, `local.py`, `app/integrations/scanner/__init__.py`, `base.py`, `noop.py`, `app/schemas/attachments.py`, `app/api/routers/attachments.py`, `tests/api/test_ticket_create.py`, `tests/api/test_attachments.py`, `tests/integration/test_ticket_numbers.py`. **Modifies:** `app/api/routers/tickets.py`, `app/main.py`.
**Spec:**
- **POST /attachments** (any active user): multipart `file`; validate size (413 `file_too_large`), type and sniffed content (415 `unsupported_file_type`; declared and sniffed types must agree) per R.10; sanitize the display name (basename only, control characters removed, at most 150 characters); store under a random key (never the user's name in a path); run the `Scanner` (the default `NoopScanner` returns `clean`; a real scanner may return `pending` or `infected`); create an unlinked attachment owned by the uploader; 201 `Attachment`. A user may hold at most `max_files` unlinked uploads.
- **POST /tickets** (JSON): `{department_id, category_id, title, description, priority, confidential, attachment_ids}`. The department must have `accepts_tickets` (422 `fields.department_id` otherwise); the category must belong to it and be active, and is required when the department has active categories; `confidential` is forced true when the category is confidential; `requested_priority` and `priority` both start as the given priority; `attachment_ids` must be the caller's unlinked, non-`infected` attachments (at most `max_files`) and become linked. Ticket number `IBX-{code}-{IST year}-{6 digits}` from `ticket_counters` incremented under a row lock; `origin_department_code` stored; status `new`; `sla_started_at` is now; audit; publish `TicketCreated`; response 201 `Ticket`.
- **GET /attachments/{id}/download:** the viewer must be able to see the ticket (unlinked: only the uploader); only `clean` files; `Content-Disposition: attachment; filename*=UTF-8''...` and `X-Content-Type-Options: nosniff`; streamed. Not allowed: 404.
- Storage interface: `save(stream, key_hint) -> key`, `open(key) -> stream`; `LocalStorage` writes below `ATTACHMENT_DIR` and refuses path traversal.
**Tests:** each validation and the required-category logic; confidential forcing; number format, uniqueness under 20 concurrent creations in different threads (real commits), IST year boundary; attachment limits, sniff mismatch, traversal-style names, linking rules, hidden attachment download; events published.
**Done when:** gate passes.
**Do not:** trust the client's content type or filename, expose storage keys, or allow creation in a department without Spokes.

---

### B15: Workflow A: acknowledge, assign, status, hold, ETA, priority (R1)

**Goal:** the first half of the ticket state machine.
**Depends on:** B14. **Reads:** `app/policy/allowed_actions.py`, `app/policy/visibility.py`, `app/services/ticket_reads.py`, `app/services/tickets.py`, `app/core/events.py`, `app/services/audit.py`. **Needs rules:** R.3, R.4, R.7, R.8, A.6. **Endpoints:** `POST /tickets/{id}/acknowledge`, `/assign`, `/status`, `/hold`, `/eta`, `/priority`.
**Creates:** `app/services/workflow/__init__.py`, `common.py` (lock the ticket, authorize through the policy, write the timeline event, bump `updated_at`, build the response), `progress.py`, `app/schemas/workflow.py`, `app/api/routers/ticket_workflow.py`, `tests/api/test_workflow_ack_assign.py`, `tests/api/test_workflow_status_eta_priority.py`, `tests/unit/test_workflow_common.py`. **Modifies:** `app/main.py`.
**Every operation:**
1. Lock the ticket (`FOR UPDATE`). Unknown or not visible: 404 `not_found`.
2. Authorize: if the action is not in `compute_allowed_actions`, use `classify_denial` for 403 `forbidden` or 409 `invalid_transition`.
3. Validate cross-field rules (422 with `fields`).
4. Apply, write the `ticket_events` row (public and staff texts per R.8), audit, publish events, return the updated `Ticket`.
**Operation rules:**
- **acknowledge** (status `new`; the actor is on the responsible team and is not the requester): `owner_id` becomes the actor; with an `eta` set it; without an `eta` keep `no_eta_reason` in the event data and set `next_checkpoint_at`; status `acknowledged`; `acknowledged_at` and `last_team_update_at` now; publish `TicketAcknowledged` and `TeamUpdateRecorded`.
- **assign:** a Spoke may assign only to an active member of the ticket's department (home department or Spoke mapping); Admin or Super Admin to any active user with a required reason; assigning to the current assignee is 422; status `acknowledged` or `reopened` becomes `assigned`, other statuses unchanged; the event is public ("Assigned to X"); publish `TicketAssigned`.
- **status:** `in_progress` is start work (from `acknowledged`, `assigned`, `reopened`) or resume (from `awaiting_requester`, `on_hold`, which clears `awaiting_since`, `hold_reason`, `hold_review_date`); `awaiting_requester` (from `in_progress`) requires `message` (5 or more characters), writes it as a public comment by the actor, sets `awaiting_since`. Publish `TicketStatusChanged` and `TeamUpdateRecorded`.
- **hold** (from `in_progress`): `reason` and a future `review_date`; status `on_hold`; publish `TicketStatusChanged` and `TeamUpdateRecorded`.
- **eta:** a future `eta` different from the current one, `reason` required; the event is public and includes the reason in the staff text; publish `TicketEtaChanged` (with `is_extension`) and `TeamUpdateRecorded`.
- **priority:** responsible team only; reason required; the new value must differ; the event is staff-only; publish `TicketPriorityChanged`.
**Tests:** every operation for allowed and denied actor classes and statuses; cross-field validation; events and audit rows; two concurrent acknowledgements (one wins, the other gets `invalid_transition`); the requester cannot acknowledge; assign restrictions.
**Done when:** gate passes.
**Do not:** change a status outside `app/services/workflow/`; skip the lock.

---

### B16: Workflow B: resolve, confirm, reopen, cancel, close, transfer (R1)

**Goal:** the second half of the state machine.
**Depends on:** B15. **Reads:** `app/services/workflow/common.py`, `progress.py`, `app/services/sla/timers.py`, `app/policy/*`. **Needs rules:** R.3, R.4, R.7, R.8, A.6. **Endpoints:** `POST /tickets/{id}/resolve`, `/confirm-closure`, `/reopen`, `/cancel`, `/close`, `/transfer`.
**Creates:** `app/services/workflow/closure.py`, `transfer.py`, `system.py` (`close_system(session, clock, ticket_id)` for the scheduler), additions to `app/schemas/workflow.py` and `app/api/routers/ticket_workflow.py`, `tests/api/test_workflow_closure.py`, `tests/api/test_workflow_transfer.py`. **Modifies:** `app/schemas/workflow.py`, `app/api/routers/ticket_workflow.py`.
**Operation rules (same pattern as B15):**
- **resolve:** from `in_progress`; `summary` 10 to 2000; the actor is the assignee, owner, Admin, or Super Admin and never the requester; sets `resolved_at` and `resolution_summary`; public event; publish `TicketResolved`.
- **confirm-closure:** requester only, status `resolved`; optional `rating` (1 to 5) and `comment` stored; status `closed`, `closed_at`, `close_reason='confirmed'`; publish `TicketClosed`.
- **reopen:** from `resolved` or `closed`; the requester or the responsible team; reason required; within `reopen_window_days` of `resolved_at` and `reopen_count` below `max_reopens`, else 409 `invalid_transition` with `details`; status `reopened`, `reopen_count` plus one, clears `resolved_at`, `closed_at`, `resolution_summary` (kept in the timeline), `last_team_update_at`, `eta`, `next_checkpoint_at`; owner and assignee are kept; publish `TicketReopened`.
- **cancel:** the requester only while `new`; the responsible team from any active status; reason required; status `cancelled`; publish `TicketCancelled`.
- **close** (administrative): the responsible team, status `resolved` only, reason required; status `closed`, `close_reason='admin'`; publish `TicketClosed`.
- **transfer:** the responsible team; the target department must differ and have `accepts_tickets`; `category_id` required when the target has active categories and must belong to it; reason required. Effects: new department and category, status `new`, owner, assignee, ETA, checkpoint, hold and awaiting fields cleared, `sla_started_at` now; `confidential` becomes true if the new category is confidential and is never downgraded; ticket number and `origin_department_code` unchanged; the response is built before the access check of the new state, so the actor receives the updated `Ticket` even if they can no longer see it (the next read returns 404); publish `TicketTransferred`.
- **close_system:** closes a `resolved` ticket with `close_reason='auto'` and no actor; used only by B19.
**Tests:** every operation for allowed and denied cases; reopen window and count edges with `FrozenClock`; transfer side effects and access loss; confidential never downgraded; auto-close path; timeline and audit rows.
**Done when:** gate passes.
**Do not:** add any status transition that is not in R.4; allow the requester to resolve.

---

### B17: Comments and collaborators (R1)

**Goal:** conversation on a ticket and sharing.
**Depends on:** B15. **Reads:** `app/services/workflow/common.py`, `app/policy/*`, `app/schemas/tickets.py`. **Needs rules:** R.3, R.7, R.8. **Endpoints:** `POST /tickets/{id}/comments`, `POST /tickets/{id}/collaborators`, `DELETE /tickets/{id}/collaborators/{user_id}`.
**Creates:** `app/services/comments.py`, `app/services/collaborators.py`, `app/api/routers/ticket_comments.py`, `tests/api/test_comments.py`, `tests/api/test_collaborators.py`. **Modifies:** `app/schemas/tickets.py`, `app/main.py`.
**Spec:**
- **comments:** `{body, internal}`, body 1 to 5000; a public comment needs `comment` in `allowed_actions`, an internal note needs `internal_note`; not on `closed` or `cancelled`. A comment or note by the team or the assignee publishes `TeamUpdateRecorded`. A requester's public comment on an `awaiting_requester` ticket moves it to `in_progress` with a public system event and `TicketStatusChanged`. Publish `CommentAdded`. Response `TimelineEvent` (201).
- **collaborators:** needs `manage_collaborators`; the target must be an active user other than the requester; duplicates 409; response `Ticket`; audit (security limited when the ticket is confidential); publish `CollaboratorChanged`.
- Comments are immutable.
**Tests:** permissions per actor class and status; internal never visible to requesters or collaborators; auto-resume; the update timer resets only for team comments; collaborator visibility including on a confidential ticket; audit.
**Done when:** gate passes.
**Do not:** allow editing or deleting a comment, or an internal note from a requester.

---

### B18: Notifications: events, recipients, portal and email (R1)

**Goal:** turn domain events into portal notifications and emails.
**Depends on:** B16, B17. **Reads:** `app/core/events.py`, `app/services/email_outbox.py`, `app/policy/actors.py`, `app/policy/visibility.py`, `app/services/sla/escalation.py`. **Needs rules:** R.6, R.7. **Endpoints:** `GET /notifications`, `GET /notifications/unread-count`, `POST /notifications/{id}/read`, `POST /notifications/read-all`.
**Creates:** `app/services/notifications.py`, `app/services/handlers/notification_handlers.py`, `app/services/handlers/recipients.py`, `app/templates/email/` additions (one template pair per notification kind in R.7), `app/schemas/notifications.py`, `app/api/routers/notifications.py`, `tests/integration/test_notification_handlers.py`, `tests/api/test_notifications.py`, `tests/unit/test_email_masking.py`. **Modifies:** `app/services/handlers/__init__.py`, `app/main.py`.
**Spec:**
- One handler per event of R.7. Each computes recipients (R.7 table), **removes anyone who cannot see the ticket**, never notifies the acting user, creates a `notifications` row (with a `dedupe_key` for scheduled events) and, where the table says email, an outbox row, all in the event's transaction.
- `critical` is true for escalation events (level 2 and above), protected-action events, and a deactivation that leaves open tickets; there are no preferences in Release 1.
- **Masking:** for a confidential ticket the portal text is generic ("Update on {id}") and the email contains the ticket number, department, status, priority, and a link only; never the title, description, comments, or resolution text. For other tickets the texts follow R.7.
- **Endpoints:** list own notifications (`unread`, paging, newest first) as `Paged<Notification>` (`read`, `critical`, `text`, `ticket_id` as the ticket number, `kind`), unread count, mark one read (404 for another user's), mark all read.
**Tests:** recipients for every event; confidential filtering and masking (Admin without grant, Spoke without grant); critical flags; outbox rows share the transaction; ownership isolation; dedupe keys.
**Done when:** gate passes.
**Do not:** send email inline; include confidential content in any email; notify someone who cannot see the ticket.

---

### B19: Scheduler: escalations, reminders, auto-close, housekeeping (R1)

**Goal:** the worker jobs that make SLA tracking and escalation happen automatically.
**Depends on:** B18. **Reads:** `app/worker/main.py`, `app/worker/jobs/send_outbox.py`, `app/services/sla/*`, `app/services/workflow/system.py`, `app/core/events.py`. **Needs rules:** R.4, R.5, R.6.
**Creates:** `app/worker/jobs/sla_scan.py`, `auto_close.py`, `reminders.py`, `protected_action_expiry.py`, `housekeeping.py`, `app/services/sla/scanner.py`, `tests/integration/test_sla_scan.py`, `test_auto_close.py`, `test_reminders.py`, `test_scheduler_idempotency.py`, `test_housekeeping.py`. **Modifies:** `app/worker/jobs/__init__.py`.
**Spec:**
- **sla_scan:** take an advisory lock so only one scanner runs at a time; select active timers whose next threshold has passed (`FOR UPDATE SKIP LOCKED`, batch 100) and process each in its own savepoint. For each timer compute the due steps from the R.6 step table. For each due step call `record_step`; only when it was newly inserted update the timer's `level`, call `recompute_ticket`, and publish `SlaWarningRaised` (level 1) or `EscalationRaised` (level 2 and above) with the recipients. **Catch-up:** after downtime emit each distinct level once, and for repeated steps only the most recent index.
- **auto_close:** `auto_close` timers past due on `resolved` tickets are closed through `close_system`.
- **reminders:** `requester_reminder` due: one notification to the requester (no auto-close); `hold_review` due: one notification to the owner.
- **protected_action_expiry:** `pending` requests past `expires_at` become `expired`, audited, the requester notified.
- **housekeeping:** delete unlinked attachments older than 24 hours (file and row); delete used or expired email tokens older than 7 days and revoked or expired refresh tokens older than 30 days; delete `rate_limit_hits` older than 1 day. These are the only hard deletes in the system.
- Jobs commit per ticket, are safe in two parallel workers, and safe to re-run. All durations come from the policy and the clock.
**Tests:** per priority the exact step sequence over simulated time for each timer kind; idempotency (run twice and concurrently: one escalation each); recovery (acknowledgement stops escalation and resets the level); a 3-day outage catch-up; pause suspends update and ETA escalation; auto-close at the right business day across a weekend; protected-action expiry; housekeeping deletes only what it should.
**Done when:** gate passes.
**Do not:** read the system clock directly, send email from a job, or process a timer without a row lock.

---

### B20: Audit endpoint and dashboards (R1)

**Goal:** the audit log view and the Release 1 dashboards.
**Depends on:** B16. **Reads:** `app/models/audit.py`, `app/policy/visibility.py`, `app/queries/tickets.py`. **Needs rules:** R.8, R.10. **Endpoints:** `GET /audit`, `GET /dashboard/employee`, `/dashboard/spoke`, `/dashboard/admin`.
**Creates:** `app/queries/audit.py`, `app/services/audit_reads.py`, `app/services/dashboards.py`, `app/schemas/audit.py`, `app/schemas/dashboards.py`, `app/api/routers/audit.py`, `app/api/routers/dashboards.py`, `tests/api/test_audit.py`, `tests/api/test_dashboards.py`. **Modifies:** `app/main.py`.
**Spec:**
- **GET /audit:** flag `audit.view_all` (Admin and Super Admin only, else 403); filters `q` (action or detail contains), `actor_id`, `action`, `ticket_id` (ticket number), `from`, `to`; newest first; `Paged<AuditEntry>`. Super Admin sees everything; Admin never sees `is_security_limited` entries; entries tied to a ticket are additionally filtered by ticket visibility (confidential rule) for Admins.
- **Dashboards:** shapes of Appendix A.3, formulas in R.10, all counts through the visibility clause. `/dashboard/spoke` is scoped to the caller's departments (403 for a non-Spoke). `/dashboard/admin` returns `null` for `sla_met_pct`, `avg_initial_response_seconds`, `reopen_rate_pct`, and `by_department` in Release 1.
**Tests:** scope per role, confidential and security-limited exclusions, every count formula, a non-Spoke denied.
**Done when:** gate passes.
**Do not:** expose audit rows for tickets the caller cannot see.

---

### B21: MFA (TOTP), enabled by configuration (R1)

**Goal:** optional multi-factor login, off by default (D-14).
**Depends on:** B06. **Reads:** `app/services/auth.py`, `app/api/routers/auth.py`, `app/core/security.py`. **Needs rules:** R.1 (D-14). **Endpoints:** `POST /auth/mfa/setup`, `/auth/mfa/confirm`, `/auth/mfa/verify`.
**Creates:** `app/services/mfa.py`, `tests/api/test_mfa.py`, `tests/unit/test_mfa_service.py`. **Modifies:** `app/services/auth.py`, `app/api/routers/auth.py`, `app/schemas/auth.py`, `app/cli.py` (command `mfa-reset`).
**Spec:**
- Enforcement is driven by `MFA_REQUIRED_ROLES` (empty means never required) and the user's `mfa_enabled`. After a correct password: if `mfa_enabled`, login returns `{mfa_required:true, mfa_token}`; else if the user's roles intersect `MFA_REQUIRED_ROLES` (a user is a `spoke` when they have an active mapping), login returns `{mfa_enrol_required:true, mfa_token}`; otherwise `LoginSuccess`.
- `mfa_token` is a 5-minute JWT with purpose `mfa`, accepted only by the three MFA endpoints.
- **setup:** generates a TOTP secret (`pyotp`), stores it encrypted with Fernet (`FIELD_ENCRYPTION_KEY`), returns `{secret, otpauth_uri}`.
- **confirm:** verifies the first code (window plus or minus one step), sets `mfa_enabled`, creates 8 recovery codes (stored hashed), returns `LoginSuccess` plus `recovery_codes` (shown once).
- **verify:** accepts a TOTP code or an unused recovery code; 5 consecutive failures lock the account for 15 minutes (429 `too_many_attempts`); success returns `LoginSuccess`.
- CLI `mfa-reset --email` clears a user's MFA (operator recovery); audited.
**Tests:** all three login paths; enforcement by role and Spoke mapping; code window; recovery code single use; lockout; token purpose isolation; with `MFA_REQUIRED_ROLES` empty nothing changes for any user.
**Done when:** gate passes.
**Do not:** turn MFA on by default or store the secret unencrypted.

---

### B22: Seed data and CLI (R1)

**Goal:** make the real backend usable by the frontend exactly like the mock.
**Depends on:** B20. **Reads:** Appendix S (seed data), `tests/factories.py`, `app/services/*`.
**Creates:** `app/cli.py` (if not present), `app/seed/__init__.py`, `app/seed/data.py`, `app/seed/run.py`, `tests/integration/test_seed.py`, `tests/integration/test_cli.py`.
**Spec:**
- `python -m app.cli create-super-admin --email E --name N` reads the password from `ADMIN_PASSWORD` or a prompt; creates an `active` Super Admin; refuses if the email exists; allowed in every environment (the production bootstrap).
- `python -m app.cli seed` builds Appendix S: nine departments, accounts for every role and state with the password `Ibotix2026Demo`, categories (with the three confidential ones), grants, about 16 tickets covering every status and every escalation level, notifications, and audit entries. Tickets are created through the services using a clock set in the past, then `reconcile` and `recompute_ticket` make timers consistent. Idempotent. **Refuses to run when `ENV=prod`.**
- `python -m app.cli reset-db` (dev and test only) recreates the schema through Alembic. `python -m app.cli export-openapi PATH` writes the OpenAPI JSON.
**Tests:** idempotency; every seeded login works or fails with the documented code; at least one ticket per status and per level; confidential visibility for seeded users (the HR Spoke sees the HR confidential ticket, the Legal Spoke and the Admin do not); prod refusal.
**Done when:** gate passes and the frontend can log in with its mock turned off.
**Do not:** put real credentials in seed data.

---

### B23: Contract conformance and frontend integration (R1)

**Goal:** prove backend and frontend agree.
**Depends on:** B22. **Reads:** `scripts/check_contract.py`, `contract/routes.txt`, Appendix A.
**Creates:** `tests/api/test_contract_shapes.py`, `docs/FRONTEND-INTEGRATION.md`. **Modifies:** `scripts/check_contract.py`.
**Spec:**
- `check_contract.py --full` must report no difference between `contract/routes.txt` and the app.
- `test_contract_shapes.py` calls each endpoint with seeded data and asserts the **exact key sets** and value types of: `Me`, `Department`, `Ticket`, `SlaState`, `TimelineEvent`, `SignupRequest`, `UserListItem`, `ProtectedAction`, `ConfidentialGrant`, `Notification`, `AuditEntry`, `PolicyConfig`, `PublicConfig`, the three dashboards, and the error envelope; and the status code and `error.code` of every row in Appendix A.1.
- `docs/FRONTEND-INTEGRATION.md`: start the backend and worker; in the frontend run `npm run gen:api` against `http://localhost:8000/openapi.json` and fix type differences; set the frontend's `VITE_USE_MOCKS=false`; CORS and cookie settings for the frontend origin; run the frontend E2E suite against the live backend.
- Fix every difference in the backend (never edit Appendix A here only); contract mistakes follow section 4.2.
**Done when:** gate passes with `--full`; the shape tests pass; the frontend runs against the live backend with the same seed.
**Do not:** loosen an assertion to make it pass.

---

### B24: Security hardening and performance (R1)

**Goal:** close security gaps and meet the BRD performance target (list and search about 2 to 3 seconds).
**Depends on:** B23.
**Creates:** `app/core/security_headers.py`, `tests/security/test_authorization_matrix.py`, `tests/security/test_confidentiality_leaks.py`, `tests/security/test_auth_hardening.py`, `scripts/perf_seed.py`, `tests/perf/test_list_performance.py`, `docs/SECURITY.md`. **Modifies:** `app/main.py`, `alembic/versions/` (a new revision for any added indexes).
**Spec:**
- **Headers:** `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Cache-Control: no-store` on all `/api/v1/auth` responses and attachment downloads.
- **Authorization matrix test:** from `contract/routes.txt` and Appendix R.2: for every route and every actor class (anonymous, employee, Spoke, Admin, Super Admin, plus Admin with the toggle off) assert the expected 401, 403, or success class. A new route without a matrix entry fails the test.
- **Confidentiality leak test:** create a confidential ticket and call every endpoint that can reveal tickets as users without access (list, detail, timeline, attachment download, notifications, audit, dashboards, lookup, search `q`); assert nothing about the ticket appears in bodies, counts, headers, or error messages and that hidden and missing tickets return identical 404s.
- **Auth hardening:** lockout, rate limits (signup, resend, forgot, reapply, login), refresh reuse, token tampering, password policy, no account enumeration.
- **Performance:** `perf_seed.py` inserts 50,000 tickets and 200,000 events across the nine departments; the perf test asserts `GET /tickets` (default order, filtered by department and status, and a text search) answers in under 300 ms at the 95th percentile on the test database; use `EXPLAIN` to adjust indexes; no sequential scans on list queries.
- Review upload handling, request size limits, and CORS (no wildcards).
**Done when:** gate passes and the security and performance suites pass.
**Do not:** weaken a test to pass; add dependencies.

---

### B25: Operations: Docker, logging, backups, README (R1)

**Goal:** a repeatable way to run and operate the backend.
**Depends on:** B24.
**Creates:** `Dockerfile`, `docker-compose.full.yml` (api, worker, db, mailpit), `.dockerignore`, `docs/OPERATIONS.md`, `docs/BACKUP-RESTORE.md`, `scripts/backup.sh`, `scripts/restore_check.sh`, additions to `README.md`. **Modifies:** `app/api/routers/health.py`.
**Spec:**
- `Dockerfile`: `python:3.12-slim`, non-root user, installs from `pyproject.toml`; two commands (API with Uvicorn, worker with `python -m app.worker`); healthcheck on `/health/live`; migrations are a separate one-shot command (`alembic upgrade head`), never run at API start.
- `/health/ready` checks the database; new `/health/worker` returns `ok` when the heartbeat is newer than three ticks, else 503 (outside the contract).
- The application connects as a **non-owner database role** that has no `UPDATE` or `DELETE` on `audit_log` and `ticket_events` (the migrator role owns the schema); document the role setup.
- Logging: JSON lines with `request_id`, route, status, duration, actor id (never emails or tokens); worker logs job counts and durations.
- `docs/BACKUP-RESTORE.md`: daily `pg_dump` plus the attachment directory snapshot, retention, a restore drill; RPO and RTO placeholders for the infrastructure team.
- `docs/OPERATIONS.md`: environment variables, first deployment (migrate, create the first Super Admin, `SLA_TIME_SCALE=1.0`), monitoring (heartbeat, outbox `failed` count, error rate), upgrade procedure.
**Done when:** `docker compose -f docker-compose.full.yml up` runs API, worker, database, and mail catcher, and the seeded demo works end to end.
**Do not:** bake secrets into images or run migrations automatically at API start.

---

### B26: Integration, time-travel, and concurrency tests (R1 gate)

**Goal:** prove the BRD section 20 loop and the hard concurrency cases at API level before go-live.
**Depends on:** B25.
**Creates:** `tests/scenarios/` with the files below and `tests/scenarios/helpers.py` (build actors, advance the clock, run worker jobs). **Modifies:** `pyproject.toml` (coverage thresholds).

| Scenario file | Covers |
|---|---|
| `test_01_raise_and_route.py` | Employee raises an HR ticket; all HR Spokes notified; it is in the HR queue |
| `test_02_acknowledge.py` | Spoke acknowledges with ETA; requester sees owner and ETA |
| `test_03_no_ack_escalation.py` | 18h L1, 24h L2 (Spokes, contact, Admins), 48h L3 (Admins, Super Admins); acknowledgement stops it |
| `test_04_delegate.py` | Spoke assigns to a department member; non-member refused; Admin assigns with a reason |
| `test_05_progress_and_stale.py` | Update silence: L1 at 20h, L2 at 24h, L3 at 48h; any team update resets |
| `test_06_eta_extension.py` | Extension needs a reason and notifies the requester; ETA overdue escalation |
| `test_07_transfer.py` | IT ticket moved to HR; same number; fresh response clock |
| `test_08_resolve_confirm_reopen.py` | Summary mandatory; confirmation with rating; reopen window and count |
| `test_09_admin_limits.py` | Admin sees all non-confidential tickets and cannot manage Admins |
| `test_10_superadmin_manages_admin.py` | Super Admin approves and deactivates an Admin |
| `test_11_unauthorized_access.py` | Another employee's ticket returns 404 with no content |
| `test_12_signup_chain.py` | Signup, verify, approve, reject, reapply, login gating |
| `test_13_protected_actions.py` | Second Super Admin required; blocked below two |
| `test_14_confidential.py` | Hidden from Spoke and Admin without a grant; visible after a grant; masked emails |
| `test_15_critical_priority.py` | Escalation contact notified at creation; earlier warning and L3 |
| `test_16_escalation_fallback.py` | No contact: Admins, then Super Admins |
| `test_17_scheduler_restart.py` | 3-day outage then restart: no duplicates, no loss, no flood |
| `test_18_concurrency.py` | 20 parallel creations (unique numbers); two acknowledgements (one wins); two schedulers (one escalation); two outbox workers (one email) |
| `test_19_auto_close.py` | Auto-close after 3 business days across a weekend |
| `test_20_mfa_toggle.py` | With `MFA_REQUIRED_ROLES` empty nobody is asked; with it set Admin must enrol |

**Coverage thresholds:** 85% overall; 95% for `app/policy/` and `app/services/sla/`.
**Done when:** gate passes with scenarios and thresholds. This is the release gate for the backend.
**Do not:** use real sleeps (advance the clock), depend on test order, or lower thresholds.

---

## 6. RELEASE 2 PARTS

Each begins with a contract update (section 4.2), done together with the frontend.

### R2-A: Dashboards and KPI queries
**Goal:** the section 14 KPIs and the Release 2 dashboard fields.
**Depends on:** B26. **Needs rules:** R.2, R.5, R.6, R.10, R.12. **Endpoints:** `GET /reports/kpis`; changed `GET /dashboard/employee`, `/dashboard/spoke`, `/dashboard/admin`.
**Reads:** `app/services/dashboards.py`, `app/schemas/dashboards.py`, `app/queries/tickets.py`, `app/policy/visibility.py`, `app/policy/flags.py`, `app/models/ticket.py`, `app/models/sla.py`, `tests/perf/test_list_performance.py`, `scripts/perf_seed.py`.
**Creates:** `app/queries/kpis.py`, `app/services/kpis.py`, `app/schemas/reports.py`, `app/api/routers/reports.py`, `alembic/versions/r2a_kpi_indexes.py`, `tests/api/test_kpis.py`, `tests/perf/test_kpi_performance.py`.
**Modifies:** `app/main.py`, `app/schemas/dashboards.py`, `app/services/dashboards.py`, `app/models/ticket.py`, `app/models/sla.py` (index declarations only), `contract/routes.txt`, `tests/api/test_dashboards.py`, `tests/api/test_contract_shapes.py`, `tests/security/test_authorization_matrix.py`, `tests/security/test_confidentiality_leaks.py`, `docs/FRONTEND-INTEGRATION.md`.
**Spec:**
- Each R.12 KPI is one query builder in `app/queries/kpis.py` that takes the scoped ticket clause; the service runs them and builds `KpiReport`. Scope and the 403 decision live in `app/policy/` (`can_view_org_reports`, `report_departments`).
- The dashboards reuse the same builders (no second formula).
- Migration `r2a_kpi_indexes` holds only the indexes justified by `EXPLAIN` (likely candidates: `ticket_events (action, ticket_id, at)` partial on the three actions used, `escalation_events (at)`, `tickets (created_at)`).
**Tests:**
- One test per KPI with a hand-built fixture where the expected number is obvious, including the empty case (`null` percentages).
- Visibility: a confidential ticket changes no number for an Admin without a grant; it does for a Super Admin.
- Spoke scope: own departments only; another `department_id` gives 403; employee gives 403.
- Validation: `from >= to`, range over 366 days, unknown department, bad priority give 422 with the field.
- Filters: date range, department and priority each narrow the result.
- Dashboards: the new fields match `/reports/kpis` over the same window.
- Perf: every aggregate under 500 ms on the 50,000-ticket perf seed.
**Done when:** gate passes (`--full` contract check) and the perf test passes.
**Do not:** compute any KPI in Python loops over tickets, bypass the visibility clause, or add KPI fields not in Appendix A.

### R2-B: Exports and saved views
**Goal:** role-scoped CSV, XLSX and PDF exports and user-owned saved views.
**Depends on:** R2-A. **Needs rules:** R.2, R.9, R.12, R.13. **Endpoints:** `GET /reports/export`, `GET|POST /saved-views`, `PATCH|DELETE /saved-views/{id}`; changed `GET /tickets` (two filters).
**Reads:** `app/services/kpis.py`, `app/policy/reports.py`, `app/queries/tickets.py`, `app/services/ticket_reads.py`, `app/api/routers/tickets.py`, `app/services/audit.py`, `app/models/identity.py`, `pyproject.toml`.
**Creates:** `app/models/saved_view.py`, `app/schemas/exports.py`, `app/schemas/saved_views.py`, `app/services/exports/__init__.py`, `app/services/exports/tables.py`, `app/services/exports/writers.py`, `app/services/saved_views.py`, `app/api/routers/exports.py`, `app/api/routers/saved_views.py`, `alembic/versions/r2b_saved_views.py`, `tests/api/test_exports.py`, `tests/api/test_saved_views.py`, `tests/unit/test_export_writers.py`.
**Modifies:** `pyproject.toml`, `app/models/__init__.py`, `app/main.py`, `app/policy/reports.py`, `app/queries/tickets.py`, `app/services/ticket_reads.py`, `app/api/routers/tickets.py`, `contract/routes.txt`, `tests/api/test_ticket_list.py`, `tests/api/test_contract_shapes.py`, `tests/security/test_authorization_matrix.py`, `tests/security/test_confidentiality_leaks.py`, `docs/FRONTEND-INTEGRATION.md`.
**Spec:**
- `tables.py` turns a ticket query or a `KpiReportOut` into a neutral table model (header block, sections, columns, rows); `writers.py` renders that model as CSV (streamed), XLSX or PDF. No business logic in the writers.
- The ticket export reuses `ticket_list_statement` and the visibility clause; rows are read with `yield_per`.
- Saved view `query` is validated by the same code path as `GET /tickets` (one parser for both).
**Tests:**
- Each format: header block present with generated-by, generated-at and filters; correct `Content-Type` and filename; CSV formula cells prefixed.
- Scope: Admin sees the organisation without confidential tickets; Super Admin sees them; Spoke gets department data only and 403 for another department; employee 403.
- Row limits give 422 `fields.format`; bad `type`/`format` give 422.
- Audit row written once per export, security limited when a confidential ticket is included.
- Saved views: CRUD, name rules (length, case-insensitive duplicate 409), 50-view limit, other users' views 404, built-in 403, soft delete hides the view, built-in list by role, "No Update > 24h" returns only stale tickets (BRD FR-47 acceptance).
- New list filters `unassigned` and `awaiting_before`.
- Confidentiality leak test covers both export types in every format.
**Done when:** gate passes (`--full` contract check).
**Do not:** truncate exports silently, bypass the visibility clause, let one user read another's views, or store built-in views.

### R2-C1: Business calendar, holidays, SLA basis overrides
**Goal:** business-hours SLA mode with a holiday calendar, globally and per department or category.
**Depends on:** R2-B. **Needs rules:** R.4, R.5, R.6, R.14. **Endpoints:** `GET|PUT /calendar`, `POST /calendar/holidays`, `DELETE /calendar/holidays/{date}`; changed `PATCH /departments/{id}`, `PATCH /categories/{id}`, `PUT /policy`.
**Reads:** `app/services/sla/due_time.py`, `app/services/sla/timers.py`, `app/services/sla/scanner.py`, `app/services/policy.py`, `app/services/policy_admin.py`, `app/services/departments.py`, `app/services/categories.py`, `app/models/org.py`, `app/models/policy.py`.
**Creates:** `app/models/calendar.py`, `app/schemas/calendar.py`, `app/services/calendar.py`, `app/services/sla/working_time.py`, `app/api/routers/calendar.py`, `alembic/versions/r2c1_business_calendar.py`, `tests/unit/test_working_time.py`, `tests/api/test_calendar.py`, `tests/integration/test_business_mode.py`.
**Modifies:** `app/models/__init__.py`, `app/models/org.py`, `app/main.py`, `app/services/sla/due_time.py`, `app/services/sla/timers.py`, `app/services/sla/scanner.py`, `app/services/policy_admin.py`, `app/services/departments.py`, `app/services/categories.py`, `app/schemas/org.py`, `app/schemas/policy.py`, `app/api/routers/departments.py`, `app/api/routers/categories.py`, `contract/routes.txt`, `tests/unit/test_due_time.py`, `tests/api/test_policy.py`, `tests/api/test_departments.py`, `tests/api/test_categories.py`, `tests/api/test_contract_shapes.py`, `tests/security/test_authorization_matrix.py`, `docs/FRONTEND-INTEGRATION.md`.
**Tests:** working-time arithmetic (inside hours, overnight, weekend, holiday, start outside hours, scaling); basis resolution order; switching a department to business moves due times past non-working time (BRD acceptance); running timers unchanged by a calendar edit; `add_business_days` skips holidays; calendar validation and permissions; audit rows.
**Done when:** gate passes; coverage of `app/services/sla/` stays at least 95%.

### R2-C2: Notification preferences and digests
**Goal:** per-user email preferences and a daily digest, with critical emails locked on.
**Depends on:** R2-C1. **Needs rules:** R.7, R.14. **Endpoints:** `GET|PUT /me/notification-preferences`.
**Reads:** `app/services/notifications.py`, `app/services/email_outbox.py`, `app/services/email_templates.py`, `app/worker/jobs/__init__.py`, `app/policy/visibility.py`.
**Creates:** `app/models/preferences.py`, `app/schemas/preferences.py`, `app/services/preferences.py`, `app/api/routers/preferences.py`, `app/worker/jobs/digest.py`, `app/templates/email/notification_digest.html.j2`, `app/templates/email/notification_digest.txt.j2`, `alembic/versions/r2c2_notification_preferences.py`, `tests/api/test_notification_preferences.py`, `tests/integration/test_digest_job.py`.
**Modifies:** `app/models/__init__.py`, `app/main.py`, `app/services/notifications.py`, `app/services/email_templates.py`, `app/worker/jobs/__init__.py`, `contract/routes.txt`, `tests/unit/test_email_masking.py`, `tests/unit/test_events.py`, `tests/integration/test_worker_loop.py`, `tests/api/test_contract_shapes.py`, `tests/security/test_authorization_matrix.py`, `tests/security/test_confidentiality_leaks.py`, `docs/FRONTEND-INTEGRATION.md`.
**Tests:** each preference value; critical notifications always email (BRD acceptance: muted digest still receives breach emails); digest sent once per IST day at the chosen hour, idempotent across two workers; no digest when nothing is queued; hidden and confidential tickets never leak in a digest; `critical_email` cannot be set.
**Done when:** gate passes.

---

## 7. Assistant rules file (`AGENTS.md` / `CLAUDE.md` at the repository root)

```
Backend assistant rules (FastAPI + PostgreSQL ticketing portal)

When told "Build Bnn":
1. Read docs/BACKEND_GUIDE.md: section 3 (Context Pack), section 4 (gate), the Part Bnn section, Appendix A, and the parts of Appendix R the part names. Read the files the part lists under Reads.
2. Create or modify only the files the part lists. Write complete files.
3. Run the gate from section 4.1 and fix failures until it passes. If it still fails after two attempts with the same cause, stop and report.
4. Report FILES CREATED, FILES MODIFIED, ASSUMPTIONS (maximum 5), the self-check list answered yes or no, and the gate result.
5. Stop. Do not start another part.

Hard rules: contract first (reply CONTRACT_GAP: and stop if Appendix A lacks something); rules first (reply RULE_GAP: and stop if Appendix R lacks something); never invent endpoints, fields, enum values, error codes, or rules. No code comments, no docstrings, no print, no TODO, no type: ignore. Services never commit; routers are thin; all permission and visibility logic lives in app/policy; time only through the injected Clock. Only the allowed packages. Synchronous SQLAlchemy 2.0, real PostgreSQL in tests, no Redis or Celery. Public endpoints never return HTTP 401. A ticket the caller may not see returns the same 404 as a missing ticket. Confidential tickets must never leak through any list, count, search, notification, audit entry, email, or error message.
```

---
## APPENDIX A: API contract v1.1 (single source of truth for frontend and backend)

This appendix is identical in the frontend change request and the backend guide. It amends sections 5 and 6 of `IBOTIX_FRONTEND_SPEC.md`. Where this appendix and the old spec differ, this appendix wins.

### A.1 Conventions

- Base path `/api/v1`. JSON, `snake_case` keys, timestamps ISO 8601 UTC with `Z`. Lists use `Paged<T> = { items: T[]; total: number; page: number; page_size: number }` (query `page` from 1, `page_size` default 25, maximum 100).
- Auth: `Authorization: Bearer <access JWT>` (15 minutes). Refresh token is an httpOnly cookie `refresh_token`; `/auth/refresh` and `/auth/logout` use `credentials: "include"`.
- **Ids:** department `id` is its code (`IT`, `HR`, 2 to 6 uppercase letters). Ticket `id` is the ticket number (`IBX-IT-2026-001234`) and is the only identifier used in ticket URLs. Users, categories, grants, requests, notifications, attachments use opaque string ids.
- **Error envelope (every non-2xx):**
```json
{ "error": { "code": "validation_error", "message": "Human readable", "fields": { "title": "Required" }, "details": {}, "request_id": "..." } }
```
- **Error codes and HTTP status:**

| HTTP | `code` | When |
|---|---|---|
| 401 | `unauthenticated` | missing, invalid, or expired access token (client refreshes once, retries once, then logs out) |
| 401 | `invalid_credentials` | wrong email or password on login (never triggers refresh) |
| 403 | `forbidden` | authenticated but not allowed (non-ticket resources) |
| 403 | `account_state` | correct password but the account is not active; `details.state` is `pending_verification`, `pending_approval`, `rejected`, or `deactivated`; for `rejected` also `details.rejection_reason` |
| 404 | `not_found` | unknown id, **and also any ticket the caller may not see** (identical response) |
| 409 | `conflict` | duplicate or stale state; `invalid_transition` when the action is not allowed in the current status |
| 410 | `token_expired` | verification or reset token expired |
| 413 | `file_too_large` | upload above the limit |
| 415 | `unsupported_file_type` | type not allowed or content does not match |
| 422 | `validation_error` | field errors in `fields` |
| 429 | `too_many_attempts` | login lockout; `details.retry_after_seconds` |
| 429 | `rate_limited` | other rate limits; `details.retry_after_seconds` |
| 500 | `server_error` | unexpected |

  Additional 409 codes: `invalid_transition`, `protected_action_blocked`. **Frontend rule:** the client refreshes on 401 `unauthenticated` only, and never for any `/auth/*` call except `/auth/me`. **Backend rule:** public endpoints (`/public/config`, `signup`, `verify-email`, `resend-verification`, `reapply`, `forgot-password`, `reset-password`) never return 401.

### A.2 Enums (lowercase, exact)

- `Role`: `super_admin`, `admin`, `spoke`, `employee` (there is no resolver role)
- `AccountState`: `pending_verification`, `pending_approval`, `active`, `rejected`, `deactivated`
- `Priority`: `low`, `medium`, `high`, `critical`
- `TicketStatus`: `new`, `acknowledged`, `assigned`, `in_progress`, `awaiting_requester`, `on_hold`, `resolved`, `closed`, `reopened`, `cancelled`
- `TicketAction`: `acknowledge`, `assign`, `transfer`, `change_priority`, `revise_eta`, `start_work`, `ask_requester`, `hold`, `resume`, `resolve`, `confirm_closure`, `reopen`, `cancel`, `close_admin`, `comment`, `internal_note`, `manage_collaborators`
- `SlaKind`: `initial_response`, `progress_update`, `eta`
- `ScanStatus`: `pending`, `clean`, `infected`
- `ProtectedActionKind`: `deactivate_super_admin`, `demote_super_admin`
- `ProtectedActionStatus`: `pending`, `approved`, `rejected`, `expired`
- `SignupStatus`: `pending`, `approved`, `rejected`

### A.3 Types

```ts
interface UserRef { id: string; name: string; email: string; title?: string }

interface Me extends UserRef {
  roles: Role[]                       // always includes 'employee'; adds 'spoke' if mapped; 'admin'; 'super_admin'
  department_id: string | null        // home department code
  spoke_departments: string[]         // department codes
  permissions: string[]               // flags from A.5
  mfa_enabled: boolean
  theme?: 'system' | 'light' | 'dark'
}

interface Category { id: string; department_id: string; name: string; confidential: boolean; active: boolean; sla_mode: SlaMode | null }   // null = inherit

interface Department {
  id: string; name: string; active: boolean
  accepts_tickets: boolean            // active and at least one active Spoke
  spokes: UserRef[]
  escalation_contact: UserRef | null  // one contact per department
  categories: Category[]              // flat, one level
  sla_mode: SlaMode | null            // null = inherit the policy sla_mode
}

interface SlaState {
  level: 0 | 1 | 2 | 3                // L0 normal, L1 warning, L2 breach, L3 persistent
  kind: SlaKind | null
  paused: boolean
  stopped: boolean                    // closed or cancelled
  due_at: string | null               // the breach time of the governing timer
  label: string                       // server text: 'Initial response due', 'Update overdue', 'Awaiting closure', ...
}

interface Attachment { id: string; name: string; size: number; mime: string; scan_status: ScanStatus }

interface Ticket {
  id: string; title: string; description: string
  department_id: string; category_id: string | null; category_name: string | null
  priority: Priority; requested_priority: Priority
  status: TicketStatus; confidential: boolean
  requester: UserRef; owner: UserRef | null; assignee: UserRef | null; collaborators: UserRef[]
  created_at: string; sla_started_at: string; acknowledged_at: string | null
  eta: string | null; next_checkpoint_at: string | null; last_team_update_at: string | null
  resolved_at: string | null; closed_at: string | null; reopen_count: number
  hold: { reason: string; review_date: string } | null
  resolution_summary: string | null
  feedback: { rating: number | null; comment: string | null } | null
  sla: SlaState
  allowed_actions: TicketAction[]
  attachments: Attachment[]
}

interface Comment { id: string; ticket_id: string; author: UserRef; created_at: string; body: string; internal: boolean }
interface TimelineEvent {
  id: string; at: string; actor: UserRef | { id: 'system'; name: 'System' }
  type: 'comment' | 'internal_note' | 'audit'
  action?: string; detail?: string; body?: string
  public: boolean                     // the server already omits non-public events for requesters
}

interface SignupRequest {
  id: string; name: string; email: string; email_verified: boolean
  requested_role: 'employee' | 'admin' | 'super_admin'; requested_department: string
  approved_role?: Role; approved_department?: string
  status: SignupStatus
  decided_by?: UserRef; decided_at?: string; rejection_reason?: string; created_at: string
  can_approve: boolean                // computed by the server for the caller
}

interface UserListItem extends UserRef {
  roles: Role[]; state: AccountState; department_id: string | null
  spoke_departments: string[]; last_login_at: string | null; created_at: string
}

interface ProtectedAction {
  id: string; kind: ProtectedActionKind; target: UserRef; requested_by: UserRef; reason: string
  status: ProtectedActionStatus; decided_by?: UserRef; decision_reason?: string
  created_at: string; expires_at: string
  can_decide: boolean                 // pending, not expired, caller is neither requester nor target
}

interface ConfidentialGrant { id: string; user: UserRef; category: Category; granted_by: UserRef; granted_at: string }

interface Notification { id: string; created_at: string; read: boolean; critical: boolean; text: string; ticket_id?: string; kind: string }
interface AuditEntry {
  id: string; at: string; actor: UserRef | { id: 'system'; name: 'System' }
  action: string; object_type: string; object_id: string | null
  old_value?: unknown; new_value?: unknown; reason?: string; detail?: string
}

interface PolicyConfig {
  initial_response_hours: number                    // 24, same for all priorities
  warning_hours: Record<Priority, number>           // L1 for initial response: 18, 18, 18, 12 (low, medium, high, critical)
  l3_hours: Record<Priority, number>                // L3 for initial response: 48, 48, 36, 30
  update_warning_hours: number                      // 20: L1 after this much silence
  update_cadence_hours: number                      // 24: L2 after this much silence, L3 at twice this
  eta_warning_hours: number                         // 2: L1 before an ETA
  escalation_repeat_hours: number                   // 24: L3 repeats
  requester_reminder_hours: number                  // 48
  auto_close_business_days: number | null           // 3; null disables auto-close
  reopen_window_days: number                        // 7
  max_reopens: number                               // 3
  sla_mode: SlaMode                                 // 'business' counts working time of the BusinessCalendar (R.14)
  admins_can_manage_departments: boolean            // default true
}

interface PublicConfig {
  allowed_email_domains: string[]
  departments: { id: string; name: string }[]      // active departments for the signup form
  attachment_limits: { max_bytes: number; max_files: number; allowed_mime_types: string[] }
  password_min_length: number                       // 12
  first_response_hours: number                      // initial_response_hours from the policy
}

type AgingBucket = '0_2' | '3_7' | '8_14' | '15_30' | '31_plus'

interface DepartmentHealth { department_id: string; name: string; on_track: number; warning: number; breached: number }

interface KpiReport {
  generated_at: string
  filters: { from: string; to: string; department_ids: string[]; priorities: Priority[] }
  sla_compliance: { met: number; missed: number; pct: number | null }
  initial_response: { count: number; avg_seconds: number | null; median_seconds: number | null }
  initial_response_trend: { date: string; count: number; avg_seconds: number | null }[]   // date = IST YYYY-MM-DD, one entry per day in range
  resolution_turnaround: { count: number; avg_seconds: number | null; median_seconds: number | null }
  reopen: { resolved: number; reopened: number; rate_pct: number | null }
  escalations: { l1: number; l2: number; l3: number }
  eta_breach_count: number
  stale_count: number
  overdue_eta_count: number
  unacknowledged_over_24h: number
  persistent_l3_count: number
  aging: { bucket: AgingBucket; count: number }[]                                         // always all five buckets, in order
  departments: {
    department_id: string; name: string; active: number
    by_priority: { low: number; medium: number; high: number; critical: number }
    on_track: number; warning: number; breached: number
    sla_met_pct: number | null
  }[]
  workload: {
    by_assignee: { user: UserRef | null; active: number; breached: number }[]             // user null = unassigned
    by_owner: { user: UserRef | null; active: number; breached: number }[]
  }
  top_categories: { category_id: string | null; name: string; count: number }[]          // at most 10
}

interface EmployeeDashboard { open: number; awaiting_my_response: number; resolved_to_confirm: number; closed: number; assigned_to_me: number;
  assigned_warning: number; assigned_breached: number;
  recent_updates: TimelineEvent[]; attention: Ticket[] }

interface SpokeDashboard { new_unacknowledged: number; approaching_sla: number; breached: number; stale_or_eta_overdue: number; awaiting_requester: number; on_hold: number; resolved_pending_closure: number;
  sla_met_pct: number | null; avg_initial_response_seconds: number | null; reopen_rate_pct: number | null; by_department: DepartmentHealth[];
  attention: Ticket[] }

interface AdminDashboard {
  open_count: number; breached_count: number; l3_count: number; stale_count: number; pending_approvals: number
  sla_met_pct: number | null; avg_initial_response_seconds: number | null; reopen_rate_pct: number | null
  by_department: DepartmentHealth[]
  attention: Ticket[]
}
```

In Release 1 the four nullable `AdminDashboard` fields are `null`; the frontend hides a tile or chart whose value is `null`. From Release 2 the three `AdminDashboard` KPI fields are `null` only when there is no data in the window (denominator 0); `by_department` is always a list.

```ts
type ExportType = 'tickets' | 'kpis'
type ExportFormat = 'csv' | 'xlsx' | 'pdf'

type TicketListQuery = {          // the GET /tickets query parameters except page and page_size
  scope?: 'mine' | 'assigned' | 'queue' | 'all'; q?: string; status?: string[]; priority?: Priority[]
  department_id?: string; category_id?: string; sla_state?: 'unacknowledged' | 'warning' | 'breached' | 'stale'
  escalation_level?: number; requester_id?: string; assignee_id?: string; confidential?: boolean
  overdue_eta?: boolean; unassigned?: boolean; awaiting_before?: string
  created_from?: string; created_to?: string; sort?: string
}

interface SavedView {
  id: string                       // UUID, or 'builtin.<key>' for a built-in view
  name: string
  built_in: boolean
  query: TicketListQuery
  created_at: string | null        // null for built-in views
  updated_at: string | null
}

type SlaMode = 'calendar' | 'business'
type NonCriticalEmail = 'immediate' | 'daily_digest' | 'off'

interface BusinessCalendar {
  timezone: 'Asia/Kolkata'                 // read-only
  working_days: number[]                    // ISO weekdays 1 (Monday) to 7 (Sunday), ascending, at least one
  work_start: string                        // 'HH:MM', 24-hour, IST
  work_end: string                          // 'HH:MM', after work_start
  holidays: Holiday[]                       // active holidays, ascending by date
  updated_at: string | null
}
interface Holiday { date: string; name: string }   // date 'YYYY-MM-DD' (IST)

interface NotificationPreferences {
  non_critical_email: NonCriticalEmail
  digest_hour: number                       // 0 to 23, IST; used when non_critical_email = 'daily_digest'
  critical_email: 'always'                  // read-only; critical emails cannot be turned off
}
```

**Built-in views** (in this order):

| id | name | query | shown to |
|---|---|---|---|
| `builtin.department_breached` | My Department - SLA Breached | `{scope:'queue', sla_state:'breached'}` | Spokes |
| `builtin.no_update_24h` | No Update > 24h | `{scope:'queue' for a Spoke, else 'all' for Admin/Super Admin, else 'mine'; sla_state:'stale'}` | everyone |
| `builtin.unassigned_today` | Unassigned Today | `{scope as above, unassigned:true, created_from: today 00:00 IST}` | everyone |
| `builtin.escalated_l3` | Escalated L3 | `{scope as above, escalation_level:3}` | everyone |
| `builtin.awaiting_requester_48h` | Awaiting Requester > 48h | `{scope as above, awaiting_before: now − 48 hours}` | everyone |

### A.4 Endpoints

**Public and auth**

| Method and path | Request | Response | Notes |
|---|---|---|---|
| GET `/public/config` | none | `PublicConfig` | no auth |
| POST `/auth/signup` | `{name, email, password, requested_role, requested_department}` | 202 `{message}` | same response whether or not the email exists; domain allowlist enforced (422 `fields.email`) |
| POST `/auth/verify-email` | `{token}` | `{state:'pending_approval'}` | 410 `token_expired`; 422 invalid |
| POST `/auth/resend-verification` | `{email}` | 202 | always 202 |
| POST `/auth/reapply` | `{email, password, requested_role, requested_department}` | 202 | only for `rejected` accounts; wrong password gives 403 `forbidden` with `fields.password` (never 401) |
| POST `/auth/login` | `{email, password}` | `LoginResult` | see below |
| POST `/auth/mfa/setup` | `{mfa_token}` | `{secret, otpauth_uri}` | only when MFA is enabled by configuration |
| POST `/auth/mfa/confirm` | `{mfa_token, code}` | `LoginSuccess & {recovery_codes: string[]}` | |
| POST `/auth/mfa/verify` | `{mfa_token, code}` | `LoginSuccess` | |
| POST `/auth/refresh` | cookie | `{access_token, expires_in}` | rotates the refresh cookie |
| POST `/auth/logout` | cookie | 204 | |
| POST `/auth/forgot-password` | `{email}` | 202 | always 202 |
| POST `/auth/reset-password` | `{token, password}` | 204 | 410 `token_expired` |
| GET `/auth/me` | none | `Me` | |

`LoginSuccess = { access_token, expires_in, user: Me }`. `LoginResult = LoginSuccess | { mfa_required: true, mfa_token } | { mfa_enrol_required: true, mfa_token }`.

**Users, signup requests, administrators**

| Method and path | Request | Response | Notes |
|---|---|---|---|
| GET `/users` | query `q, role, state, department_id, page, page_size` | `Paged<UserListItem>` | flag `users.manage_roles` or `admins.manage` |
| GET `/users/lookup` | query `q` (min 2 characters) | `UserRef[]` | any active user; active users only; maximum 20 |
| GET `/departments/{id}/members` | none | `UserRef[]` | any active user; home department or active Spoke mapping |
| PATCH `/users/{id}/roles` | `{spoke_departments: string[], reason}` | `UserListItem` | replaces the Spoke mappings; flag `users.manage_roles`; there is no resolver role |
| POST `/users/{id}/deactivate` | `{reason}` | `{result:'deactivated'\|'protected_request_created', open_ticket_count, protected_action_id}` | |
| POST `/users/{id}/activate` | none | `UserListItem` | |
| GET `/signup-requests` | query `status, page, page_size` | `Paged<SignupRequest>` | flag `users.approve_employee` |
| POST `/signup-requests/{id}/approve` | `{approved_role, approved_department}` | `SignupRequest` | |
| POST `/signup-requests/{id}/reject` | `{reason}` | `SignupRequest` | |
| GET `/admins` | none | `UserListItem[]` | Admin and Super Admin accounts; flag `admins.manage` |
| POST `/admins` | `{user_id}` | `UserListItem` | promote an active employee to Admin |
| DELETE `/admins/{user_id}` | none | `UserListItem` | demote an Admin to employee; a Super Admin target is refused (409 `protected_action_blocked`, use a protected action) |
| GET `/protected-actions` | query `status, page` | `Paged<ProtectedAction>` | flag `superadmins.protect` |
| POST `/protected-actions` | `{kind, target_user_id, reason}` | `ProtectedAction` | |
| POST `/protected-actions/{id}/approve` | none | `ProtectedAction` | |
| POST `/protected-actions/{id}/reject` | `{reason}` | `ProtectedAction` | |

**Departments, categories, grants, policy**

| Method and path | Request | Response | Notes |
|---|---|---|---|
| GET `/departments` | none | `Department[]` | inactive departments only for users with `departments.manage` |
| POST `/departments` | `{id, name}` | `Department` | `id` is the code; immutable |
| PATCH `/departments/{id}` | `{name?, active?, sla_mode?}` | `Department` | cannot activate without an active Spoke (409); `sla_mode` may be `null` (inherit) |
| POST `/departments/{id}/spokes` | `{user_id}` | `Department` | |
| DELETE `/departments/{id}/spokes/{user_id}` | none | `Department` | |
| PUT `/departments/{id}/escalation` | `{contact_id: string \| null}` | `Department` | contact must be an active member of the department |
| POST `/departments/{id}/categories` | `{name, confidential}` | `Category` | |
| PATCH `/categories/{id}` | `{name?, active?, confidential?, sla_mode?}` | `Category` | `sla_mode` may be `null` (inherit) |
| DELETE `/categories/{id}` | none | 204 | soft: sets `active=false` |
| GET `/confidential-grants` | query `category_id, user_id` | `ConfidentialGrant[]` | flag `confidential.manage` |
| POST `/confidential-grants` | `{user_id, category_id}` | `ConfidentialGrant` | category must be confidential |
| DELETE `/confidential-grants/{id}` | none | 204 | revokes |
| GET `/policy` | none | `PolicyConfig` | Admin and Super Admin read |
| PUT `/policy` | `PolicyConfig` | `PolicyConfig` | flag `policy.manage`; creates a new policy version |

**Tickets** (every mutation returns the updated `Ticket`)

| Method and path | Request | Notes |
|---|---|---|
| GET `/tickets` | query `scope` (`mine`, `assigned`, `queue`, `all`), `q`, `status[]` (a status or `open`), `priority[]`, `department_id`, `category_id`, `sla_state` (`unacknowledged`, `warning`, `breached`, `stale`), `escalation_level`, `requester_id`, `assignee_id`, `confidential`, `overdue_eta`, `unassigned`, `awaiting_before`, `created_from`, `created_to`, `sort`, `page`, `page_size` | `Paged<Ticket>`; `queue` uses the caller's Spoke departments (optionally narrowed by `department_id`); `all` needs `tickets.view_all`; default sort `urgency` |
| POST `/tickets` | `{department_id, category_id, title, description, priority, confidential, attachment_ids[]}` | JSON only; 201 |
| GET `/tickets/{id}` | none | 404 for unknown or not visible |
| GET `/tickets/{id}/timeline` | none | `TimelineEvent[]`, oldest first, already filtered |
| POST `/tickets/{id}/comments` | `{body, internal}` | returns `TimelineEvent` |
| POST `/tickets/{id}/acknowledge` | `{eta?, no_eta_reason?, next_checkpoint_at?}` | an ETA, or both reason and checkpoint |
| POST `/tickets/{id}/assign` | `{assignee_id, reason?}` | |
| POST `/tickets/{id}/transfer` | `{department_id, category_id?, reason}` | |
| POST `/tickets/{id}/priority` | `{priority, reason}` | |
| POST `/tickets/{id}/eta` | `{eta, reason}` | |
| POST `/tickets/{id}/status` | `{status:'in_progress'\|'awaiting_requester', message?}` | message required for `awaiting_requester`; `in_progress` also resumes from hold or awaiting |
| POST `/tickets/{id}/hold` | `{reason, review_date}` | |
| POST `/tickets/{id}/resolve` | `{summary}` | |
| POST `/tickets/{id}/confirm-closure` | `{rating?, comment?}` | requester only |
| POST `/tickets/{id}/reopen` | `{reason}` | |
| POST `/tickets/{id}/cancel` | `{reason}` | |
| POST `/tickets/{id}/close` | `{reason}` | administrative close; action `close_admin` |
| POST `/tickets/{id}/collaborators` | `{user_id}` | |
| DELETE `/tickets/{id}/collaborators/{user_id}` | none | |
| POST `/attachments` | multipart `file` | 201 `Attachment`; stays unlinked until a ticket is created with its id |
| GET `/attachments/{id}/download` | none | authorized bytes; the frontend fetches with the bearer token and saves a blob |

**Notifications, audit, dashboards**

| Method and path | Response | Notes |
|---|---|---|
| GET `/notifications?unread=true&page=` | `Paged<Notification>` | own only |
| GET `/notifications/unread-count` | `{count}` | used by the bell |
| POST `/notifications/{id}/read`, POST `/notifications/read-all` | 204 | |
| GET `/audit?q=&actor_id=&action=&ticket_id=&from=&to=&page=` | `Paged<AuditEntry>` | flag `audit.view_all`; Admin does not see security-limited entries |
| GET `/dashboard/employee`, `/dashboard/spoke`, `/dashboard/admin` | the dashboard types | Spoke dashboard scoped to the caller's departments |
| GET `/reports/kpis?from=&to=&department_id=&priority[]=` | `KpiReport` | `reports.view_org`: organisation-wide; Spoke without it: own departments only (another `department_id` gives 403 `forbidden`); otherwise 403. Every count uses the visibility clause |
| GET `/reports/export?type=&format=&…filters` | file (200) | `type=tickets` takes the `TicketListQuery` parameters; `type=kpis` takes the `/reports/kpis` parameters. Access as `/reports/kpis` (Spoke: own departments; employee: 403). `Content-Type`: `text/csv; charset=utf-8`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, or `application/pdf`; `Content-Disposition: attachment; filename="ibotix-<type>-<YYYYMMDD-HHMM IST>.<format>"`. The frontend downloads with the bearer token as a blob (same flow as attachment download) |

**Saved views**

| Method and path | Request | Response | Notes |
|---|---|---|---|
| GET `/saved-views` | none | `SavedView[]` | built-in views first, then the caller's own views by name |
| POST `/saved-views` | `{name, query}` | 201 `SavedView` | `query` validated exactly like `GET /tickets` |
| PATCH `/saved-views/{id}` | `{name?, query?}` | `SavedView` | own views only (others' or unknown: 404); built-in: 403 |
| DELETE `/saved-views/{id}` | none | 204 | soft delete; same 404/403 rules |

**Business calendar**

| Method and path | Request | Response | Notes |
|---|---|---|---|
| GET `/calendar` | none | `BusinessCalendar` | Admin and Super Admin |
| PUT `/calendar` | `{working_days, work_start, work_end}` | `BusinessCalendar` | flag `policy.manage` |
| POST `/calendar/holidays` | `{date, name}` | 201 `BusinessCalendar` | `policy.manage`; an active holiday on that date gives 409 `conflict` |
| DELETE `/calendar/holidays/{date}` | none | 204 | `policy.manage`; soft delete; unknown date 404 |

**Notification preferences**

| Method and path | Request | Response | Notes |
|---|---|---|---|
| GET `/me/notification-preferences` | none | `NotificationPreferences` | any active user, own only |
| PUT `/me/notification-preferences` | `{non_critical_email, digest_hour}` | `NotificationPreferences` | `critical_email` is not accepted |

### A.5 Permission flags (`Me.permissions`)

| Flag | Granted to |
|---|---|
| `tickets.create` | every active user |
| `tickets.view_all` | Admin, Super Admin |
| `tickets.view_department` | Spoke |
| `tickets.acknowledge`, `tickets.assign`, `tickets.transfer`, `tickets.change_priority`, `tickets.revise_eta`, `tickets.hold`, `tickets.resolve`, `tickets.close_admin`, `tickets.reopen`, `tickets.internal_notes` | Spoke, Admin, Super Admin (the assignee's rights on one ticket come from `allowed_actions`) |
| `users.approve_employee` | Admin, Super Admin |
| `users.approve_admin`, `users.approve_super_admin` | Super Admin |
| `users.manage_roles` (map Spokes, deactivate employees) | Super Admin; Admin only while `admins_can_manage_departments` is true |
| `admins.manage` | Super Admin |
| `superadmins.protect` | Super Admin |
| `confidential.manage` | Super Admin |
| `departments.manage` | Super Admin; Admin only while `admins_can_manage_departments` is true |
| `policy.manage` | Super Admin |
| `audit.view_all` | Admin, Super Admin |
| `reports.view_org` | Admin, Super Admin: organisation-wide `GET /reports/kpis` |

---

### A.6 Validation rules (frontend Zod and backend must match exactly)

| Field or form | Rule |
|---|---|
| Email | valid, trimmed, lowercased; signup and reapply: domain in `allowed_email_domains` |
| Name | 2 to 100 characters |
| Password | at least 12 and at most 128 characters, with a lowercase letter, an uppercase letter, and a digit |
| Requested role | `employee`, `admin`, or `super_admin` only (Spoke is never a signup role) |
| Department id (code) | `^[A-Z]{2,6}$`, immutable; department and category names 2 to 80 characters |
| KPI filters | `from`, `to` ISO 8601 with offset; `from < to` (else 422 `fields.to`); range at most 366 days (else 422 `fields.from`); defaults `to` = now, `from` = `to` minus 30 days; `department_id` an existing department (else 422 `fields.department_id`); `priority[]` values from `Priority` (`priority` also accepted) |
| Export | `type` in `ExportType`, `format` in `ExportFormat` (else 422 with that field); the filters follow the rules of the endpoint they mirror; more than 50,000 rows (CSV, XLSX) or 2,000 rows (PDF) gives 422 `fields.format` |
| Saved view | `name` trimmed, 2 to 80 characters, unique per user ignoring case (409 `conflict`); `query` keys only from `TicketListQuery`, values valid for `GET /tickets` (422 `fields.query.<key>`); at most 50 views per user (409 `conflict`) |
| `awaiting_before` | ISO 8601 with offset |
| Calendar | `working_days` 1 to 7 distinct integers in 1..7; `work_start`, `work_end` `HH:MM` with `work_start < work_end` (else 422 `fields.work_end`) |
| Holiday | `date` `YYYY-MM-DD`; `name` 2 to 80 characters, trimmed |
| Notification preferences | `non_critical_email` in `NonCriticalEmail`; `digest_hour` integer 0 to 23 |
| Ticket title / description | 1 to 120 / 1 to 5000 characters, trimmed |
| Ticket category | required when the department has active categories |
| Attachments | type, size, and count from `PublicConfig.attachment_limits` |
| Acknowledge | a future `eta`, or both `no_eta_reason` (at least 5 characters) and a future `next_checkpoint_at`; never neither |
| ETA revision | `eta` in the future and different from the current ETA; `reason` at least 5 |
| Ask requester | `message` at least 5 characters (posted as a public comment) |
| Hold | `reason` at least 5; `review_date` in the future |
| Resolve | `summary` 10 to 2000 characters |
| Reopen, cancel, close, transfer, priority change, reject, deactivate, protected action | `reason` 5 to 1000 characters |
| Assign reason | optional for Spokes; required (at least 5) for Admin and Super Admin |
| Transfer | target different from current; category required when the target has active categories |
| Rating / feedback comment | integer 1 to 5 (optional) / up to 1000 characters |
| Comment body | 1 to 5000 characters, trimmed |
| Policy | hours fields 1 to 168; `eta_warning_hours` 1 to 48; `auto_close_business_days` 1 to 30 or null; `reopen_window_days` 1 to 90; `max_reopens` 0 to 10; every `warning_hours` value below `initial_response_hours`; every `l3_hours` value above `initial_response_hours`; `update_warning_hours` below `update_cadence_hours`; `sla_mode` `calendar` or `business` |
| Lookup `q` | at least 2 characters |

"Future" means later than the current time when submitted.

---

## APPENDIX R: Business rules (authoritative)

### R.1 Decision register

| ID | Rule |
|---|---|
| D-1 | There is no Resolver role; "assignee" is per ticket. A Spoke assigns only to active members of the ticket's department (home department or an active Spoke mapping). Admin or Super Admin may assign to any active user and must give a reason. |
| D-2 | A Spoke is a mapping of a user to one or more departments. Every new ticket notifies all active Spokes of its department; the first to acknowledge becomes the accountable owner. |
| D-3 | Each department has one escalation contact. L2 goes to the department's Spokes, the contact, and all Admins; if the contact is missing or inactive, Admins, then Super Admins. L3 goes to all Super Admins and Admins. No backup contact, no per-category override, no separate executive group. |
| D-4 | The progress-update timer starts when the ticket is acknowledged. |
| D-5 | All priorities share the 24h initial-response SLA. Priority changes sorting and escalation speed (earlier warning and L3 for higher priorities). A Critical ticket notifies the department escalation contact at creation. |
| D-6 | A confidential ticket is visible to Super Admins, to users holding an active grant for the ticket's category (any employee, Spoke, or Admin), and to the ticket's requester, assignee, and collaborators. Only a Super Admin grants or revokes. Spoke or Admin status never grants access. |
| D-7 | Admins manage departments, categories, Spokes, and escalation contacts while `admins_can_manage_departments` is true. Only Super Admins manage Admin accounts, the SLA policy, and confidential grants. |
| D-8 | Signup with company email, department, and requested role (`employee`, `admin`, `super_admin`); pending until approved. Employee requests: any Admin or Super Admin. Admin requests: a Super Admin. Super Admin requests: a different Super Admin. Nobody approves their own. The approver may change department and role (authority needed for the higher of requested and approved role). Spoke is assigned afterward. Rejected users see the reason and may reapply. |
| D-9 | Deactivating or demoting a Super Admin is a protected action needing a second, different Super Admin (not the requester, not the target); the system always keeps at least two active Super Admins; the request expires after 72 hours; Super Admins are never deleted. Demotion sets the role to `admin`. Admin or Super Admin may deactivate employees and Spokes; only a Super Admin may deactivate an Admin. Deactivated users cannot log in; open tickets they own or are assigned alert Admins. |
| D-10 | Release 1 is the full BRD section 20 control loop with SLA, escalation, audit, and confidential controls. KPI dashboards, exports, saved views, business-hours mode, and notification preferences are Release 2. |
| D-11 | At closure the requester may give a 1 to 5 rating and an optional comment. |
| D-12 | Ticket number `IBX-{department code at creation}-{IST year}-{6-digit sequence per code per year}`; never changes on transfer. Codes are 2 to 6 uppercase letters. |
| D-13 | Defaults: requester may cancel only while `new`; reopen within 7 days of `resolved_at`, at most 3 times, never after `cancelled`; a transfer gives the receiving department a fresh initial-response cycle; a reopen starts a new initial-response cycle; Awaiting Requester and On Hold pause the progress-update and ETA timers; resolved tickets auto-close after 3 business days (Monday to Friday, IST). |
| D-14 | MFA is optional and off by default; `MFA_REQUIRED_ROLES` turns enforcement on. |
| D-15 | Categories are one level in Release 1. |

### R.2 Ticket visibility (one clause everywhere)

A ticket is visible to an actor when any of these holds:
1. The actor is a Super Admin.
2. The actor is the requester, the assignee, or a collaborator.
3. The ticket is **not** confidential and the actor is an active Spoke of the ticket's department.
4. The ticket is **not** confidential and the actor is an Admin.
5. The ticket **is** confidential and the actor holds an active grant on the ticket's category.
6. The ticket is **not** confidential and the actor is the active escalation contact of the ticket's department (read access only; the contact gains no ticket actions from this rule). This makes the R.6 L2 and `CREATION_CONTACT` notifications reach the contact.

The same clause governs lists, counts, search, dashboards, audit entries tied to tickets, notification recipients, and attachment downloads. A ticket that is not visible behaves exactly like one that does not exist (404).

### R.3 Allowed actions

**Actor classes** (an actor may belong to several; the union applies): `REQUESTER`, `COLLABORATOR`, `ASSIGNEE`, `TEAM` (the ticket is visible to the actor and the actor is an active Spoke of its department, or its owner, or an Admin, or a Super Admin). A requester acting as `TEAM` cannot `acknowledge` or `resolve` their own ticket.

| Action | Statuses | Actor classes |
|---|---|---|
| `acknowledge` | `new` | TEAM |
| `assign` | `acknowledged`, `assigned`, `in_progress`, `awaiting_requester`, `on_hold`, `reopened` | TEAM |
| `change_priority` | active statuses (`new`, `acknowledged`, `assigned`, `in_progress`, `awaiting_requester`, `on_hold`, `reopened`) | TEAM |
| `revise_eta` | `acknowledged`, `assigned`, `in_progress`, `awaiting_requester`, `on_hold`, `reopened` | TEAM, ASSIGNEE |
| `start_work` | `acknowledged`, `assigned`, `reopened` | TEAM, ASSIGNEE |
| `ask_requester` | `in_progress` | TEAM, ASSIGNEE |
| `hold` | `in_progress` | TEAM, ASSIGNEE |
| `resume` | `awaiting_requester`, `on_hold` | TEAM, ASSIGNEE |
| `resolve` | `in_progress` | TEAM, ASSIGNEE (never the requester) |
| `confirm_closure` | `resolved` | REQUESTER |
| `reopen` | `resolved`, `closed`, within the window and count | REQUESTER, TEAM |
| `cancel` | active statuses (TEAM); `new` only (REQUESTER) | TEAM, REQUESTER |
| `close_admin` | `resolved` | TEAM |
| `transfer` | active statuses | TEAM |
| `comment` | every status except `closed`, `cancelled` | REQUESTER, COLLABORATOR, TEAM, ASSIGNEE |
| `internal_note` | same statuses | TEAM, ASSIGNEE |
| `manage_collaborators` | same statuses | TEAM |

### R.4 Lifecycle and timer effects

Allowed transitions: `new` to `acknowledged`; `acknowledged` to `assigned` or `in_progress`; `assigned` to `in_progress`; `in_progress` to `awaiting_requester`, `on_hold`, or `resolved`; `awaiting_requester` and `on_hold` back to `in_progress`; `resolved` to `closed` or `reopened`; `closed` to `reopened`; `reopened` to `assigned` or `in_progress`; any active status to `cancelled`; any active status to `new` by transfer.

| Event | Timer effect |
|---|---|
| `TicketCreated` | Start `initial_response` (cycle 1) from `sla_started_at`: `warning_at` = start + scaled `warning_hours[priority]`; `due_at` = start + scaled `initial_response_hours`; `l3_at` = start + scaled `l3_hours[priority]`. |
| `TicketAcknowledged` | `initial_response` met (level 0). Start `progress_update` from now (`warning_at` + `update_warning_hours`, `due_at` + `update_cadence_hours`, `l3_at` + twice the cadence). Start `eta` (due = `eta`, or `next_checkpoint_at` when there is no ETA; `warning_at` = due minus `eta_warning_hours`; `l3_at` = due + `update_cadence_hours`). |
| `TeamUpdateRecorded` | Restart `progress_update` (cycle plus one, level 0) unless paused, terminal, or not started. Meaningful updates: a public comment or internal note by the team or assignee, a status change, a hold, an ETA revision, a resolution. Assignment, priority change, collaborator changes, and system reminders do not count. |
| To `awaiting_requester` | Pause `progress_update` and `eta`; start `requester_reminder` (due = now + `requester_reminder_hours`). |
| To `on_hold` | Pause `progress_update` and `eta`; start `hold_review` (due = `hold_review_date`). |
| Resume to `in_progress` from those | Stop `requester_reminder` or `hold_review`; restart `progress_update`; resume `eta` (add the paused time to `paused_seconds`; the ETA date does not move). |
| Start work or assign from `reopened` | Mark the new-cycle `initial_response` met; start `progress_update`. |
| `TicketEtaChanged` | Restart `eta` with the new due. |
| `TicketPriorityChanged` | Recompute `warning_at` and `l3_at` of an unmet `initial_response` from the new priority; `due_at` is unchanged. |
| `TicketResolved` | Mark `eta` met (late if after its due); stop `progress_update`, `requester_reminder`, `hold_review`; if `auto_close_business_days` is not null start `auto_close` (due = `add_business_days(now, n)`, not scaled). |
| `TicketClosed`, `TicketCancelled` | Stop every timer. |
| `TicketReopened` | Stop `auto_close`; restart `initial_response` (new cycle, `sla_started_at` now, thresholds from the current priority); stop `eta`; `progress_update` stays stopped until work starts. |
| `TicketTransferred` | Restart `initial_response` (`sla_started_at` now); stop `progress_update`, `eta`, `requester_reminder`, `hold_review`. |
| Any other change | `reconcile(ticket)` makes the timer set match the status. |

### R.5 Policy defaults, levels, and the `SlaState` object

**Default policy (version 1):** `initial_response_hours` 24; `warning_hours` low 18, medium 18, high 18, critical 12; `l3_hours` low 48, medium 48, high 36, critical 30; `update_warning_hours` 20; `update_cadence_hours` 24; `eta_warning_hours` 2; `escalation_repeat_hours` 24; `requester_reminder_hours` 48; `auto_close_business_days` 3; `reopen_window_days` 7; `max_reopens` 3; `sla_mode` `calendar`; `admins_can_manage_departments` true. Every duration in hours is multiplied by `SLA_TIME_SCALE` (1.0 in production). In `business` mode every scaled hour duration counts only working time of the business calendar (R.14); the mode is resolved per ticket as category override, else department override, else the policy `sla_mode`.

**Level of an active timer** (not met, stopped, or paused) at time `now`: 3 when `now >= l3_at`; 2 when `now >= due_at`; 1 when `now >= warning_at`; otherwise 0. A paused timer has level 0. `tickets.escalation_level` is the maximum over active timers; `update_overdue` is true when `progress_update` is at level 1 or higher.

**The `SlaState` object:**
- `closed`: `{level:0, kind:null, paused:false, stopped:true, due_at:null, label:'Closed'}`; `cancelled`: the same with label `'Cancelled'`.
- `resolved`: `{level:0, kind:null, paused:true, stopped:false, due_at: the auto_close due or null, label:'Awaiting closure'}`.
- `on_hold` or `awaiting_requester`: `{level:0, kind:null, paused:true, stopped:false, due_at:null, label:'Timer paused'}`.
- Otherwise the governing timer is the active timer with the highest level among `initial_response` (while unmet), `progress_update`, and `eta`; ties go to the earliest `due_at`. `kind` is its kind, `due_at` is its `due_at`, `level` its level, `paused` false, `stopped` false, and the label is: `initial_response` 'Initial response due' (level below 2) or 'Initial response overdue'; `progress_update` 'Next update due' or 'Update overdue'; `eta` 'ETA due' or 'ETA overdue'.

### R.6 Escalation

**Steps** (each recorded once per ticket, timer kind, cycle, and step key):

| Timer | Step key | When | Level |
|---|---|---|---|
| `initial_response` | `CREATION_CONTACT` | at creation, or when the priority becomes critical while unmet | 1, to the escalation contact only |
| | `L1` | `warning_at` | 1 |
| | `L2` | `due_at` | 2 |
| | `L3` | `l3_at` | 3 |
| | `L3_REPEAT_n` (n at least 1) | `l3_at + n * escalation_repeat_hours` | 3 |
| `progress_update` | `L1`, `L2`, `L3` | `warning_at`, `due_at`, `l3_at` | 1, 2, 3 |
| | `L3_REPEAT_n` | `l3_at + n * escalation_repeat_hours` | 3 |
| `eta` | `L1`, `L2`, `L3` | `warning_at`, `due_at`, `l3_at` | 1, 2, 3 |
| | `L3_REPEAT_n` | `l3_at + n * escalation_repeat_hours` | 3 |

**Recipients:** L1: owner, assignee, and the department's active Spokes. L2: the L1 set, the department's escalation contact (if active), and all active Admins; if the contact is missing or inactive the Admins serve as fallback, and if there are no active Admins, all active Super Admins. L3: all active Super Admins and all active Admins. `CREATION_CONTACT`: the escalation contact (same fallback chain).

**Confidential tickets:** every recipient list is filtered by the visibility clause; if the filtered L2 or L3 list has no one with management authority, add all active Super Admins.

**Recovery:** acknowledgement ends `initial_response` escalation; a meaningful update restarts `progress_update`; an ETA revision or resolution ends ETA escalation. After downtime, emit each distinct level once and, for repeated steps, only the latest index.

### R.7 Domain events and notifications

Events (frozen dataclasses with ids, actor id, timestamp, and the fields named): `SignupVerified`, `SignupDecided`, `UserDeactivated(open_ticket_count)`, `ProtectedActionRequested`, `ProtectedActionDecided`, `ConfidentialGrantChanged`, `TicketCreated`, `TicketAcknowledged`, `TicketAssigned`, `TicketStatusChanged(from, to)`, `TicketEtaChanged(old, new, is_extension, reason)`, `TicketPriorityChanged(old, new)`, `TicketResolved`, `TicketClosed(reason)`, `TicketReopened`, `TicketCancelled`, `TicketTransferred(from_department, to_department)`, `TeamUpdateRecorded`, `CommentAdded(internal)`, `CollaboratorChanged(added)`, `SlaWarningRaised(timer_kind, level)`, `EscalationRaised(timer_kind, level, step_key)`.

Recipients (always minus the acting user and always filtered by visibility for ticket events). P = portal, E = email, C = critical. `kind` is the notification kind.

| Event | `kind` | Recipients and channels |
|---|---|---|
| `SignupVerified` | `signup_pending` | Employee request: all active Admins and Super Admins; Admin request: all active Super Admins; Super Admin request: all active Super Admins except the applicant. P+E |
| `UserDeactivated` (count above zero) | `user_deactivated_open_tickets` | all active Admins and Super Admins. P+E+C |
| `ProtectedActionRequested` | `protected_action_requested` | active Super Admins except requester and target. P+E+C |
| `ProtectedActionDecided` | `protected_action_decided` | requester and all active Super Admins. P+E+C |
| `ConfidentialGrantChanged` | `confidential_grant_changed` | the affected user. P+E |
| `TicketCreated` | `ticket_created` | requester (P+E); all active Spokes of the department (P+E) |
| `TicketAcknowledged` | `ticket_acknowledged` | requester (P+E, includes owner and ETA) |
| `TicketAssigned` | `ticket_assigned` | assignee (P+E); requester (P); Spokes (P) |
| `TicketStatusChanged` | `status_changed` | requester (P+E); owner and assignee (P) |
| `CommentAdded` public by team | `comment_added` | requester and collaborators (P+E) |
| `CommentAdded` public by requester or collaborator | `comment_added` | owner, assignee, Spokes (P+E) |
| `CommentAdded` internal | `internal_note` | owner, assignee, Spokes (P only) |
| `TicketEtaChanged` | `eta_changed` | requester (P+E with old, new, and "extension" wording when `is_extension`) |
| `TicketPriorityChanged` | `priority_changed` | owner and assignee (P) |
| `TicketTransferred` | `transferred` | requester (P+E); Spokes of both departments (P+E) |
| `TicketResolved` | `resolved` | requester (P+E with the summary and confirm or reopen link) |
| `TicketClosed` | `closed` | requester (P+E); owner and assignee (P) |
| `TicketReopened` | `reopened` | owner, assignee, Spokes (P+E); requester (P) |
| `TicketCancelled` | `cancelled` | requester (P+E); owner and assignee (P) |
| `CollaboratorChanged` (added) | `collaborator_added` | the collaborator (P+E) |
| `SlaWarningRaised` | `sla_warning` | L1 recipients (P+E, not critical) |
| `EscalationRaised` (level 2 and above, or `CREATION_CONTACT`) | `escalation` | recipients of the level (P+E+C) |
| `requester_reminder` timer due (scheduler, no event) | `requester_reminder` | requester (P+E), deduplicated per timer cycle; text "Ticket {id} is waiting for your reply" |
| `hold_review` timer due (scheduler, no event) | `hold_review_due` | owner (P+E), deduplicated per timer cycle; text "Hold review due on {id}" |
| Protected action expired (scheduler, no event) | `protected_action_decided` | requester (P+E+C); text "The request to {verb} Super Admin {target} expired" |

**Texts:** portal `text` is a short sentence, for example "New ticket IBX-IT-2026-001234 in IT: {title}", "Your ticket {id} was acknowledged. ETA {eta}", "L2 initial response breach on {id}". For a confidential ticket the portal text is "Update on {id}" and emails contain only the number, department, status, priority, and the link `FRONTEND_BASE_URL/tickets/{id}`.

### R.8 Timeline and audit visibility

**`ticket_events`:** every ticket change writes one row. `kind` is `comment`, `internal_note`, or `audit`. `detail` is the staff text; `public_detail` is the requester text (null means requesters see `detail`). `is_public` decides whether requesters and collaborators see the event.

| Action | Public | Notes |
|---|---|---|
| `acknowledged`, `assigned`, `status_changed`, `hold`, `resolved`, `closed`, `reopened`, `cancelled`, public comments | yes | |
| `eta_revised`, `transferred` | yes | `public_detail` omits the reason; staff `detail` includes it |
| internal notes, `priority_changed`, `escalation`, `collaborator_added`, `collaborator_removed` | no | staff only |

**`audit_log` and `/audit`:** entries are written for signup, verification, approval and rejection, login success and failure, lockout, role and department changes, Spoke mappings, grants, protected actions, deactivation and activation, every ticket state change, ETA revisions, priority changes, transfers, policy and configuration changes (old and new values), escalation steps, and attachment downloads of confidential tickets. `is_security_limited` is set for role, grant, signup-decision, and protected-action entries. Super Admin sees everything; Admin everything except security-limited entries, with ticket entries filtered by visibility; other roles use the ticket timeline.

### R.9 List semantics

- **Scopes:** `mine` (requester or collaborator), `assigned` (assignee is the caller), `queue` (the caller's active Spoke departments, optionally narrowed by `department_id`; 403 for a non-Spoke), `all` (flag `tickets.view_all`). The visibility clause always applies.
- **Filters:** `status` repeatable (`open` means every status except `resolved`, `closed`, `cancelled`), `priority` repeatable, `department_id`, `category_id`, `requester_id`, `assignee_id`, `sla_state` (`unacknowledged`: status `new`; `warning`: `escalation_level = 1`; `breached`: `escalation_level >= 2`; `stale`: `update_overdue`), `escalation_level` (0 to 3), `confidential`, `overdue_eta` (an active ticket whose `eta` is in the past), `created_from`, `created_to`, `q` (case-insensitive contains on ticket number or title).
- **Default sort `urgency`:** active tickets first; then `escalation_level` descending; then priority rank descending; then `sla_started_at` ascending; then ticket number. Other `sort` values: `created_at`, `-created_at`, `priority`, `-priority`, `status`, `title`.

### R.10 Dashboards and attachments

**"Active" statuses** are every status except `resolved`, `closed`, `cancelled`. All counts use the visibility clause.
- **`EmployeeDashboard`:** `open` (requested by the caller, active); `awaiting_my_response` (requested, `awaiting_requester`); `resolved_to_confirm` (requested, `resolved`); `closed` (requested, `closed`); `assigned_to_me` (assignee is the caller, active); `recent_updates` (the latest 10 public events on visible tickets the caller requested or is assigned to); `attention` (up to 6 such tickets with `escalation_level > 0` or `awaiting_requester`, in urgency order).
- **`SpokeDashboard`** (caller's departments): `new_unacknowledged` (status `new`); `approaching_sla` (level 1, active); `breached` (level 2 or higher); `stale_or_eta_overdue` (`update_overdue` or an overdue ETA); `awaiting_requester`; `on_hold`; `resolved_pending_closure` (`resolved`); `attention` (up to 6 by urgency).
- **`AdminDashboard`:** `open_count` (active); `breached_count` (level 2 or higher); `l3_count` (level 3); `stale_count` (`update_overdue`); `pending_approvals` (pending verified signup requests with `can_approve` true for the caller); `attention` (up to 6 by urgency); the four Release 2 fields follow R.12.
- **Attachments:** default allowed types `application/pdf`, `image/png`, `image/jpeg`, `text/plain`, `text/csv`, and the Word and Excel OOXML types; at most 10 MB and 5 files per ticket. Content sniff: PDF starts `%PDF-`, PNG `89 50 4E 47`, JPEG `FF D8 FF`, OOXML `PK 03 04`, text and CSV must be UTF-8 without NUL bytes; the declared type must agree.

### R.11 Permission flags

Computed per request exactly as Appendix A.5 from the actor and the current policy: Spoke flags apply to any user with an active mapping; Admin-or-Super-Admin flags by `global_role`; `users.manage_roles` and `departments.manage` for an Admin require `admins_can_manage_departments`; Super Admin always has them.

### R.12 KPI definitions

**Scope.** The ticket set S is every ticket matching `visible_ticket_clause(actor)`, narrowed to the caller's Spoke departments when the caller lacks `reports.view_org`, then by `department_id` and `priority` (current values). "Active" is as in R.10. The window is `[from, to)`. "First X event" is the earliest `ticket_events` row with `action = X` for the ticket.

| KPI | Definition |
|---|---|
| `sla_compliance` | Over tickets in S with `created_at` in the window: `missed` = tickets with an `escalation_events` row for `initial_response` at level 2 or higher (any cycle); `met` = the rest with `acknowledged_at` not null; tickets neither met nor missed are not counted. `pct` = met / (met + missed) × 100 |
| `initial_response` | Tickets in S whose first `acknowledged` event is in the window: count, mean and median of (that event's `at` − `created_at`) in seconds |
| `initial_response_trend` | The same grouped by the IST date of the first `acknowledged` event; days with no data have `count` 0 and `avg_seconds` null |
| `resolution_turnaround` | Tickets in S whose first `resolved` event is in the window: count, mean and median of (event `at` − `created_at`) |
| `reopen` | `resolved` = tickets in S with a `resolved` event in the window; `reopened` = those of them with a `reopened` event in the window; `rate_pct` = reopened / resolved × 100 |
| `escalations` | `escalation_events` rows in the window on tickets in S, counted by level (L3 includes `L3_REPEAT_n`); `CREATION_CONTACT` is not counted |
| `eta_breach_count` | `escalation_events` rows with `timer_kind = eta` and `step_key = L2` in the window on tickets in S |
| `stale_count` | Active tickets in S with `update_overdue` |
| `overdue_eta_count` | Active tickets in S with `eta < now`, excluding `on_hold` and `awaiting_requester` |
| `unacknowledged_over_24h` | Tickets in S with status `new` and `sla_started_at <= now − 24 hours` (not scaled) |
| `persistent_l3_count` | Active tickets in S at `escalation_level` 3 with an `L3_REPEAT_n` step in the current cycle of the timer at level 3 |
| `aging` | Active tickets in S by whole days since `created_at`: 0–2, 3–7, 8–14, 15–30, 31+ |
| `departments` | One row per active department in scope (zeros included), sorted by name: `active` = active tickets; `by_priority` = active tickets by priority; `on_track` / `warning` / `breached` = active tickets at `escalation_level` 0 / 1 / 2 or higher; `sla_met_pct` = `sla_compliance.pct` for that department |
| `workload` | Active tickets in S grouped by `assignee_id` (and separately by `owner_id`); `breached` = those at level 2 or higher; sorted by `active` descending, then name; `null` user for unassigned/unowned is listed last |
| `top_categories` | Tickets in S with `created_at` in the window grouped by category (null = "Uncategorised"), top 10 by count, then name |

**Dashboards (replaces the Release 2 sentence in R.10).** `AdminDashboard.sla_met_pct`, `avg_initial_response_seconds` (the mean) and `reopen_rate_pct` use the R.12 definitions over the last 30 days with no department or priority filter; `by_department` is R.12 `departments` reduced to `DepartmentHealth`. `SpokeDashboard` gets the same four fields scoped to the caller's departments. `EmployeeDashboard.assigned_warning` = assigned to the caller, active, level 1; `assigned_breached` = assigned to the caller, active, level 2 or higher.

**Performance.** Each aggregate must finish under 500 ms at 50,000 tickets (perf seed). Add indexes only where `EXPLAIN` shows a sequential scan on a large table.

### R.13 Exports and saved views

- **Scope.** An export contains exactly what the matching read endpoint would show the caller: `type=tickets` = the `GET /tickets` result (visibility clause, scope, filters, sort) narrowed to the caller's Spoke departments when the caller lacks `reports.view_org`; `type=kpis` = the `KpiReport` for the same parameters. Employees cannot export.
- **Header block** (first lines of a CSV; top of the first XLSX sheet; title block of the PDF): `Report` (Tickets or KPIs), `Generated by` (name and email), `Generated at` (IST), `Filters` (every applied parameter as `key=value`, defaults included), `Rows`.
- **Ticket columns:** ticket number, title, department, category, status, priority, confidential, requester, owner, assignee, created at, acknowledged at, ETA, SLA label, escalation level, update overdue, resolved at, closed at, reopen count. Names, not ids; empty cell for none.
- **KPI layout:** CSV one section per KPI separated by a blank line; XLSX one sheet per section (Summary, Trend, Aging, Departments, Workload, Top categories); PDF the same sections as tables.
- **Audit:** every successful export writes `report_exported` (decision 8). Refused exports (403, 422) write nothing.
- **Saved views:** owned by one user, never visible to others; applying a view is the frontend calling `GET /tickets` with its `query`, so visibility always applies at read time. Built-in views are computed per request (R.13 table in A.3).
- **List filters:** `unassigned=true` means `assignee_id IS NULL`; `awaiting_before=T` means `status = awaiting_requester AND awaiting_since <= T`.

### R.14 Business calendar and notification preferences

- **Calendar:** one organisation calendar; timezone fixed `Asia/Kolkata`; defaults working days Monday to Friday, hours 09:00 to 18:00, no holidays. Holidays are soft-deleted (`removed_at`). Super Admin (`policy.manage`) edits; Admin and Super Admin read.
- **Basis overrides:** `Department.sla_mode` and `Category.sla_mode` override only the basis; every hour threshold stays global.
- **Working time** is the calendar's working days and hours in IST, minus active holidays. `calculate_due(start, hours, mode, scale, calendar)`: `calendar` mode adds wall-clock time; `business` mode moves `start` to the next working minute and then adds `hours × scale` of working time, crossing nights, non-working days and holidays.
- **Timers:** `warning_at`, `due_at` and `l3_at` of `initial_response` and `progress_update`, the `eta` timer's `l3_at` (due + cadence), `requester_reminder` and the repeat steps (`l3_at + n × escalation_repeat_hours`) all use `calculate_due` with the ticket's mode. `eta` `due_at` is the ETA itself; its `warning_at` is wall-clock `due − eta_warning_hours`. `hold_review` is the chosen date.
- **`add_business_days(start, n)`** counts working days of the calendar (holidays excluded) in IST, in both modes.
- **Effect of changes:** a calendar, holiday or basis change applies when a timer next starts or restarts; running timers keep their times.
- **Notification emails:** a notification with `critical: true` always enqueues its email immediately. Otherwise the recipient's `non_critical_email` decides: `immediate` enqueues now, `daily_digest` queues it for the digest, `off` sends no email. Portal notifications are created in every case.
- **Digest:** a worker job runs each tick; for each user with `daily_digest` whose `digest_hour` has passed today (IST) and who has queued items and no digest yet for today, it sends one `notification_digest` email listing every queued item (oldest first, at most 50, then "and N more") and marks them sent. Items whose ticket the user can no longer see are dropped. Confidential tickets use the masked text of R.7. One digest per user per IST day (unique key).
- **Defaults and exemptions:** `non_critical_email` `immediate`, `digest_hour` 9. Account emails (verification, password reset, signup decisions) are not notifications and ignore preferences.
- **Audit:** `business_calendar_updated`, `holiday_added`, `holiday_removed`, `sla_basis_changed` (old and new value). Preference changes are not audited.

---

## APPENDIX S: Seed data for the backend (same as the frontend mock)

Domain `ibotix.ai`, password `Ibotix2026Demo`. Departments (code and name): `IT` IT & Infrastructure, `ENG` Engineering / Product, `HR` HR / People Operations, `ADM` Administration & Facilities, `FIN` Finance & Accounts, `SEC` Information Security / Compliance, `SAL` Sales / Business Development, `OPS` Project Delivery / Operations, `LEG` Legal / Contracts. Every department has one escalation contact (a head of department, an Employee) except `SAL` (tests the fallback), and every department has at least one active Spoke except `ADM` (tests "No active Spoke yet").

| Person | Role | Notes |
|---|---|---|
| Asha Verma | Employee, ENG | |
| Meera Iyer | Employee, FIN | |
| Dev Patel | Employee, IT | assignee in several tickets (no resolver role) |
| Rohan Mehta, Isha Gupta | Spokes of IT (Rohan also ENG) | |
| Neha Kapoor | Spoke of HR | granted the HR confidential category |
| Sanjay Rao | Spoke of FIN | |
| Tara Joshi | Employee in ADM | not a Spoke (ADM has none) |
| Vikram Singh | Spoke of SEC | granted the Security confidential category |
| Aarav Khanna | Spoke of LEG | **not** granted (tests denial) |
| Priya Nair | Admin | not granted any confidential category |
| Karan Shah | Super Admin | |
| Mira Kulkarni | Super Admin | second Super Admin (needed for protected actions) |
| Heads of IT, HR, FIN, SEC, LEG, OPS | Employees | escalation contacts |
| Three pending signups | Employee, Admin, Super Admin requests | |
| One rejected, one deactivated, one unverified | | for the status pages |

Confidential categories: HR "Employee Records", LEG "Contract Review", SEC "Security Incident". Each department has 2 to 4 categories.
Tickets (about 16): on track, approaching SLA, breached L2, persistent L3, acknowledged but stale, ETA overdue, awaiting requester, on hold, resolved awaiting confirmation, closed with a rating, reopened, cancelled, a confidential HR ticket, a Critical security ticket, a transferred ticket (original code IT, now HR), a ticket assigned to Dev Patel.
