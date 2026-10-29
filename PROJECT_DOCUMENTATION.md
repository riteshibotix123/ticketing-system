# Ibotix Ticketing Portal Backend: Project Knowledge Document

This document explains the backend in this folder to a developer who has never seen it. Every statement cites the file (and, where useful, the function) it comes from, so you can check it yourself. Anything I could not confirm from the code is marked **Unclear - needs confirmation**.

> **Status of this document: complete.** It was written in parts because the project is large (about 12,000 lines of application code, 120 test files and a 1,450-line build guide).
>
> | Part | Sections | State |
> |---|---|---|
> | 1 | Table of contents, 1 Overview, 2 Architecture, 3 Folders, 4.1 to 4.4 (root files, infrastructure, `app/core`, entry points, integrations) | **Done** |
> | 2 | 4.5 Models and migrations, 6 Data layer (tables, ER diagram, who reads and writes) | **Done** |
> | 3 | 4.6 to 4.8 Policy, queries, schemas, with their code walkthroughs | **Done** |
> | 4 | 4.9 Services (tickets, workflow, SLA, notifications, reports, exports, calendar, preferences), 5 Code walkthrough | **Done** |
> | 5 | 4.10 Routers, 7 Endpoint reference, 8 End-to-end flows | **Done** |
> | 6 | 4.11 to 4.14 Worker jobs, seed and CLI, templates, tests; 9 to 15 (security, dependencies, jobs, testing, quality review, glossary, quick reference) | **Done** |

---

## Table of contents

1. [Project Overview](#1-project-overview)
   1. [What the project does](#11-what-the-project-does)
   2. [Who uses it: roles](#12-who-uses-it-roles)
   3. [Tech stack](#13-tech-stack)
   4. [Install and run](#14-install-and-run)
   5. [Environment variables](#15-environment-variables)
2. [Architecture](#2-architecture)
   1. [The four processes](#21-the-four-processes)
   2. [Layers inside the API](#22-layers-inside-the-api)
   3. [Component and data-flow diagram](#23-component-and-data-flow-diagram)
   4. [Design patterns and key decisions](#24-design-patterns-and-key-decisions)
3. [Folder-by-Folder Breakdown](#3-folder-by-folder-breakdown)
4. [File-by-File Breakdown](#4-file-by-file-breakdown)
   1. [Root files](#41-root-files)
   2. [Infrastructure: Docker, Alembic setup, contract, docs, scripts](#42-infrastructure-docker-alembic-setup-contract-docs-scripts)
   3. [app/core](#43-appcore)
   4. [Entry points and integrations](#44-entry-points-and-integrations)
   5. [Models and migrations](#45-models-and-migrations)
   6. [Policy](#46-policy-apppolicy)
   7. [Queries](#47-queries-appqueries)
   8. [Schemas](#48-schemas-appschemas)
   9. [Services](#49-services-appservices)
      1. [Accounts and identity](#491-accounts-and-identity)
      2. [Organisation, policy and platform](#492-organisation-policy-and-platform-services)
      3. [Tickets](#493-tickets-creation-reading-attachments-comments-collaborators)
      4. [Ticket workflow](#494-ticket-workflow-appservicesworkflow)
      5. [SLA engine](#495-sla-engine-appservicessla)
      6. [Event handlers and notifications](#496-domain-event-handlers-and-notifications)
      7. [Reporting](#497-reporting-dashboards-kpis-exports-saved-views)
   10. [Routers](#410-routers-appapirouters)
   11. [Worker jobs](#411-worker-jobs-appworkerjobs)
   12. [Seed data and CLI](#412-seed-data-and-cli)
   13. [Email templates](#413-email-templates-apptemplatesemail)
   14. [Tests](#414-tests-tests)
5. [Code-Section Walkthrough](#5-code-section-walkthrough)
6. [Data Layer](#6-data-layer)
   1. [Conventions shared by every table](#61-conventions-shared-by-every-table)
   2. [Tables](#62-tables)
   3. [ER diagram](#63-er-diagram)
   4. [Who reads and writes each table](#64-who-reads-and-writes-each-table)
   5. [Database-level protections](#65-database-level-protections)
7. [API / Endpoint Reference](#7-api--endpoint-reference)
   1. [Rules that apply to every route](#71-rules-that-apply-to-every-route)
   2. [Health](#72-health-no-prefix-public)
   3. [Public configuration and authentication](#73-public-configuration-and-authentication)
   4. [Users, signup approvals, Admins, protected actions](#74-users-signup-approvals-admins-protected-actions)
   5. [Organisation](#75-organisation-departments-categories-grants-policy-calendar)
   6. [Tickets](#76-tickets-list-create-read-timeline-comments-collaborators-attachments)
   7. [Ticket workflow](#77-ticket-workflow)
   8. [Notifications and preferences](#78-notifications-and-preferences)
   9. [Audit, dashboards, reports, exports, saved views](#79-audit-dashboards-reports-exports-saved-views)
8. [End-to-End Flows](#8-end-to-end-flows)
   1. [Signup, verification, approval, first login](#81-self-signup-email-verification-approval-first-login)
   2. [Login with MFA, refresh, logout](#82-login-with-mfa-token-refresh-and-logout)
   3. [Raising a ticket with an attachment](#83-raising-a-ticket-with-an-attachment)
   4. [Working a ticket to closure](#84-working-a-ticket-to-closure)
   5. [SLA escalation by the worker](#85-sla-escalation-by-the-worker)
   6. [Exporting a report](#86-exporting-a-ticket-report)
   7. [Daily email digest](#87-daily-email-digest)
   8. [Removing a Super Admin](#88-removing-a-super-admin-protected-action)
9. [Configuration, Authentication and Security](#9-configuration-authentication-and-security)
   1. [Configuration](#91-configuration)
   2. [Authentication](#92-authentication-who-are-you)
   3. [Authorization](#93-authorization-what-may-you-do)
   4. [Confidentiality guarantees](#94-confidentiality-guarantees)
   5. [Web and transport security](#95-web-and-transport-security)
10. [Third-Party Integrations and Dependencies](#10-third-party-integrations-and-dependencies)
11. [Background Jobs, Scheduled Tasks, Signals, Hooks](#11-background-jobs-scheduled-tasks-signals-hooks)
12. [Testing](#12-testing)
13. [Code Quality Review](#13-code-quality-review)
   1. [All findings](#130-all-findings)
   2. [Prioritised summary and status](#131-prioritised-summary-and-status)
   3. [What is done well](#132-what-is-done-well)
14. [Glossary](#14-glossary)
15. [Quick-Reference Tables](#15-quick-reference-tables)

---

## 1. Project Overview

### 1.1 What the project does

This is the server side of an **internal helpdesk** ("ticketing portal") for a company called Ibotix. Employees use it to ask other departments for help. Each request is a **ticket**: "my laptop screen flickers" goes to the IT department, "please correct my payslip" goes to HR.

The backend:

- stores users, departments, categories and tickets in PostgreSQL;
- decides who may see and do what with each ticket (`app/policy/`);
- runs each ticket through a fixed lifecycle: new, acknowledged, assigned, in progress, awaiting the requester, on hold, resolved, closed, reopened, cancelled (`app/core/enums.py`, `TicketStatus`);
- measures **service-level agreements (SLAs)**: how fast a department first responds, how often it posts updates, whether it meets its promised date. When a deadline is missed the ticket **escalates** to more senior people (`app/services/sla/`);
- notifies people in the portal and by email (`app/services/notifications.py`, `app/worker/jobs/send_outbox.py`);
- keeps an immutable audit trail of every significant action (`app/models/audit.py`);
- supports **confidential tickets** (for example HR investigations) that only specific people may see;
- in Release 2: KPI reports, CSV/XLSX/PDF exports, saved list views, a business-hours calendar for SLAs, and per-user email preferences with a daily digest.

The problem it solves: requests sent by chat or email get lost and nobody is accountable. Here every request has an owner, a deadline, an escalation path and a history.

The authoritative specification is `Backend_Build_Guide_v2.md` in this folder: Appendix A is the API contract, Appendix R the business rules. The code was built part by part from that guide (parts B01 to B26 for Release 1; R2-A, R2-B, R2-C1 and R2-C2 for Release 2), as recorded in `CLAUDE.md`.

There is no frontend in this folder. A separate frontend (React, judging by the Vite port `5173` in `.env.example`, **Unclear - needs confirmation**) calls this API. `docs/FRONTEND-INTEGRATION.md` explains how to connect it.

### 1.2 Who uses it: roles

Roles are defined in `app/core/enums.py` (`Role`) and interpreted by `app/policy/__init__.py` (`Actor`).

| Role | How someone gets it | What it means |
|---|---|---|
| `employee` | Everyone. `Actor.roles` always includes it. | Raise tickets, follow their own tickets, comment, confirm closure, reopen. |
| `spoke` | Not stored as a role. A user is a Spoke when they have at least one active row in `spoke_assignments` (`Actor.is_spoke` checks `spoke_department_ids`). | Works a department's queue: acknowledges, assigns, updates and resolves that department's tickets. |
| `admin` | `users.global_role = 'admin'` | Organisation-wide oversight: sees all non-confidential tickets, manages departments (if the policy flag allows), approves employees. |
| `super_admin` | `users.global_role = 'super_admin'` | Everything an Admin can do, plus confidential tickets, policy changes and administrator management. Removing or demoting a Super Admin needs a second Super Admin's approval ("protected action"). |

A user has exactly one `global_role` (`employee`, `admin` or `super_admin`) and may additionally be a Spoke of one or more departments. `Actor.has_role` (lines 30-35) shows the rule: `employee` is always true, `spoke` means "has Spoke departments", and the other two compare against `global_role`.

### 1.3 Tech stack

All versions are pinned in `pyproject.toml`.

| Area | Technology | Where to look |
|---|---|---|
| Language | Python 3.12 (exactly; `requires-python = ">=3.12,<3.13"`, `.python-version`) | `pyproject.toml` |
| Web framework | FastAPI 0.162 on Uvicorn 0.54 | `app/main.py` |
| Validation / settings | Pydantic 2.14, pydantic-settings 2.16 | `app/schemas/`, `app/core/config.py` |
| Database | PostgreSQL 16 (Docker image `postgres:16`) with the `pg_trgm` extension | `docker-compose.yml`, `alembic/versions/b02_extensions.py` |
| ORM | SQLAlchemy 2.0, **synchronous** sessions | `app/core/db.py`, `app/models/` |
| DB driver | psycopg 3 (binary) | `DATABASE_URL` uses `postgresql+psycopg://` |
| Migrations | Alembic 1.20 | `alembic/` |
| Password hashing | argon2-cffi (Argon2id) | `app/core/security.py` |
| Tokens | PyJWT (HS256) | `app/core/security.py` |
| MFA | pyotp (TOTP), cryptography (Fernet encryption of secrets) | `app/services/mfa.py` |
| Uploads | python-multipart | `app/api/routers/attachments.py` |
| Email addresses | email-validator | `app/schemas/` (Part 3) |
| Email templates | Jinja2 | `app/services/email_templates.py`, `app/templates/email/` |
| Excel / PDF export | openpyxl, reportlab | `app/services/exports/writers.py` |
| Local mail catcher | Mailpit (Docker) | `docker-compose.yml` |
| Tests | pytest, pytest-cov, httpx (FastAPI `TestClient`) | `tests/` |
| Lint / format / types | ruff, mypy (strict, with the Pydantic plugin) | `pyproject.toml` `[tool.ruff]`, `[tool.mypy]` |

What is deliberately **not** used (rule in `CLAUDE.md`): no async database access, no Redis, no Celery. Background work runs in a simple polling worker process (`app/worker/main.py`) that stores its state in PostgreSQL.

External services: an **SMTP server** for email (Mailpit locally; the company relay in production). There are no other external APIs. File storage is the local disk (`app/integrations/storage/local.py`), and virus scanning is a placeholder that marks every file clean (`app/integrations/scanner/noop.py`).

### 1.4 Install and run

These steps come from `README.md` and `CLAUDE.md`. Commands are for Git Bash on Windows; on Linux or macOS use `.venv/bin/activate`.

1. **Python environment**
   ```bash
   python -m venv .venv
   source .venv/Scripts/activate
   pip install -e ".[dev]"
   ```
   `CLAUDE.md` notes that this developer's `.venv` has no `pip`; there, packages are installed with `uv pip install --python .venv/Scripts/python.exe ...`.
2. **Configuration:** `cp .env.example .env`, then edit (see 1.5).
3. **Database and mail:** `docker compose up -d db mailpit`. This starts PostgreSQL on host port **5433** (5432 inside the container; `CLAUDE.md` says a local Windows PostgreSQL owns 5432) and Mailpit (SMTP on 1025, web UI on http://localhost:8025). `docker/initdb/01-create-test-db.sql` creates the second database `ibotix_test` for the tests.
4. **Schema:** `alembic upgrade head`.
5. **Demo data (optional):** `python -m app.cli seed` (refused when `ENV=prod`; Part 6).
6. **API:** `uvicorn app.main:app --reload`. Then:
   - `GET /health/live`, `GET /health/ready`, `GET /health/worker`
   - the business API under `/api/v1/...`
   - OpenAPI at `/openapi.json`, interactive docs at `/docs` (disabled when `ENV=prod`, `app/main.py` line 57).
7. **Worker:** `python -m app.worker` in a second terminal. Without it no emails are sent, SLAs never escalate and nothing auto-closes.
8. **Quality gate** (`README.md`, `CLAUDE.md`): `ruff check . && ruff format --check . && mypy app && mypy tests scripts alembic/env.py alembic/versions && pytest -q && alembic upgrade head && alembic check && python scripts/check_contract.py --full`.

The whole stack can also run in Docker with `docker compose -f docker-compose.full.yml up -d --build` (section 4.2).

### 1.5 Environment variables

All settings are fields of `Settings` in `app/core/config.py`. pydantic-settings reads them from the process environment or from a `.env` file in the working directory (`model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)`, line 29). The variable name is the field name in upper case. `get_settings()` (line 105) caches one instance for the whole process.

| Variable | Default (`config.py`) | What it does | Where it is used |
|---|---|---|---|
| `ENV` | `dev` | `dev`, `test` or `prod`. `test` switches the database to `TEST_DATABASE_URL`, email to an in-memory sender and turns off JSON logging. `prod` hides `/docs`, makes `seed` and `reset-db` refuse, and enforces the three production rules below. | `app/core/db.py` `database_url`; `app/integrations/email/__init__.py` `build_sender`; `app/main.py` `create_app`; `app/cli.py`, `app/seed/run.py` (Part 6) |
| `DATABASE_URL` | `postgresql+psycopg://ibotix:ibotix@localhost:5433/ibotix` | Main database connection | `app/core/db.py`, `alembic/env.py` |
| `TEST_DATABASE_URL` | `...:5433/ibotix_test` | Database used when `ENV=test` | `app/core/db.py`; `tests/conftest.py` (Part 6) |
| `JWT_SECRET` | `dev-insecure-jwt-secret` | Signing key for access tokens and MFA tokens. Must be at least 32 characters in prod (`_enforce_prod_rules`). Stored as `SecretStr`, so it is never printed. | `app/core/security.py`, `app/services/mfa.py` |
| `ACCESS_TOKEN_MINUTES` | 15 (minimum 1) | Access-token lifetime | `create_access_token` |
| `REFRESH_TOKEN_DAYS` | 7 (minimum 1) | Refresh-token lifetime | `app/services/auth.py` (Part 4) |
| `COOKIE_SECURE` | `false` | `Secure` flag on the refresh cookie. Must be `true` in prod. | `app/api/routers/auth.py` (Part 5) |
| `COOKIE_SAMESITE` | `lax` | `lax`, `strict` or `none` for the refresh cookie | `app/api/routers/auth.py` |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated browser origins allowed to call the API. A `*` wildcard is rejected (`_reject_wildcard_origin`). Also used by the origin check on refresh and logout. | `app/main.py`, `app/api/deps.py` `require_allowed_origin` |
| `ALLOWED_EMAIL_DOMAINS` | `ibotix.ai` | Only these email domains may sign up. Lower-cased by `_normalize_domains`. | signup service (Part 4), `PublicConfig` |
| `FRONTEND_BASE_URL` | `http://localhost:5173` | Base of links inside emails (verify, reset, ticket links) | `app/services/email_outbox.py` `enqueue_email` |
| `SMTP_HOST`, `SMTP_PORT` | `localhost`, 1025 | Mail server address | `app/integrations/email/smtp.py` |
| `SMTP_USER`, `SMTP_PASSWORD` | empty | Login, only attempted when `SMTP_USER` is not empty | `SmtpSender.send` |
| `SMTP_FROM` | `helpdesk@ibotix.ai` | `From:` address | `SmtpSender.send` |
| `SMTP_STARTTLS` | `false` | Upgrade the SMTP connection with STARTTLS | `SmtpSender.send` |
| `ATTACHMENT_DIR` | `./var/attachments` | Folder where uploaded files are stored | `app/integrations/storage/__init__.py` `build_storage` |
| `MAX_UPLOAD_BYTES` | 10485760 (10 MiB) | Largest upload. The body-size middleware allows this plus 64 KiB. | `app/main.py` (middleware), attachments service, `PublicConfig` |
| `MAX_FILES_PER_TICKET` | 5 | Attachments allowed per ticket | attachments service, `PublicConfig` |
| `ALLOWED_CONTENT_TYPES` | PDF, PNG, JPEG, text, DOCX, XLSX | Accepted upload MIME types (comma-separated) | attachments service, `PublicConfig` |
| `TIMEZONE` | `Asia/Kolkata` | Read into `Settings.timezone`, but **no code uses it**. IST is hard-coded as a fixed +05:30 offset in `app/core/clock.py` (`IST`). See 13.0. | nowhere |
| `WORKER_TICK_SECONDS` | 15 | Pause between worker cycles; also how long before `/health/worker` reports stale (3 ticks) | `app/worker/main.py` `main`, `app/api/routers/health.py` |
| `SLA_TIME_SCALE` | 1.0 (must be > 0) | Multiplies every SLA duration so that tests and demos can shrink "24 hours" to minutes. Must be exactly 1.0 in prod. | `app/services/sla/` (Part 4), `app/worker/jobs/sla_scan.py` |
| `MFA_REQUIRED_ROLES` | empty | Comma list from `super_admin`, `admin`, `spoke`. Empty means MFA is off (`Settings.mfa_enabled`). | `app/services/mfa.py` |
| `FIELD_ENCRYPTION_KEY` | empty | Fernet key that encrypts stored TOTP secrets. Needed as soon as MFA is used. | `app/services/mfa.py` line 199 |

Two more variables are used outside `Settings`:

- `ADMIN_PASSWORD`: read by `python -m app.cli create-super-admin` (`README.md`; Part 6 covers `app/cli.py`).
- In `docker-compose.full.yml`: `APP_DB_PASSWORD` and `OWNER_DB_PASSWORD` (database role passwords), plus the app variables above with defaults.

**Production rules** (`Settings._enforce_prod_rules`, lines 88-98). When `ENV=prod`, start-up fails unless `JWT_SECRET` is at least 32 characters, `COOKIE_SECURE=true` and `SLA_TIME_SCALE=1.0`.

**Secrets handling.** `JWT_SECRET`, `SMTP_PASSWORD` and `FIELD_ENCRYPTION_KEY` are `SecretStr`, so printing `Settings` shows `**********`. `.env` is excluded from git (`.gitignore`) and from the Docker image (`.dockerignore`). The image has no secrets; production passes them as environment variables (`docs/OPERATIONS.md`).

---

## 2. Architecture

### 2.1 The four processes

| Process | Command | What it does |
|---|---|---|
| **API** | `uvicorn app.main:app` | Serves HTTP. Stateless, so several copies can run side by side (`docs/OPERATIONS.md`). |
| **Worker** | `python -m app.worker` | Loops forever: every `WORKER_TICK_SECONDS` it runs seven jobs in order (`app/worker/jobs/__init__.py` `registered_jobs`): `sla_scan`, `reminders`, `auto_close`, `protected_action_expiry`, `housekeeping`, `digest`, `send_outbox`. |
| **Migrations** | `alembic upgrade head` | One-shot. Creates and upgrades the schema. The API never migrates itself. |
| **CLI** | `python -m app.cli <command>` | One-shot admin tasks: seed demo data, reset the database, create a Super Admin, reset MFA, export OpenAPI. |

API and worker share **one PostgreSQL database**, and the database is also how they talk to each other:

- The API never sends email. It writes rows to `email_outbox`; the worker's `send_outbox` job sends them.
- The API writes SLA timer rows; the worker's `sla_scan` job reads them and escalates overdue tickets.
- The worker records liveness in `worker_heartbeat`; the API's `GET /health/worker` reads it.

### 2.2 Layers inside the API

A request passes through these layers. The arrows show the allowed direction of calls; the import counts in section 3 confirm it.

1. **Middleware** (`app/main.py` lines 62-73): request id and access log, security headers, CORS, body size limit, gzip.
2. **Routers** (`app/api/routers/*.py`): parse the request with a Pydantic schema, resolve the caller (`CurrentActor` from `app/api/deps.py`) and call **one** service method. `CLAUDE.md` calls these "thin routers".
3. **Services** (`app/services/`): the business logic. They load and change ORM objects, call the policy layer for permission checks, write audit rows, publish domain events and return a response schema. **Services never commit**; the commit happens in the `get_db` dependency after the router returns (`app/core/db.py` `transactional`).
4. **Policy** (`app/policy/`): pure permission and visibility rules. `CLAUDE.md`: "all permission and visibility logic lives in app/policy".
5. **Queries** (`app/queries/`): reusable SQLAlchemy `SELECT` builders for lists, KPIs and audit search.
6. **Models** (`app/models/`): SQLAlchemy table classes.
7. **Event handlers** (`app/services/handlers/`): run synchronously inside the same transaction when a service publishes an event (`app/core/events.py` `EventBus.publish`). They update SLA timers and create notifications.

### 2.3 Component and data-flow diagram

```mermaid
flowchart LR
    Browser["Frontend (browser)"] -->|"HTTPS JSON\nBearer access token\nrefresh cookie"| MW

    subgraph API["API process: uvicorn app.main:app"]
        MW["Middleware\nrequest id, security headers,\nCORS, body limit, gzip"] --> R["Routers\napp/api/routers"]
        R -->|"CurrentActor\n(app/api/deps.py)"| S["Services\napp/services"]
        S --> P["Policy\napp/policy"]
        S --> Q["Queries\napp/queries"]
        S -->|"publish(event)"| BUS["EventBus\napp/core/events.py"]
        BUS --> H["Handlers\nSLA timers, notifications"]
        S --> A["AuditService"]
        H --> OUT["enqueue_email()"]
    end

    subgraph DB["PostgreSQL"]
        T[("tickets, users,\nticket_events, sla_timers,\naudit_log, notifications,\nemail_outbox, ...")]
    end

    S --> T
    Q --> T
    A --> T
    H --> T
    OUT --> T

    subgraph W["Worker process: python -m app.worker"]
        J1["sla_scan"] --> J2["reminders"] --> J3["auto_close"] --> J4["protected_action_expiry"] --> J5["housekeeping"] --> J6["digest"] --> J7["send_outbox"]
    end

    W --> T
    J7 -->|SMTP| MAIL["Mail server\n(Mailpit locally)"]
    S -->|"files"| DISK[("ATTACHMENT_DIR\nlocal disk")]
    J5 -->|"delete files"| DISK
```

### 2.4 Design patterns and key decisions

Each item names the code that shows it.

| Pattern or decision | What it means | Evidence |
|---|---|---|
| **Contract first** | The API shape is fixed in the guide's Appendix A. `contract/routes.txt` lists every route, and `scripts/check_contract.py` fails if the app and that file disagree. | `scripts/check_contract.py`, `contract/routes.txt` (85 routes) |
| **Transaction per request** | `get_db` opens a session, yields it, commits on success and rolls back on any exception. Services only `flush()`. | `app/core/db.py` lines 26-37 |
| **Commit before the response** | `DbSession` is declared with `Depends(get_db, scope="function")`, so FastAPI finishes the dependency (and commits) before sending the response. A client never sees "success" for a change that later fails to commit. | `app/api/deps.py` line 18 |
| **Injected clock** | Code never calls `datetime.now()` directly. It takes a `Clock`; production uses `SystemClock`, tests use `FrozenClock` to move time. | `app/core/clock.py`, `ClockDep` in `app/api/deps.py` |
| **In-process domain events** | Services publish small frozen dataclasses (`TicketCreated`, `TicketResolved`, ...). Handlers subscribed on the global `bus` react inside the same transaction. This keeps SLA and notification code out of the workflow services. | `app/core/events.py`, `app/services/handlers/__init__.py` (Part 4) |
| **Transactional outbox** | Emails are rows in `email_outbox`, committed together with the change that caused them, and sent later by the worker. A rolled-back change never sends an email. | `app/services/email_outbox.py`, `app/worker/jobs/send_outbox.py` |
| **Policy layer** | Who may see or do what is decided in `app/policy/` only. One SQL clause, `visible_ticket_clause(actor)`, is used in every ticket query. | `CLAUDE.md` B11; Part 3 |
| **Same 404 for hidden and missing** | A ticket you may not see answers exactly like a ticket that does not exist, so its existence never leaks. | `CLAUDE.md` hard rules; `TicketReadService.load_visible` (Part 4) |
| **Uniform error envelope** | Every error is `{"error": {"code", "message", "fields"?, "details"?, "request_id"}}` with a fixed code-to-status mapping. Even 405 becomes 404 `not_found`. | `app/core/errors.py` |
| **Immutable history** | `ticket_events` and `audit_log` cannot be updated or deleted: database triggers, plus a production DB role without those rights. | `docs/OPERATIONS.md`; migrations (Part 2) |
| **Database-backed rate limits and locks** | Rate-limit counters, worker heartbeat and job locks live in PostgreSQL (advisory locks, `FOR UPDATE SKIP LOCKED`), so several API or worker processes stay correct. | `docs/SECURITY.md`; Part 4 and 6 |
| **Protocols for integrations** | Email, storage and scanner are `typing.Protocol` interfaces with swappable implementations, chosen by small `build_*` factories. | `app/integrations/*/base.py`, `__init__.py` |
| **Settings frozen and cached** | One immutable `Settings` per process. The app factory can take explicit settings (tests do). | `app/core/config.py`, `create_app(settings)` |

---

## 3. Folder-by-Folder Breakdown

"Depends on" lists the `app.*` packages a folder imports, taken from its `import` lines.

| Folder | Purpose | Why it exists | Depends on |
|---|---|---|---|
| `/` (project root) | Packaging, configuration, guide and docs entry | Tools (pip, ruff, mypy, pytest, alembic, Docker) look for their config here | n/a |
| `.venv/` | Local Python environment | Not in git (`.gitignore`); not described further | n/a |
| `.vscode/` | Editor setting: load `.env` into terminals | Developer convenience | n/a |
| `alembic/` | Alembic migration environment (`env.py`, file template) | Creates and evolves the database schema | `app.models` (for `Base.metadata`), `app.core.config`, `app.core.db` |
| `alembic/versions/` | One file per schema revision: `b02` to `b05` (Release 1), `r2a` to `r2c2` (Release 2) | Ordered, reviewable schema history | `alembic`, `sqlalchemy` only |
| `app/` | The application package | Everything that runs | n/a |
| `app/api/` | HTTP layer: `deps.py` (shared dependencies) | Keeps request concerns out of services | `app.core`, `app.policy`, `app.services.me` |
| `app/api/routers/` | One module per resource; each defines an `APIRouter` | Maps URLs to service calls | `app.api.deps`, `app.schemas`, `app.services`, `app.core` (pagination, enums, errors, db), `app.integrations` (attachments), `app.worker.main` (health) |
| `app/core/` | Framework-level building blocks: settings, database, clock, errors, events, security, pagination, logging, middleware | Shared by every layer | `app.core` itself, plus `app.models.sla` and `app.models.ticket` (only `app/core/events.py`, see 13.0) |
| `app/integrations/` | Adapters to the outside world | Lets tests and dev swap real services for fakes | `app.core.config`, `app.core.enums` |
| `app/integrations/email/` | `EmailSender` protocol, SMTP and in-memory senders | Sending email | `app.core.config` |
| `app/integrations/scanner/` | `Scanner` protocol, a no-op scanner | Virus-scan hook for uploads | `app.core` |
| `app/integrations/storage/` | `Storage` protocol, local-disk storage | Storing attachment files | `app.core.config` |
| `app/models/` | SQLAlchemy ORM models (one module per area) | Defines the database tables | `app.models.base`, `app.core.enums`, `app.core.types` |
| `app/policy/` | Permission, visibility and allowed-action rules | Single place for "may this actor do this?" | `app.core`, `app.models`, `app.services.policy` (see 13.0) |
| `app/queries/` | Reusable `SELECT` builders | Ticket list filters, KPI aggregates, audit search | `app.models`, `app.policy`, `app.schemas`, `app.services.sla` |
| `app/schemas/` | Pydantic request and response models | The JSON shapes of Appendix A | `app.schemas.common`, `app.core`, a few `app.models` enums, `app.services.sla` |
| `app/seed/` | Demo data (`data.py`) and the loader (`run.py`) | Realistic data for development and tests | `app.services`, `app.models`, `app.schemas`, `app.core` |
| `app/services/` | Business logic, one module per area | The heart of the app | everything above |
| `app/services/exports/` | Report export: data tables plus CSV/XLSX/PDF writers | Release 2 exports | `app.services.kpis`, `app.queries`, `app.policy` |
| `app/services/handlers/` | Domain-event handlers (SLA timers, notifications) | Reactions to workflow events | `app.services.sla`, `app.services.notifications`, `app.models` |
| `app/services/sla/` | SLA engine: due times, working time, timers, levels, escalation, scanner | Deadlines and escalation | `app.models`, `app.services.policy`, `app.services.calendar`, `app.services.workflow` |
| `app/services/workflow/` | Ticket actions: acknowledge, assign, status, hold, ETA, priority, resolve, close, reopen, cancel, transfer | One place for lifecycle changes | `app.policy`, `app.services.ticket_reads`, `app.core.events` |
| `app/templates/email/` | Jinja2 email templates (`.txt.j2` and `.html.j2` per kind) | Email bodies | none (loaded from disk by `app/services/email_templates.py`) |
| `app/worker/` | Worker loop (`main.py`), `Job`/`JobContext` types | Background processing | `app.core`, `app.integrations.email`, `app.models.notification` |
| `app/worker/jobs/` | The seven scheduled jobs | One module per job | `app.services`, `app.models`, `app.policy`, `app.integrations.storage` |
| `contract/` | `routes.txt`: every public route, one per line | Contract check and authorization matrix | none |
| `docker/initdb/` | SQL run when the dev Postgres container is first created | Creates the test database | none |
| `docs/` | Operations, backup, security, frontend integration | Human documentation | none |
| `scripts/` | `check_contract.py`, `perf_seed.py`, `backup.sh`, `restore_check.sh` | Tooling outside the app | `app.core` |
| `tests/` | pytest suite: `api/`, `integration/`, `unit/`, `security/`, `scenarios/`, `perf/`, plus `conftest.py` and `factories.py` | Proves the behaviour | the whole `app` package |

---

## 4. File-by-File Breakdown

Format for each file: **path**, purpose, contents, imports and importers, and when it runs.

### 4.1 Root files

#### `pyproject.toml`
- **Purpose:** project metadata, pinned dependencies and every tool's configuration.
- **Contents:**
  - `[project]`: name `ibotix-ticketing-backend`, Python 3.12, 16 runtime dependencies (table in 1.3);
  - `[project.optional-dependencies] dev`: pytest, pytest-cov, httpx, ruff, mypy, type stubs for openpyxl and reportlab;
  - `[tool.setuptools.packages.find]`: only `app*` is packaged, so tests and scripts are not installed;
  - `[tool.ruff]`: line length 100, rule sets E, F, I, UP, B, SIM, ARG, C4, PT;
  - `[tool.mypy]`: `strict = true` with the Pydantic plugin;
  - `[tool.pytest.ini_options]`: `testpaths = ["tests"]`, strict markers and config;
  - `[tool.coverage]`: source `app`, `fail_under = 85`.
- **Used by:** `pip install`, ruff, mypy, pytest, coverage, and the `Dockerfile` (`pip install .`).
- **When:** install and tooling time.

#### `.env.example`
- **Purpose:** template for `.env`, listing every variable with its development value (table in 1.5).
- **Used by:** developers (`cp .env.example .env`).

#### `.env`
- **Purpose:** the developer's real local settings. Ignored by git, so it is not in the repository and not described here.

#### `.gitignore`
- **Purpose:** keeps `.venv/`, `__pycache__/`, compiled files, `.env`, tool caches, coverage output and `var/` (local attachments) out of git.

#### `.dockerignore`
- **Purpose:** keeps the Docker build context small and secret-free. It excludes `.env` files (but keeps `.env.example`), the venv, git data, caches, `var`, `backups`, and also `tests`, `docs`, `docker`, `contract`, the build guide, `CLAUDE.md`, the compose files and the `Dockerfile`. The image therefore contains only `pyproject.toml`, `app/`, `alembic.ini`, `alembic/` and `scripts/` (see `Dockerfile`).

#### `.python-version`
- **Purpose:** `3.12`; tells tools such as pyenv or uv which Python to use.

#### `.vscode/settings.json`
- **Purpose:** `"python.terminal.useEnvFile": true`, so VS Code terminals load `.env`.

#### `alembic.ini`
- **Purpose:** minimal Alembic config.
  - `script_location = %(here)s/alembic`;
  - `prepend_sys_path = .` so `import app` works;
  - `file_template = %%(rev)s`, so a migration file is named after its revision id (for example `r2c1_business_calendar.py`).
- **When:** whenever an `alembic` command runs.

#### `Backend_Build_Guide_v2.md` (1,449 lines)
- **Purpose:** the specification the code was built from:
  - section 3: context pack and allowed packages;
  - section 4: quality gate;
  - sections 5 and 6: part-by-part build instructions;
  - Appendix A: API contract (enums, types, endpoints, permission flags, validation);
  - Appendix R: business rules (R.1 decisions to R.14 business calendar);
  - Appendix S: seed data.
- **Used by:** people and the AI assistant (`CLAUDE.md`). No code reads it.

#### `CLAUDE.md`
- **Purpose:** rules and accumulated conventions for the AI assistant that built the project (how to build a part, hard rules, environment notes, one paragraph of conventions per part B05 to R2-C2).
- **For you:** a compact summary of conventions, for example "services never commit", "routers are thin", and how each test fixture behaves. No code reads it.

#### `README.md`
- **Purpose:** short developer guide: requirements, setup, run, gate, CLI commands, full Docker stack, links to `docs/`.

#### `PROJECT_DOCUMENTATION.md`
- **Purpose:** this document.

### 4.2 Infrastructure: Docker, Alembic setup, contract, docs, scripts

#### `docker-compose.yml`
- **Purpose:** the **development** services.
  - `db`: `postgres:16`, user, password and database all `ibotix`, host port `5433`, a named volume, and the init script folder mounted read-only;
  - `mailpit`: SMTP on 1025, web UI on 8025.
- **When:** `docker compose up -d db mailpit`. The tests need `db` running.

#### `docker/initdb/01-create-test-db.sql`
- **Purpose:** one line, `CREATE DATABASE ibotix_test OWNER ibotix;`. Postgres runs it automatically, only when the data volume is first created.

#### `Dockerfile`
- **Purpose:** the production image for API, worker and migrations.
- **Steps:**
  1. Start from `python:3.12-slim`, with byte-code writing off, unbuffered output and pip cache off.
  2. Create a non-root user `ibotix` (uid and gid 10001).
  3. Copy `pyproject.toml` and `app/`, then `pip install .`.
  4. Copy `alembic.ini`, `alembic/` and `scripts/`.
  5. Create `/app/var/attachments` owned by `ibotix` and switch to that user.
  6. Expose port 8000.
  7. Healthcheck: a Python one-liner fetches `/health/live`.
  8. Default command: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-access-log`. The Uvicorn access log is off because the app writes its own (`app/core/request_context.py`).
- **When:** `docker build`, and `docker-compose.full.yml`.

#### `docker-compose.full.yml`
- **Purpose:** the whole system in Docker (project name `ibotix-full`). A shared environment block `x-app-env` sets defaults for every app variable.
- **Services:**

  | Service | Role |
  |---|---|
  | `db` | `postgres:16`, not published to the host |
  | `mailpit` | web UI on host port **8026** |
  | `migrate` | builds the image and runs `alembic upgrade head` as the owner role `ibotix` |
  | `db-roles` | after `migrate`, runs psql to create the login role `ibotix_app` and grant it SELECT, INSERT, UPDATE and DELETE on all tables, then revokes UPDATE, DELETE and TRUNCATE on `audit_log` and `ticket_events`, and all writes on `alembic_version` |
  | `api` | port 8000, connects as `ibotix_app`, attachments on a named volume |
  | `worker` | `python -m app.worker`; its healthcheck calls `http://api:8000/health/worker` |
- **When:** demos and production-like testing (README "Full stack in Docker").

#### `alembic/env.py`
- **Purpose:** Alembic's runtime entry point.
- **Contents:**
  - `target_metadata = app.models.Base.metadata`: importing `app.models` registers every table, which autogenerate needs;
  - `resolve_url()`: uses `config.attributes["url"]` when a caller passes one (tests do, **Unclear - needs confirmation**, see Part 6 `tests/conftest.py`); otherwise `database_url(get_settings())`;
  - `run_migrations_offline()` and `run_migrations_online()`: standard Alembic, both with `compare_type=True`, so `alembic check` also detects column type changes. Online mode uses a `NullPool` engine.
- **Imports:** `app.models`, `app.core.config.get_settings`, `app.core.db.database_url`.
- **When:** every `alembic` command.

#### `alembic/script.py.mako`
- **Purpose:** template for new migration files. It produces typed module variables (`revision: str`, `down_revision: str | None`, ...) so migrations pass mypy strict.

#### `alembic/versions/*.py`
- **Purpose:** the eight schema revisions, applied in this order:

  | File | Lines | Creates |
  |---|---|---|
  | `b02_extensions.py` | 16 | `CREATE EXTENSION IF NOT EXISTS pg_trgm` (trigram text search) |
  | `b03_identity_org_policy.py` | 649 | users, organisation and policy tables |
  | `b04_tickets_sla_notifications.py` | 563 | tickets, SLA, notification tables |
  | `b05_audit_log.py` | 99 | the audit log |
  | `r2a_kpi_indexes.py` | 31 | KPI indexes |
  | `r2b_saved_views.py` | 45 | saved views |
  | `r2c1_business_calendar.py` | 135 | business calendar and SLA basis |
  | `r2c2_notification_preferences.py` | 99 | notification preferences and digests |

  Each one is described table by table in **Part 2**.

#### `contract/routes.txt`
- **Purpose:** the API contract as a plain list, one `METHOD /api/v1/path` per line (85 lines, starting with `GET /api/v1/public/config`).
- **Used by:**
  - `scripts/check_contract.py`, the gate;
  - `tests/security/test_authorization_matrix.py`, which fails if a listed route has no permission expectation.

#### `docs/OPERATIONS.md`
- **Purpose:** how to deploy and run in production:
  - the three processes;
  - the production value of every variable;
  - the database role SQL (owner vs `ibotix_app`);
  - first-deployment steps, including creating two Super Admins;
  - monitoring signals (health endpoints, outbox failures and backlog queries, log fields);
  - the upgrade and rollback procedure.

#### `docs/BACKUP-RESTORE.md`
- **Purpose:** backup policy (RPO and RTO left as `<TBD by infrastructure>`, daily 02:00 IST, 14-day retention), usage of the two scripts, and an 8-step disaster-recovery procedure. It stresses that the database and the attachment folder must be backed up together.

#### `docs/SECURITY.md`
- **Purpose:** the security controls, each paired with the test that proves it:
  - authentication (Argon2id, JWT, refresh rotation with reuse detection, lockout, MFA, no account enumeration);
  - the rate-limit table;
  - the authorization matrix;
  - the confidential-ticket leak tests;
  - HTTP hardening and upload checks;
  - performance results (the `jit=off` and `mine`-scope fixes).
- Section 9 (Part 6) checks these claims against the code.

#### `docs/FRONTEND-INTEGRATION.md`
- **Purpose:** how to run the frontend against this backend:
  - starting everything, the seeded accounts and generating API types;
  - CORS and cookies, E2E runs and conformance checks;
  - sections 7 to 10 on the Release 2 features (KPIs, exports and saved views, business calendar, notification preferences).

#### `scripts/__init__.py`
- **Purpose:** empty; makes `scripts` a package so that `python -m scripts.perf_seed` works (`CLAUDE.md` B24).

#### `scripts/check_contract.py`
- **Purpose:** compares the app's routes with `contract/routes.txt`.
- **Functions:**
  - `load_contract(path)` → `(routes, problems)`: reads non-blank lines. A line is "malformed" if the method is not get/post/put/patch/delete or the path does not start with `/api/v1/`; a repeated line is a "duplicate".
  - `load_app_routes(app)`: reads `app.openapi()["paths"]` and keeps `/api/v1` operations.
  - `build_app()`: imports `app.main` and calls `create_app()`.
  - `main()`: prints the differences.
- **Pass/fail:** it fails if there are problems, extra routes (in the app but not the contract) or, with `--full`, missing routes (in the contract but not the app). Exit code 1 on failure.
- **When:** the quality gate, by hand.

#### `scripts/perf_seed.py`
- **Purpose:** loads 50,000 tickets and 200,000 events for load testing. Described in Part 6 together with the performance tests.

#### `scripts/backup.sh`
- **Purpose:** writes `BACKUP_DIR/<UTC timestamp>/database.dump` (`pg_dump --format=custom --no-owner`), `attachments.tar.gz` and `SHA256SUMS`. It exits with an error if the dump is empty, then deletes backup folders older than `RETENTION_DAYS` (default 14).
- **Configuration:** `PG_DUMP` and `ATTACHMENT_TAR` can be overridden so that the commands run inside Docker containers.

#### `scripts/restore_check.sh`
- **Purpose:** restore drill.
- **Steps:**
  1. Pick the newest backup folder, or the one given as the first argument.
  2. Verify the checksums.
  3. Count the files in the archive.
  4. Restore into a temporary database `restore_check_<timestamp>`.
  5. Query the Alembic revision and the row counts of `users`, `tickets`, `ticket_events`, `audit_log` and linked `attachments`.
  6. Fail if the revision is missing, there are no users, or the archive holds fewer files than there are linked attachments.
- A `trap ... EXIT` drops the temporary database even on failure.

### 4.3 app/core

The core package has no business logic. Every other layer uses it.

#### `app/__init__.py`, `app/core/__init__.py`, `app/api/__init__.py`, `app/api/routers/__init__.py`, `app/seed/__init__.py`, `app/services/sla/__init__.py`, `app/services/workflow/__init__.py`
- **Purpose:** empty files that mark Python packages. They contain no code.

#### `app/core/config.py`
- **Purpose:** typed application settings.
- **Contents:**
  - `MIN_PROD_JWT_SECRET_LENGTH = 32`;
  - type aliases: `MfaRole` (a Literal of three roles), `CommaList` and `MfaRoleList` (lists marked `NoDecode`, so pydantic-settings does not try to parse JSON);
  - `Environment` (StrEnum: `dev`, `test`, `prod`);
  - `_split_comma_list` and the `Settings` class (fields in 1.5);
  - `get_settings()`.
- **Walkthrough:**
  - `_parse_comma_list` (lines 65-74, `mode="before"`): turns `"a, b,,c"` into `["a", "b", "c"]` for the four list fields, before type validation.
  - `_reject_wildcard_origin` (76-81): raises if `*` is among the CORS origins, because credentials (the refresh cookie) must never be allowed for every site.
  - `_normalize_domains` (83-86): lower-cases the allowed email domains.
  - `_enforce_prod_rules` (88-98, runs after all fields): only when `env` is `prod`. Checks the JWT secret length, `cookie_secure` and `sla_time_scale == 1.0`.
  - `mfa_enabled` property (100-102): `True` when `mfa_required_roles` is not empty.
  - `get_settings()` (105-107): `@lru_cache(maxsize=1)`, so `.env` is read once per process.
- **Imported by:** almost every layer (db, security, deps, integrations, services, worker, CLI, alembic env, scripts).
- **When:** first call to `get_settings()`, which is at import of `app.core.db` (module-level engine creation).

#### `app/core/db.py`
- **Purpose:** database engine, session factory and the per-request transaction.
- **Contents:**
  - `database_url(settings)`: test URL when `ENV=test`, otherwise `DATABASE_URL`;
  - `CONNECTION_OPTIONS = "-c jit=off"`;
  - `create_db_engine(url)`: `create_engine(url, pool_pre_ping=True, connect_args={"options": "-c jit=off"})`;
  - module-level `engine` and `SessionLocal` (`autoflush=False`, `expire_on_commit=False`);
  - `transactional(session)` and `get_db()`.
- **Walkthrough:**
  - `transactional` (26-32) is a generator: yield the session; after the caller is done, `commit()`; on any exception (including `BaseException`), `rollback()` and re-raise.
  - `get_db` (35-37) opens a `SessionLocal()` in a `with` block and delegates to `transactional`. FastAPI treats it as a dependency with clean-up, so the commit runs when the request handler finishes.
  - `pool_pre_ping=True` tests each pooled connection before use, so a database restart does not break the first request.
  - `jit=off` disables PostgreSQL's JIT compiler for these connections. `docs/SECURITY.md` explains that JIT added 400 to 600 ms to every ticket-list query.
- **Side effect at import:** the engine is created when the module is first imported (it connects lazily, on first use).
- **Imported by:** `app/api/deps.py`, `app/api/routers/health.py`, `app/main.py` (to dispose the engine at shutdown), `app/worker/main.py`, `alembic/env.py`, `app/cli.py`, `scripts/perf_seed.py`, tests.

#### `app/core/clock.py`
- **Purpose:** testable time, plus Indian Standard Time.
- **Contents:**
  - `IST = timezone(timedelta(hours=5, minutes=30), "IST")`: a fixed offset, because Windows has no tz database and India has no daylight saving (`CLAUDE.md`);
  - `_require_aware(value)`: raises `ValueError` for naive datetimes;
  - `Clock` (Protocol with `now()`), `SystemClock` (returns `datetime.now(UTC)`) and `FrozenClock` (`now`, `set`, `advance`; it always stores UTC);
  - `get_clock()`: returns the shared `SystemClock`; tests override this FastAPI dependency;
  - `to_ist(value)`: converts an aware datetime to IST.
- **Imported by:** about 36 service modules, the worker, deps and tests.
- **When:** request time and job time.

#### `app/core/enums.py`
- **Purpose:** the shared enum values of Appendix A.2. All are `StrEnum`, so they serialize as lowercase strings.
- **Contents:**

  | Enum | Values |
  |---|---|
  | `Role` | `super_admin`, `admin`, `spoke`, `employee` |
  | `AccountState` | `pending_verification`, `pending_approval`, `active`, `rejected`, `deactivated` |
  | `Priority` | `low`, `medium`, `high`, `critical` |
  | `TicketStatus` | the ten statuses listed in 1.1 |
  | `TicketAction` | 17 actions: `acknowledge` to `manage_collaborators` |
  | `SlaKind` | `initial_response`, `progress_update`, `eta` |
  | `ScanStatus` | `pending`, `clean`, `infected` |
  | `ProtectedActionKind` | `deactivate_super_admin`, `demote_super_admin` |
  | `ProtectedActionStatus` | `pending`, `approved`, `rejected`, `expired` |
  | `SignupStatus` | `pending`, `approved`, `rejected` |

  - `PRIORITY_RANK`: a read-only mapping from low=1 to critical=4, used for "urgency" sorting in `app/queries/tickets.py`.
- **Imported by:** models, schemas, policy, services, queries.

#### `app/core/errors.py`
- **Purpose:** the error model and the global exception handlers.
- **Contents:**
  - `ErrorCode` (15 codes);
  - `ERROR_STATUS`: code to HTTP status, for example `invalid_transition` → 409, `token_expired` → 410;
  - `DEFAULT_MESSAGES`;
  - `HTTP_STATUS_CODES`: maps framework HTTP errors to codes; **405 maps to `not_found`**;
  - `ApiError`;
  - helper constructors: `unauthenticated`, `invalid_credentials`, `forbidden`, `account_state`, `not_found`, `conflict`, `invalid_transition`, `protected_action_blocked`, `token_expired`, `file_too_large`, `unsupported_file_type`, `validation_error`, `too_many_attempts`, `rate_limited`, `server_error`;
  - `error_response`, `_validation_fields`, the four `_handle_*` handlers and `install_error_handlers`.
- **Walkthrough:**
  - `ApiError.__init__` (87-100): stores the code, the message (or the default), the status (or the mapped status), optional `fields` (field name to message, for 422) and optional `details` (extra JSON, for example `retry_after_seconds`).
  - `account_state(state, rejection_reason)` (115-119): a 403 with `details.state`, and the rejection reason when there is one. Used when an inactive user tries to log in.
  - `error_response(request, error)` (175-187): builds `{"error": {...}}`, always including `request_id` (from `request.state` or the context variable), and repeats the id in the `X-Request-ID` header.
  - `_validation_fields(exc)` (190-196): turns Pydantic errors into a flat `{field: message}`, using only the **last** element of each error location. So `body.name` becomes `name`, and the first error per field wins. Side effect: an error inside a list item is keyed by its index (for example `"0"`). `CLAUDE.md` and the R2-C1 build both note this.
  - The handlers (199-224) turn `ApiError`, `RequestValidationError` (422) and Starlette `HTTPException` (mapped by status) into the envelope. Any other exception is logged on the `app.errors` logger with the stack trace and request id, and returns a generic 500 `server_error`, so internals never reach the client.
- **Imported by:** services, routers, pagination, `security_headers.py`, `app/main.py`.

#### `app/core/events.py`
- **Purpose:** domain events and a tiny synchronous publish/subscribe bus.
- **Events:** all are `@dataclass(frozen=True, slots=True, kw_only=True)` and inherit `actor_id` and `occurred_at` from `DomainEvent`.
  - Account events: `SignupVerified`, `SignupDecided`, `UserDeactivated` (with `open_ticket_count`), `ProtectedActionRequested`, `ProtectedActionDecided`, `ConfidentialGrantChanged`.
  - Ticket events inherit `ticket_id` from `TicketDomainEvent`:

    | Event | Extra fields |
    |---|---|
    | `TicketCreated`, `TicketAcknowledged`, `TicketAssigned` | none |
    | `TicketStatusChanged` | `from_status`, `to_status` |
    | `TicketEtaChanged` | `old`, `new`, `is_extension`, `reason` |
    | `TicketPriorityChanged` | `old`, `new` |
    | `TicketResolved`, `TicketReopened`, `TicketCancelled`, `TeamUpdateRecorded` | none |
    | `TicketClosed` | `reason` (a `CloseReason`) |
    | `TicketTransferred` | `from_department`, `to_department` |
    | `CommentAdded` | `ticket_event_id`, `internal` |
    | `CollaboratorChanged` | `user_id`, `added` |
    | `SlaWarningRaised` | `timer_kind`, `level` |
    | `EscalationRaised` | `timer_kind`, `level`, `step_key` |
- **`EventBus`:**
  - `register(event_type, handler)` (154-161): wraps the handler in `dispatch`, which calls it only if the event is an instance of `event_type`, and appends it to a list keyed by type.
  - `publish(session, event)` (163-165): calls every handler registered for **exactly** `type(event)` (not parent classes), in registration order, on a copy of the list. Handlers receive the caller's session, so their writes join the same transaction. An exception in a handler propagates to the publisher and rolls back the whole request.
  - `handler_count` (used by `tests/unit/test_events.py`) and `clear()`.
- **Module-level:** the global `bus`, plus module functions `register` and `publish` that use it.
- **Imports:** `app.models.sla.TimerKind` and `app.models.ticket.CloseReason`, so `core` depends on `models` (13.0).
- **Imported by:** services (about 14 modules), handlers, seed, tests.
- **When:** request time (publish) and app start (`register_all()` in `create_app`).

#### `app/core/ids.py`
- **Purpose:** ticket numbers.
- **Contents:** `DEPARTMENT_CODE_PATTERN = ^[A-Z]{2,6}$`, `TICKET_PREFIX = "IBX"`, `MAX_TICKET_SEQUENCE = 999_999`, and `format_ticket_no(code, year, seq)`.
- `format_ticket_no` validates all three inputs and returns for example `IBX-IT-2026-000042`.
- **Imported by:** `app/services/ticket_numbers.py`, tests (`factories.py`).

#### `app/core/types.py`
- **Purpose:** two recursive type aliases (PEP 695 `type`): `JsonValue` (any JSON value) and `JsonObject` (`dict[str, JsonValue]`).
- **Used by:** JSONB columns, audit values, email contexts, error details.

#### `app/core/logging.py`
- **Purpose:** JSON log lines on stdout.
- **Contents:**
  - `JsonFormatter.format`: writes `timestamp` (UTC ISO), `level`, `logger`, `message`, `request_id`, any of `method`, `path`, `status_code`, `duration_ms`, `user_id` found on the record, and `exception` when there is one;
  - `configure_logging(level)`: replaces the root handlers with one stdout handler and makes Uvicorn's loggers propagate to the root.
- **When:** at app creation outside tests (`create_app`) and at worker start (`app/worker/main.py`).

#### `app/core/pagination.py`
- **Purpose:** page parameters and paged queries.
- **Contents:** `DEFAULT_PAGE = 1`, `DEFAULT_PAGE_SIZE = 25`, `MAX_PAGE_SIZE = 100`, plus:
  - `PageParams`: a FastAPI dependency class reading `page` (≥1) and `page_size` (1 to 100). The extra checks in `__init__` also cover direct construction;
  - `PageResult[T]`;
  - `count_rows`: wraps the statement without its ORDER BY in `SELECT count(*) FROM (subquery)`;
  - `fetch_page`: count, then `LIMIT`/`OFFSET` (two queries);
  - `parse_sort(sort, allowed, default)`: returns the mapped sort expression or raises 422 `fields.sort` listing the allowed keys.
- **Imported by:** routers (`Depends(PageParams)`), `ticket_reads.py`, `notifications.py`, `audit_reads.py`, `users.py`, exports and others.

#### `app/core/request_context.py`
- **Purpose:** per-request id, client IP and user agent, available anywhere; plus the access log.
- **Contents:**
  - `REQUEST_ID_HEADER = "X-Request-ID"`;
  - `REQUEST_ID_PATTERN`: 1 to 128 characters from `[A-Za-z0-9._:-]`;
  - `MAX_USER_AGENT_LENGTH = 512`;
  - `RequestContext` (frozen dataclass) stored in a `ContextVar`, with `get_request_context`, `current_request_id`, `set_request_context` and `reset_request_context`;
  - `resolve_request_id`, `build_context`, `RequestContextMiddleware`, `route_template` and `log_request`.
- **Walkthrough:**
  - `resolve_request_id(value)`: reuses the client's `X-Request-ID` only if it matches the safe pattern; otherwise generates a UUID hex. This prevents log injection.
  - `build_context(scope)`: takes the IP from the ASGI `client` and truncates the user agent to 512 characters.
  - `RequestContextMiddleware.__call__`:
    1. Skip non-HTTP traffic.
    2. Build the context and store the id in `scope["state"]["request_id"]`.
    3. Start a timer.
    4. Wrap `send` to capture the status code and add the `X-Request-ID` header if missing.
    5. Set the context variable and call the app.
    6. In `finally`, always log the request and reset the context variable.
  - `route_template(scope)`: rebuilds the path with path parameters replaced by `{name}`, so logs show `/api/v1/tickets/{id}` and never ids. `"unmatched"` when no route matched.
  - `log_request(...)`: one `app.access` info line with `request_id`, `method`, `path`, `status_code`, `duration_ms` and `user_id` (set by `get_actor` in `request.state.user_id`).
- **Imported by:** `app/core/errors.py`, `app/services/audit.py` (stores the IP and user agent on audit rows, Part 4), `app/main.py`.

#### `app/core/security.py`
- **Purpose:** passwords, access tokens and opaque tokens.
- **Contents:** constants `PASSWORD_MIN_LENGTH = 12`, `PASSWORD_MAX_LENGTH = 128`, `JWT_ALGORITHM = "HS256"`, `REFRESH_TOKEN_BYTES = 32`, `REQUIRED_CLAIMS = ("sub", "iat", "exp", "jti")`; a module-level Argon2 `PasswordHasher`; `InvalidAccessToken`; `IssuedAccessToken(token, expires_in)`; and the functions below.
- **Walkthrough:**
  - `hash_password(password)`: Argon2id with library defaults.
  - `verify_password(hash, password)`: returns `False` instead of raising on mismatch, a bad hash or a verification error.
  - `_dummy_hash()` (cached) and `dummy_verify(password)`: hash a random value once, then verify against it. Login calls this for unknown emails so the response time matches a real check (no timing-based account discovery).
  - `password_policy_error(password)`: returns the first broken rule (length 12 to 128, a lowercase letter, an uppercase letter, a digit) or `None`.
  - `create_access_token(user_id, now, settings)`: claims `sub` (user id), `iat`, `exp = iat + ACCESS_TOKEN_MINUTES*60` and a random `jti`; HS256 with `JWT_SECRET`.
  - `decode_access_token(token, now, settings)`:
    1. Decode with the required claims and the algorithm pinned to HS256 (prevents algorithm-confusion attacks).
    2. Disable PyJWT's own time checks and compare `exp` with the **injected** clock instead, so tests can control time.
    3. Require `exp` to be an int and `sub` a string, then parse `sub` as a UUID.
    4. Any problem raises `InvalidAccessToken`.
  - `new_opaque_token()`: 32 random bytes, URL-safe; used for refresh, verification and reset tokens.
  - `hash_token(raw)`: SHA-256 hex, so the database stores only hashes of opaque tokens.
- **Imported by:** `app/api/deps.py`, `app/services/auth.py`, `signup.py`, `mfa.py`, `policy.py` (password length for `PublicConfig`), `app/cli.py`, seed, tests.

#### `app/core/security_headers.py`
- **Purpose:** two ASGI middlewares.
- **Contents:**
  - `STATIC_HEADERS`: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`;
  - `NO_STORE_PATHS`: every `/api/v1/auth...` path and `/api/v1/attachments/{id}/download`;
  - `MULTIPART_OVERHEAD_BYTES = 64 KiB`;
  - `needs_no_store`, `SecurityHeadersMiddleware`, `BodyTooLarge` and `BodySizeLimitMiddleware`.
- **Walkthrough:**
  - `SecurityHeadersMiddleware`: when the response starts, sets the three static headers, plus `Cache-Control: no-store` on auth and download paths so browsers never cache tokens or private files.
  - `BodySizeLimitMiddleware(limit = MAX_UPLOAD_BYTES + 64 KiB)`:
    1. If a declared `Content-Length` exceeds the limit, reject immediately with 413 `file_too_large`.
    2. Otherwise wrap `receive` to count body bytes as they arrive (this covers chunked uploads with no length). When the count passes the limit before the response has started, raise `BodyTooLarge`, which stops the app reading.
    3. `guarded_send` swallows anything the app tries to send after that and sends the 413 once instead.
    4. The outer `contextlib.suppress(BodyTooLarge)` plus the final check guarantee exactly one 413.
- **Imported by:** `app/main.py`.

### 4.4 Entry points and integrations

#### `app/main.py`
- **Purpose:** builds the FastAPI application. This is the API's entry point.
- **Contents:** `API_PREFIX = "/api/v1"`, `lifespan`, `create_app(settings=None)`, and the module-level `app = create_app()` that Uvicorn loads.
- **Walkthrough of `create_app`** (lines 50-101):
  1. Use the given settings, or `get_settings()`.
  2. Outside tests, switch logging to JSON (`configure_logging`).
  3. Create `FastAPI(title="Ibotix Ticketing API", version="1.1.0")`. `/docs` is off in prod; ReDoc is always off.
  4. Store the settings on `app.state.settings`, where `SettingsDep` reads them.
  5. Add middleware. Starlette runs the **last added first**, so the request order is: `RequestContextMiddleware`, then `SecurityHeadersMiddleware`, then `CORSMiddleware`, then `BodySizeLimitMiddleware`, then `GZipMiddleware` (responses of 1,000 bytes or more), then the app. This is why a 413 still carries the CORS and security headers, as `docs/SECURITY.md` says.
  6. CORS: the listed origins, credentials allowed, methods GET, POST, PUT, PATCH, DELETE and OPTIONS, headers `Authorization`, `Content-Type` and `X-Request-ID`. `X-Request-ID` and `Content-Disposition` are exposed to JavaScript; the latter lets the browser read export filenames.
  7. `install_error_handlers(app)`.
  8. `register_all()`: subscribes every domain-event handler on the global bus (Part 4: `app/services/handlers/__init__.py`).
  9. Mount `health.router` at the root (`/health/...`), and mount 22 business routers under `/api/v1`.
- **`lifespan`:** does nothing at start-up; at shutdown it disposes the engine (closes pooled connections).
- **When:** process start (import). `create_app` is also called by `scripts/check_contract.py` and by tests with test settings.

#### `app/api/deps.py`
- **Purpose:** shared FastAPI dependencies.
- **Contents:**
  - `DbSession = Annotated[Session, Depends(get_db, scope="function")]`;
  - `ClockDep`;
  - `get_app_settings(request)` and `SettingsDep`: use `app.state.settings` when it is a `Settings`, else `get_settings()`;
  - `_bearer_token(request)`: case-insensitive `Bearer ` prefix, returns `None` for a missing or empty token;
  - `get_actor(...)` and `CurrentActor`;
  - `require_allowed_origin(request, settings)`: 403 if an `Origin` header is present and not listed. A missing `Origin` (non-browser clients) is allowed.
- **Walkthrough of `get_actor`** (lines 40-52):
  1. Read the bearer token. If there is none, raise 401 `unauthenticated`.
  2. `decode_access_token` with the injected clock. Any failure gives the same 401.
  3. `MeService(db).load_active_actor(user_id)` reloads the user from the database on every request (Part 4). A missing or non-active user gives 401. So roles are never trusted from the token, and deactivation takes effect immediately.
  4. Store the user id on `request.state.user_id` for the access log.
  5. Return the `Actor`.
- **Imported by:** every router. `require_allowed_origin` is used on `POST /auth/refresh` and `POST /auth/logout` (`app/api/routers/auth.py` lines 113 and 133).
- **When:** request time.

#### `app/policy/__init__.py`
Covered fully in Part 3. In short, it defines:
- `STAFF_ROLES = {admin, super_admin}`;
- the frozen `Actor` dataclass (`id`, `global_role`, `department_id`, `spoke_department_ids`, `name`, `email`) with `is_spoke`, `is_admin_or_super_admin`, `is_super_admin`, `has_role(role)` and `roles` (always `employee`, plus `spoke` if mapped, plus the global staff role).

The `Actor` is the authenticated caller that every service receives.

#### `app/api/routers/health.py`
- **Purpose:** health probes, not under `/api/v1`, with no authentication.
- **Contents:** `STALE_AFTER_TICKS = 3`, `HealthStatus(status: Literal["ok"])`, and three routes:

  | Route | Behaviour |
  |---|---|
  | `GET /health/live` | Always `{"status": "ok"}` |
  | `GET /health/ready` | Runs `SELECT 1`; a database failure becomes the 500 envelope |
  | `GET /health/worker` | Reads the `worker_heartbeat` row named `"worker"`. Returns 503 `{"status": "stale"}` if the row is missing or older than `WORKER_TICK_SECONDS × 3`, otherwise `ok`. |
- **Imports:** `HEARTBEAT_NAME` from `app/models/notification.py` (moved there from the worker so the API no longer imports the worker, 13.0 #5).
- **When:** called by Docker healthchecks and monitoring.

#### `app/worker/__init__.py`
- **Purpose:** two frozen dataclasses shared by every job:
  - `JobContext(clock, settings, sender)`;
  - `Job(name, run)`, where `run(session, context) -> int` returns the number of items processed.

#### `app/worker/__main__.py`
- **Purpose:** makes `python -m app.worker` call `app.worker.main.main()`.

#### `app/worker/main.py`
- **Purpose:** the worker loop.
- **Contents:** the logger `app.worker`, the `Worker` class, `_elapsed_ms`, `install_signal_handlers` and `main`. The heartbeat row name `HEARTBEAT_NAME` lives in `app/models/notification.py`.
- **Walkthrough:**
  - `Worker.__init__`: stores the session factory, the context, the job list and the tick length; creates a `threading.Event` for stopping.
  - `run_forever()`: loops `tick()` then `self._stop.wait(tick_seconds)` until stopped. Waiting on the event means a stop signal interrupts the sleep immediately.
  - `tick()`: runs each job in order, unless stopping, collecting `{job name: count or None}`, then calls `_beat`.
  - `_run_job(job)`: opens a fresh session per job, calls `job.run(session, context)` and logs `"job %s processed %d items in %d ms"`. On any exception it rolls back, logs the stack trace and returns `None`. One failing job never stops the others, and jobs commit their own work (`CLAUDE.md` B07).
  - `_beat(results)`: upserts `worker_heartbeat` (`INSERT ... ON CONFLICT (name) DO UPDATE`) with `last_seen_at` and `details = {"jobs": {...}, "failed": [...]}` in its own session. A heartbeat failure is logged, not raised.
  - `install_signal_handlers(worker)`: SIGTERM and SIGINT call `worker.stop()`, so Docker stop or Ctrl+C finish the current job and exit cleanly.
  - `main()`: configures JSON logging, **registers the domain-event handlers** (`register_all()`, so events published by jobs reach the SLA and notification handlers; this was missing until the fix of 13.0 #37), builds the context (`SystemClock`, settings, `build_sender(settings)`), creates the worker with `SessionLocal` and `registered_jobs()`, installs the signal handlers and runs forever.
- **When:** the worker process (`python -m app.worker`).

#### `app/worker/jobs/__init__.py`
- **Purpose:** `registered_jobs()` returns the seven jobs in their fixed order. `send_outbox` is last so that emails queued by the earlier jobs in the same tick go out at once. Each job is described in Part 6.

#### `app/integrations/email/base.py`
- **Purpose:** `OutgoingEmail(to_address, subject, body_text, body_html)` (frozen dataclass) and the `EmailSender` protocol (`send(message) -> None`).

#### `app/integrations/email/memory.py`
- **Purpose:** `InMemorySender`, which appends messages to a list behind a lock, with `sent` (a copy) and `clear()`. Used when `ENV=test`, so tests can inspect emails without a mail server.

#### `app/integrations/email/smtp.py`
- **Purpose:** `SmtpSender`, which sends real email with the standard library.
- **`send(message)`:**
  1. Build a multipart `EmailMessage` (plain text plus an HTML alternative) with the configured `From`.
  2. Open `smtplib.SMTP(host, port, timeout=30)`.
  3. Optionally run `starttls()`.
  4. Log in only if `SMTP_USER` is set.
  5. `send_message`.
- **Error handling:** exceptions propagate to the caller, `send_outbox` (Part 6), which handles retries.

#### `app/integrations/email/__init__.py`
- **Purpose:** `build_sender(settings)` returns `InMemorySender()` when `ENV=test`, otherwise `SmtpSender(settings)`; it also re-exports the classes.
- **Used by:** `app/worker/main.py`, tests.

#### `app/integrations/scanner/base.py`, `noop.py`, `__init__.py`
- **Purpose:** the virus-scan hook.
  - `Scanner` protocol: `scan(content: bytes) -> ScanStatus`;
  - `NoopScanner.scan`: always returns `ScanStatus.CLEAN`;
  - `build_scanner(_settings)`: always returns `NoopScanner()`.
- No real scanner exists. `docs/SECURITY.md` says to plug one in before handling untrusted files at scale.
- **Used by:** `app/api/routers/attachments.py` → `AttachmentService` (Part 4).

#### `app/integrations/storage/base.py`
- **Purpose:** `StorageError` and the `Storage` protocol: `save(stream, key_hint) -> key`, `open(key) -> BinaryIO`, `delete(key)`.

#### `app/integrations/storage/local.py`
- **Purpose:** `LocalStorage(root)`, files on disk.
- **Contents:** `HINT_PATTERN = ^[a-z0-9_-]{1,32}$`, `KEY_PATTERN = ^[a-z0-9_-]{1,32}/[0-9a-f]{32}$`, `CHUNK_SIZE = 64 KiB`.
- **Walkthrough:**
  - `_path(key)`: rejects any key not matching `KEY_PATTERN`, resolves the path and rejects it if it escapes the root (defence against path traversal such as `../../etc`).
  - `save(stream, key_hint)`:
    1. Validate the hint.
    2. Generate the key `"<hint>/<uuid hex>"`.
    3. Create the folder.
    4. Open the file with mode `"xb"` (fails if it already exists, so nothing is ever overwritten).
    5. Copy the stream in 64 KiB chunks.
    6. Return the key.
  - `open(key)`: raises `StorageError("stored file is missing")` if absent.
  - `delete(key)`: `unlink(missing_ok=True)`.
- User file names never become paths: keys are random (`attachments/<hex>` according to `CLAUDE.md` B14).

#### `app/integrations/storage/__init__.py`
- **Purpose:** `build_storage(settings)` returns `LocalStorage(settings.attachment_dir)`.
- **Used by:** the attachments router, the housekeeping job, tests.

---

### 4.5 Models and migrations

Every model inherits from `Base` (`app/models/base.py`). No model declares SQLAlchemy `relationship()` attributes: tables are linked only through foreign-key columns, and services join explicitly in their queries. The full column lists are in section 6.2; this section describes each file.

#### `app/models/base.py`
- **Purpose:** shared building blocks for all models.
- **Contents:**
  - `NAMING_CONVENTION`: deterministic constraint names, for example `ix_<label>`, `uq_<table>_<columns>`, `ck_<table>_<name>`, `fk_<table>_<column>_<referred table>`, `pk_<table>`. This is why every migration names its constraints `op.f("...")` predictably.
  - `ENUM_LENGTH = 32`.
  - `Base(DeclarativeBase)`: uses the naming convention, and maps Python `datetime` to `DateTime(timezone=True)`, so every timestamp is `timestamptz`.
  - `UuidPk`: mixin adding `id: UUID` primary key with a Python-side `uuid.uuid4` default.
  - `Timestamps`: mixin adding non-null `created_at` and `updated_at`. **There are no automatic defaults**: services must set both from the injected clock.
  - `enum_type(enum_cls, name)`: builds a SQLAlchemy `Enum` with `native_enum=False` (stored as `VARCHAR(32)`, not a PostgreSQL enum type), `create_constraint=True` (a CHECK constraint lists the allowed values), and `values_callable=_enum_values` (stores the lowercase **value**, not the Python member name). `CLAUDE.md` names this the convention for every enum column.
- **Imported by:** every model module.

#### `app/models/identity.py`
- **Purpose:** people and everything about their accounts.
- **Enums defined here:**
  - `EmailTokenPurpose`: `verify`, `reset`;
  - `Theme`: `system`, `light`, `dark`.
- **Models:**
  - `User` (`users`);
  - `MfaRecoveryCode` (`mfa_recovery_codes`);
  - `SignupRequest` (`signup_requests`);
  - `EmailToken` (`email_tokens`);
  - `RefreshToken` (`refresh_tokens`);
  - `ProtectedActionRequest` (`protected_action_requests`);
  - `RateLimitHit` (`rate_limit_hits`).
- **Module-level indexes:**
  - `uq_users_lower_email`: case-insensitive unique email;
  - `uq_signup_requests_one_pending`: at most one pending request per user;
  - `uq_rate_limit_hits_key_window_start`.
- **Created by migration:** `b03_identity_org_policy`.

#### `app/models/org.py`
- **Purpose:** the organisation: departments, Spokes, categories, confidential grants.
- **Models:**
  - `Department` (`departments`, primary key is the 2-to-6-letter code);
  - `SpokeAssignment` (`spoke_assignments`);
  - `Category` (`categories`);
  - `ConfidentialGrant` (`confidential_grants`).
- **Indexes:**
  - `uq_spoke_assignments_active` and `uq_confidential_grants_active`: partial unique indexes over rows with `revoked_at IS NULL`, so the same user and department (or category) can be granted again after a revoke;
  - `uq_categories_department_id_lower_name`: case-insensitive unique name within a department.
- **Notes:**
  - `Department.escalation_contact_user_id` uses `ForeignKey(..., use_alter=True)` because `users` and `departments` reference each other (`users.home_department_id` → `departments`). The migration adds that one foreign key after both tables exist (`b03` line 184, `op.create_foreign_key`).
  - `sla_mode` on both `Department` and `Category` was added by `r2c1_business_calendar`; it imports `SlaMode` from `app/models/calendar.py`.
- **Created by:** `b03`, extended by `r2c1`.

#### `app/models/policy.py`
- **Purpose:** versioned SLA and organisation policy.
- **Model:** `PolicyVersion` (`policy_versions`): `version` (unique, ≥1), `config` (JSONB), `created_by_id`, `created_at`.
- **Data:** the policy is never updated in place. Every change inserts `version + 1`, and the current policy is the highest version (`app/services/policy.py` `PolicyService.current_version`, Part 4).
- **Seeded row:** migration `b03` inserts version 1 with id `00000000-0000-4000-8000-000000000001` and `DEFAULT_POLICY_CONFIG`:

  | Key | Value |
  |---|---|
  | `initial_response_hours` | 24 |
  | `warning_hours` | low 18, medium 18, high 18, critical 12 |
  | `l3_hours` | low 48, medium 48, high 36, critical 30 |
  | `update_warning_hours` | 20 |
  | `update_cadence_hours` | 24 |
  | `eta_warning_hours` | 2 |
  | `escalation_repeat_hours` | 24 |
  | `requester_reminder_hours` | 48 |
  | `auto_close_business_days` | 3 |
  | `reopen_window_days` | 7 |
  | `max_reopens` | 3 |
  | `sla_mode` | `calendar` |
  | `admins_can_manage_departments` | true |

#### `app/models/audit.py`
- **Purpose:** the append-only audit trail.
- **Model:** `AuditLog` (`audit_log`). `old_value` and `new_value` are `JSONB(none_as_null=True)`, so Python `None` becomes SQL `NULL`, not the JSON value `null`.
  - `is_security_limited`: hides the entry from Admins (only Super Admins see it).
  - `is_confidential_ticket`: marks entries about confidential tickets.
- **Indexes:** `ix_audit_log_created_at` and `ix_audit_log_object_type_object_id`, plus single-column indexes on `actor_id`, `action`, `ticket_id` and `department_id`.
- **Created by:** `b05_audit_log`, which also adds the immutability trigger (6.5).

#### `app/models/ticket.py`
- **Purpose:** tickets and everything attached to them.
- **Enums defined here:**
  - `CloseReason`: `confirmed` (requester confirmed), `admin` (closed by an administrator), `auto` (auto-closed by the worker);
  - `TicketEventKind`: `comment`, `internal_note`, `audit`.
- **Models:**
  - `TicketCounter` (`ticket_counters`): composite primary key (department code, year), holding the last number used;
  - `Ticket` (`tickets`);
  - `TicketCollaborator` (`ticket_collaborators`): composite primary key (ticket, user);
  - `TicketEvent` (`ticket_events`): the timeline;
  - `Attachment` (`attachments`).
- **Indexes:**

  | Index | Purpose |
  |---|---|
  | `ix_tickets_department_id_status` | department queues |
  | `ix_tickets_escalation_level_priority` | urgency views |
  | `ix_tickets_updated_at` | recently changed tickets |
  | `ix_tickets_title_trgm`, `ix_tickets_ticket_no_trgm` | GIN trigram indexes for `ILIKE '%text%'` search |
  | `ix_ticket_events_ticket_id_at` | timeline order |
  | `ix_ticket_events_kpi_actions` | partial index on `(action, at, ticket_id)` for KPI history, `r2a` |
  | `ix_tickets_created_at` | `r2a` |
  | `ix_attachments_unlinked_created_at` | partial, `ticket_id IS NULL`, for clean-up of abandoned uploads |
- **Created by:** `b04_tickets_sla_notifications` (plus the `r2a` indexes).

#### `app/models/sla.py`
- **Purpose:** SLA timers and escalation history.
- **Enum defined here:** `TimerKind`: `initial_response`, `progress_update`, `eta`, `auto_close`, `requester_reminder`, `hold_review`. Only the first three are "SLA" timers that raise the ticket's escalation level (`CLAUDE.md` B12).
- **Models:**
  - `SlaTimer` (`sla_timers`): **one row per ticket and kind** (`UNIQUE(ticket_id, kind)`). A restart overwrites the row and increments `cycle`, so only the latest cycle is stored.
  - `EscalationEvent` (`escalation_events`): one row per escalation step reached, unique per (ticket, timer kind, cycle, step key). That uniqueness makes escalation idempotent: the scanner inserts with `ON CONFLICT DO NOTHING` (Part 4).
- **Indexes:** `ix_sla_timers_active_due_at` (partial: running timers only, used by the scanner) and `ix_escalation_events_at` (`r2a`, KPI queries).
- **Created by:** `b04`.

#### `app/models/notification.py`
- **Purpose:** in-portal notifications, the email outbox, and the worker heartbeat.
- **Enum defined here:** `EmailStatus`: `pending`, `sent`, `failed`.
- **Models:**
  - `Notification` (`notifications`);
  - `EmailOutbox` (`email_outbox`);
  - `WorkerHeartbeat` (`worker_heartbeat`, primary key `name`).
- **Indexes:**
  - `uq_notifications_user_id_dedupe_key`: partial unique, `dedupe_key IS NOT NULL`, so the same escalation never notifies a user twice;
  - `ix_notifications_user_id_read_at_created_at`: the bell list;
  - `ix_email_outbox_status_next_attempt_at`: the sender job's queue.
- **Created by:** `b04`.

#### `app/models/saved_view.py`
- **Purpose:** user-owned saved ticket-list filters (Release 2).
- **Model:** `SavedView` (`saved_views`) with `query` (JSONB) and `deleted_at` (soft delete).
- **Index:** `uq_saved_views_owner_id_name`, a partial unique index on `(owner_id, lower(name)) WHERE deleted_at IS NULL`.
- **Created by:** `r2b_saved_views`.

#### `app/models/calendar.py`
- **Purpose:** the business calendar for business-hours SLAs (Release 2, R2-C1).
- **Contents:**
  - `CALENDAR_ROW_ID = 1`;
  - enum `SlaMode` (`calendar`, `business`);
  - `BusinessCalendar` (`business_calendar`, a single-row table);
  - `Holiday` (`holidays`);
  - partial unique index `uq_holidays_active_date` (one active holiday per date).
- **Note:** the table may be empty. Code then falls back to the defaults Monday to Friday, 09:00 to 18:00 (`app/services/calendar.py` `load_working_calendar`, Part 4).
- **Created by:** `r2c1_business_calendar`, which also creates the SQL function `working_seconds` (6.5).

#### `app/models/preferences.py`
- **Purpose:** per-user email preferences and the daily digest (Release 2, R2-C2).
- **Contents:**
  - `DEFAULT_DIGEST_HOUR = 9`;
  - enum `NonCriticalEmail` (`immediate`, `daily_digest`, `off`);
  - `NotificationPreference` (`notification_preferences`, primary key `user_id`; a missing row means the defaults);
  - `NotificationDigest` (`notification_digests`, unique per user and IST date);
  - `DigestItem` (`digest_items`, one per queued notification);
  - partial index `ix_digest_items_pending`.
- **Created by:** `r2c2_notification_preferences`.

#### `app/models/__init__.py`
- **Purpose:** imports every model module and re-exports all model classes and model-level enums (`__all__`, 40 names).
- **Why it matters:** importing `app.models` registers every table on `Base.metadata`. `alembic/env.py` relies on that for autogenerate and `alembic check`, and tests use it to clean tables (`tests/conftest.py`, Part 6).

#### Migrations: `alembic/versions/`

Revisions form one straight chain (`down_revision` of each points to the previous one):

`b02_extensions` → `b03_identity_org_policy` → `b04_tickets_sla_notifications` → `b05_audit_log` → `r2a_kpi_indexes` → `r2b_saved_views` → `r2c1_business_calendar` → `r2c2_notification_preferences` (head).

| Revision | Tables created or changed | Hand-written parts beyond autogenerate |
|---|---|---|
| `b02_extensions` | none | `CREATE EXTENSION IF NOT EXISTS pg_trgm` (needed by the trigram indexes) |
| `b03_identity_org_policy` | `departments`, `rate_limit_hits`, `categories`, `users`, `confidential_grants`, `email_tokens`, `mfa_recovery_codes`, `policy_versions`, `protected_action_requests`, `refresh_tokens`, `signup_requests`, `spoke_assignments` | the deferred foreign key `departments.escalation_contact_user_id` → `users` (circular reference); inserts policy version 1 |
| `b04_tickets_sla_notifications` | `ticket_counters`, `worker_heartbeat`, `tickets`, `attachments`, `escalation_events`, `notifications`, `sla_timers`, `ticket_collaborators`, `ticket_events`, `email_outbox` | function `reject_ticket_event_change()` and trigger `ticket_events_immutable` |
| `b05_audit_log` | `audit_log` | function `reject_audit_log_change()`, trigger `audit_log_immutable`, and `REVOKE UPDATE, DELETE ON audit_log, ticket_events FROM PUBLIC` |
| `r2a_kpi_indexes` | indexes only: `ix_escalation_events_at`, `ix_ticket_events_kpi_actions`, `ix_tickets_created_at` | none |
| `r2b_saved_views` | `saved_views` | the functional partial unique index on `lower(name)` |
| `r2c1_business_calendar` | `business_calendar`, `holidays`; adds `sla_mode` to `categories` and `departments` | named CHECK constraints for the new `sla_mode` columns; the SQL function `working_seconds(timestamptz, timestamptz)` |
| `r2c2_notification_preferences` | `notification_digests`, `notification_preferences`, `digest_items` | none |

Every revision also has a `downgrade()` that reverses it. `docs/OPERATIONS.md` says not to run downgrades on production data: restore a backup instead.

### 4.6 Policy (`app/policy/`)

The policy package answers two questions: **may this actor see this ticket**, and **may this actor do this**. Services ask it before acting. Most functions are pure (no database access); the few that query are marked.

#### `app/policy/__init__.py`
- **Purpose:** the `Actor` type, the authenticated caller.
- **Contents:**
  - `STAFF_ROLES = {admin, super_admin}`.
  - `Actor` (frozen dataclass, lines 9-44): `id`, `global_role`, `department_id` (home department), `spoke_department_ids` (frozenset), `name`, `email`.
  - Properties:

    | Property | Meaning |
    |---|---|
    | `is_spoke` | has at least one Spoke department |
    | `is_admin_or_super_admin` | global role is `admin` or `super_admin` |
    | `is_super_admin` | global role is `super_admin` |
    | `roles` | `[employee]`, plus `spoke` if a Spoke, plus the staff role |
    | `has_role(role)` | `employee` always true; `spoke` means `is_spoke`; others compare the global role |
- **Built by:** `app/policy/actors.py` `load_actor` and `app/services/me.py` (Part 4).
- **Used by:** every service, deps and the worker.

#### `app/policy/actors.py`
- **`load_actor(session, user_id) -> Actor | None`** (lines 12-28). **Queries the database.**
  1. `session.get(User, user_id)`.
  2. Return `None` if the user does not exist or is not `active`.
  3. Select the user's Spoke departments: `spoke_assignments` rows with `revoked_at IS NULL`.
  4. Build the `Actor`.
- **Used by:** the notification handlers and recipient helpers, `app/services/sla/escalation.py` and `app/worker/jobs/digest.py`. They need an `Actor` for someone who is not the caller, for example to check whether a recipient may see a ticket.

#### `app/policy/flags.py`
- **Purpose:** the permission flags of Appendix A.5. The frontend receives them in `Me.permissions` to show or hide features.
- **Constants:** 24 flag strings. `TICKET_OPERATION_FLAGS` groups the ten ticket operation flags.
- **`compute_permissions(actor, admins_can_manage_departments) -> list[str]`** (lines 33-54). Builds `(flag, granted)` pairs and keeps the granted ones:

  | Flag | Employee | Spoke | Admin | Super Admin |
  |---|---|---|---|---|
  | `tickets.create` | yes | yes | yes | yes |
  | `tickets.view_all` | | | yes | yes |
  | `tickets.view_department` | | yes | only if also a Spoke | only if also a Spoke |
  | the ten `tickets.<operation>` flags (acknowledge, assign, transfer, change_priority, revise_eta, hold, resolve, close_admin, reopen, internal_notes) | | yes | yes | yes |
  | `users.approve_employee` | | | yes | yes |
  | `users.approve_admin`, `users.approve_super_admin` | | | | yes |
  | `users.manage_roles`, `departments.manage` | | | yes **if** policy `admins_can_manage_departments` is true | yes |
  | `admins.manage`, `superadmins.protect`, `confidential.manage`, `policy.manage` | | | | yes |
  | `audit.view_all`, `reports.view_org` | | | yes | yes |

  These flags are coarse feature switches. The real per-ticket decisions are made by `allowed_actions.py`.
- **`has_permission(actor, flag, admins_can_manage_departments)`:** `flag in compute_permissions(...)`. It rebuilds the list on every call; that is cheap, since there are fewer than 30 flags.
- **Used by:** `app/services/me.py` (`Me.permissions`), `permissions.py`, `reports.py`, and several services directly (`audit_reads`, `dashboards`, `protected_actions`, `signup`, `ticket_reads`).

#### `app/policy/permissions.py`
- **Purpose:** account, administration and organisation permissions (the B08 to B10 rules).
- **Constants:**
  - `SIGNUP_ROLE_RANK`: employee 0, admin 1, super_admin 2;
  - `MIN_ACTIVE_SUPER_ADMINS = 2`.
- **Functions:**

  | Function | Lines | Rule | Used by |
  |---|---|---|---|
  | `can_decide_signup(actor, requested_role, approved_role, applicant_id)` | 27-41 | Never your own request. The highest of the requested and approved roles decides: employee needs Admin or Super Admin; admin or super_admin needs a Super Admin. A role outside the rank table (for example `spoke`) is refused. | `services/signup.py`, `services/dashboards.py` (pending approvals count) |
  | `can_list_users(actor, flag)` | 44-47 | has `users.manage_roles` or `admins.manage` | `services/users.py` |
  | `can_manage_account(actor, target_role, flag)` | 50-57 | needs `users.manage_roles`. A Super Admin may manage anyone; an Admin only `employee` targets. | `services/users.py` |
  | `can_change_account_state(actor, target_id, target_role, flag)` | 60-68 | never yourself, then `can_manage_account` | `services/users.py` (activate, deactivate) |
  | `deactivation_is_protected(target_role)` | 71-72 | deactivating a Super Admin needs a protected action | `services/users.py` |
  | `can_manage_admins(actor, flag)` | 75-76 | `admins.manage` (Super Admin) | `services/users.py` |
  | `keeps_minimum_super_admins(count)` | 79-80 | after removing one, at least 2 active Super Admins remain | `services/protected_actions.py` |
  | `is_independent_super_admin(actor, requested_by_id, target_id)` | 83-86 | a Super Admin who is neither requester nor target (mirrors the database CHECK) | `services/protected_actions.py` |
  | `can_decide_protected_action(...)` | 89-99 | the request is still `pending`, not expired, and the decider is independent | `services/protected_actions.py` |
  | `can_manage_departments(actor, flag)` | 102-103 | `departments.manage`; also governs categories, Spokes and escalation contacts | `services/departments.py`, `services/categories.py` |
  | `can_manage_grants(actor, flag)` | 106-107 | `confidential.manage` (Super Admin) | `services/confidential_grants.py` |
  | `can_read_policy(actor)` | 110-111 | Admin or Super Admin | `services/policy_admin.py`, `services/calendar.py` |
  | `can_manage_policy(actor, flag)` | 114-115 | `policy.manage` (Super Admin) | `services/policy_admin.py`, `services/calendar.py` |

  "flag" above is short for the `admins_can_manage_departments` policy value, which every caller passes in after reading the current policy.

#### `app/policy/relationships.py`
- **Purpose:** how the actor relates to one ticket.
- **`ActorContext`** (frozen dataclass, lines 14-29): `actor` plus the booleans below.

  | Field | True when |
  |---|---|
  | `is_requester` | the actor raised the ticket |
  | `is_owner` | the actor is `owner_id` |
  | `is_assignee` | the actor is `assignee_id` |
  | `is_collaborator` | the actor is in `ticket_collaborators` |
  | `is_department_spoke` | the ticket's current department is one of the actor's Spoke departments |
  | `is_escalation_contact` | the actor is the escalation contact of the ticket's department (the B26 rule) |
  | `has_grant` | the actor has an active confidential grant on the ticket's category |
  | `is_admin` | the actor's global role is exactly `admin` |
  | `is_super_admin` | the actor's global role is `super_admin` |

  Property `has_confidential_access` = Super Admin or a grant.
- **`relationship_from(actor, ticket, collaborator_ids, granted_category_ids, contact_department_ids)`** (32-50): pure. It builds the context from pre-loaded sets, so `TicketPresenter` can compute contexts for a whole page of tickets with a fixed number of queries (`CLAUDE.md` B13).
- **Database helpers:** `is_collaborator` (53-60, one EXISTS query), `has_active_grant` (63-73) and `contact_departments` (76-78, the departments where the actor is escalation contact).
- **`load_relationship(session, actor, ticket)`** (81-90): runs the three helpers for one ticket, then `relationship_from`.
- **Used by:** `visibility.py`, `allowed_actions.py`, `services/ticket_reads.py`, `handlers/notification_handlers.py`.

#### `app/policy/visibility.py`
- **Purpose:** the single visibility rule (Appendix R.2), in two equivalent forms: a Python predicate for one ticket and a SQL clause for queries.
- **`is_visible(ctx, confidential)`** (11-16):
  1. A Super Admin, the requester, the assignee or a collaborator always sees the ticket, confidential or not.
  2. Otherwise, a **confidential** ticket is visible only with a grant on its category.
  3. Otherwise (not confidential): a Spoke of its department, the department's escalation contact, or any Admin.

  Note that `is_owner` is **not** in this list. An owner who is not also a Spoke, assignee or collaborator cannot see the ticket. `CLAUDE.md` B11 and B18 record this ("an owner who lost visibility gets no actions").
- **`can_view_ticket(session, actor, ticket)`** (19-20): `load_relationship` plus `is_visible`. Used by `services/attachments.py`, `handlers/recipients.py` and `services/sla/escalation.py`.
- **`visible_ticket_clause(actor)`** (23-52) returns a SQL boolean expression for `WHERE`:
  - a Super Admin gets `TRUE`;
  - everyone else gets `requester = me OR assignee = me OR EXISTS(collaborator row) OR (not confidential AND department IN my Spoke departments) OR (not confidential AND department IN (departments where I am escalation contact)) OR (not confidential, if I am Admin) OR (confidential AND EXISTS(active grant on its category))`.

  The Spoke branch becomes `FALSE` for non-Spokes and the Admin branch `FALSE` for non-Admins, so the planner can drop them. `CLAUDE.md` requires this clause in **every** ticket query: lists, counts, dashboards, KPIs, exports, notification lists, audit and digests all use it (6.4 and the callers listed in this section).
- **Consistency:** `is_visible` and `visible_ticket_clause` encode the same rule twice, once in Python and once in SQL. A change to one must be made in the other. The leak tests (`tests/security/test_confidentiality_leaks.py`, Part 6) check the result end to end.

#### `app/policy/allowed_actions.py`
- **Purpose:** which ticket actions an actor may perform now (Appendix R.3). The result becomes `Ticket.allowed_actions` in every ticket response, and the same check guards every workflow request.
- **Constants:**
  - `ActorClass` enum: `requester`, `collaborator`, `assignee`, `team`.
  - Status sets:

    | Set | Contents |
    |---|---|
    | `ACTIVE_STATUSES` | new, acknowledged, assigned, in progress, awaiting requester, on hold, reopened |
    | `WORKING_STATUSES` | active minus `new` |
    | `DISCUSSION_STATUSES` | everything except closed and cancelled |
    | `REOPENABLE_STATUSES` | resolved, closed |

  - Class sets: `TEAM` (team only), `WORKERS` (team and assignee), `REQUESTER`, `PARTICIPANTS` (all four classes).
- **`ACTION_RULES`** (lines 44-76): for each `TicketAction`, the actor classes and statuses that allow it.

  | Action | Who | In which statuses |
  |---|---|---|
  | `acknowledge` | team | new |
  | `assign` | team | working statuses |
  | `transfer`, `change_priority` | team | active statuses |
  | `revise_eta` | team, assignee | working statuses |
  | `start_work` | team, assignee | acknowledged, assigned, reopened |
  | `ask_requester`, `hold`, `resolve` | team, assignee | in progress |
  | `resume` | team, assignee | awaiting requester, on hold |
  | `confirm_closure` | requester | resolved |
  | `reopen` | requester, team | resolved, closed (plus the window and count limits) |
  | `cancel` | team in active statuses; requester only in `new` | |
  | `close_admin` | team | resolved |
  | `comment` | all participants | discussion statuses |
  | `internal_note` | team, assignee | discussion statuses |
  | `manage_collaborators` | team | discussion statuses |

  `NOT_FOR_REQUESTER_AS_TEAM = {acknowledge, resolve}` and `NEVER_FOR_REQUESTER = {resolve}`: a person who raised a ticket never resolves it, and never acknowledges it in their team role, even if they are a Spoke of that department.
- **Walkthrough:**
  - `actor_classes(ctx, confidential)` (83-95): if the ticket is not visible, no classes at all. Otherwise: requester, collaborator and assignee from the context; **team** = Spoke of the department, owner, Admin or Super Admin.
  - `classes_for_action(action, ctx, confidential)` (98-108): removes classes for requesters as described above.
  - `reopen_available(ticket, policy, now)` (111-114): needs `resolved_at`, `reopen_count < max_reopens`, and `now <= resolved_at + reopen_window_days` (inclusive).
  - `is_action_allowed(action, ctx, ticket, policy, now)` (117-131): any rule whose classes intersect the actor's classes and whose statuses contain the ticket's status. For `reopen`, the window check must also pass.
  - `compute_allowed_actions(...)` (134-141): all allowed actions, in `TicketAction` enum order.
  - `classify_denial(action, ctx, ticket)` (144-148): when an action is refused, `invalid_transition` (409) if the actor's class could do it in some other status, otherwise `forbidden` (403). Callers check visibility first and return 404 for invisible tickets (`CLAUDE.md` B11).
- **Imports:** `PolicyConfig` from `app/services/policy.py`. This is the policy-to-service dependency listed in 13.0 #4.
- **Used by:** `services/ticket_reads.py` (`compute_allowed_actions`), `services/workflow/common.py` (`is_action_allowed`, `classify_denial`).

#### `app/policy/reports.py`
- **Purpose:** report and saved-view access (Release 2).
- **`ReportScope(department_ids)`:** `None` means the whole organisation; a set limits the report to those departments.
- **Functions:**
  - `can_view_org_reports` (19-20): `reports.view_org`.
  - `can_view_reports` (23-26): org reports, or `tickets.view_department` (Spokes).
  - `report_scope(actor, flag, department_id) -> ReportScope | None` (29-41):
    1. Org viewers get the requested department, or everything.
    2. Others without report access get `None` (the caller turns that into 403).
    3. A Spoke without a requested department gets all their Spoke departments.
    4. A Spoke asking for one of their departments gets it.
    5. A Spoke asking for any other department gets `None`.
  - `built_in_view_scope(actor, flag)` (44-51): `queue` for Spokes, `all` for staff with `tickets.view_all`, otherwise `mine`. This is the scope used inside built-in saved views.
  - `sees_department_views(actor)`: Spokes only (the "My Department - SLA Breached" view).
  - `owns_saved_view(actor, owner_id)`: `actor.id == owner_id`.
- **Used by:** `services/kpis.py`, `services/exports/__init__.py`, `services/saved_views.py`.

### 4.7 Queries (`app/queries/`)

Plain functions that build SQLAlchemy `Select` statements. They never execute anything; services run them. There is no `__init__.py` in this folder, so it is an implicit namespace package. The same is true of `app/schemas`, `app/services` and `app/integrations`, while every other package has an `__init__.py`. This works in Python 3 (imports, mypy and tests all pass), but **Unclear - needs confirmation** whether it is intentional (13.0 #13).

#### `app/queries/tickets.py`
- **Purpose:** filters, sorting and visibility for ticket lists.
- **Constants:**
  - `INACTIVE_STATUSES` (resolved, closed, cancelled) and `ACTIVE_STATUSES` (the other seven; the same set as in `allowed_actions.py`, see 13.0);
  - `LIKE_ESCAPE = "\\"`;
  - `SORTS`: `urgency`, `created_at`, `-created_at`, `priority`, `-priority`, `status`, `title`;
  - `DEFAULT_SORT = "urgency"`.
- **`TicketFilters`** (frozen dataclass, 23-40): every list filter, plus `extra` (additional SQL clauses the caller adds, for example the scope).
- **Functions:**

  | Function | Lines | What it builds |
  |---|---|---|
  | `priority_rank()` | 43-48 | `CASE priority WHEN 'low' THEN 1 ... END` from `PRIORITY_RANK` |
  | `is_active_ticket()` | 51-52 | `status IN (active statuses)` |
  | `mine_clause(actor)` | 72-77 | `id IN (SELECT id FROM tickets WHERE requester = me UNION SELECT ticket_id FROM ticket_collaborators WHERE user = me)`. Written as a UNION, not an OR with EXISTS, so PostgreSQL can use both indexes (`docs/SECURITY.md`). |
  | `assigned_clause(actor)` | 80-81 | `assignee_id = me` |
  | `in_departments(ids)` | 84-85 | `department_id IN (...)` |
  | `_escape_like(term)` | 88-93 | escapes `\`, `%` and `_` so user text is matched literally |
  | `_sla_state_clause(state)` | 96-103 | `unacknowledged` → status `new`; `warning` → escalation level 1; `breached` → level ≥ 2; `stale` → `update_overdue` |
  | `filter_clauses(filters, now)` | 106-150 | one clause per filter that is set (details below) |
  | `visible_tickets(actor)` | 153-154 | `SELECT tickets WHERE visible_ticket_clause(actor)` |
  | `apply_sort(statement, sort)` | 157-176 | the chosen ordering, always tie-broken by `ticket_no` for stable pages |
  | `ticket_list_statement(actor, filters, sort, now)` | 179-182 | visible + filters + sort |
  | `visible_ticket_by_number(actor, ticket_no)` | 185-186 | one visible ticket by number |

  Filter details for `filter_clauses`:
  - `overdue_eta` adds: active, ETA set, ETA before now.
  - `awaiting_before=T` adds: status `awaiting_requester` and `awaiting_since <= T`.
  - `q` adds a case-insensitive `ILIKE '%term%'` on number or title, served by the trigram indexes.

  The `urgency` sort is: active tickets first, then higher escalation level, higher priority, older `sla_started_at`, then number.
- **Used by:** `services/ticket_reads.py` (lists and detail), `services/dashboards.py`, `services/exports/__init__.py`, `app/queries/kpis.py` (`is_active_ticket`).

#### `app/queries/audit.py`
- **Purpose:** the audit log search.
- **Contents:**
  - `AuditFilters` (`q`, `actor_id`, `action`, `ticket_no`, `created_from`, `created_to`);
  - its own `_escape_like` (a duplicate of the one in `tickets.py`);
  - `audit_scope`, `filter_clauses` and `audit_statement`.
- **Walkthrough:**
  - `audit_scope(actor)` (34-40): a Super Admin sees everything. Everyone else (in practice Admins, because the endpoint needs `audit.view_all`) sees only entries that are not security-limited **and** either have no ticket or concern a ticket visible to them.
  - `filter_clauses` (43-64): `q` searches `action` and `detail` with ILIKE; the other filters are equality or range checks. The ticket filter is by ticket **number** (`CLAUDE.md` B20).
  - `audit_statement` (67-73): `SELECT audit_log LEFT JOIN tickets`, the scope and filters, newest first, tie-broken by id.
- **Used by:** `services/audit_reads.py`.

#### `app/queries/kpis.py`
- **Purpose:** every aggregate behind the KPI report and the KPI fields of the dashboards (R2-A, Appendix R.12). Each function takes a `scope` (a list of WHERE clauses that always starts with the visibility clause) and usually a time `Window`.
- **Constants:**
  - action names `acknowledged`, `resolved`, `reopened`;
  - `BREACH_STEP = "L2"`;
  - `REPEAT_PREFIX = "L3_REPEAT_"`;
  - `IST_ZONE = "Asia/Kolkata"` (used inside PostgreSQL, which has its own timezone database);
  - `UNACKNOWLEDGED_AFTER = 24h`;
  - `TOP_CATEGORIES = 10`;
  - `UNCATEGORISED`;
  - `PAUSED_STATUSES` (awaiting requester, on hold);
  - `AGING_BUCKETS`: 0-2, 3-7, 8-14, 15-30 and 31+ days, as day ranges.
- **`Window(start, end)`:** `contains(column)` is `column >= start AND column < end` (half-open).
- **Functions:**

  | Function | Lines | Returns | How |
  |---|---|---|---|
  | `scope_clauses(visibility, department_ids, priorities)` | 64-74 | the WHERE list | visibility plus optional department and priority filters |
  | `_first_event(action, window)` | 77-94 | subquery (ticket, at) | events of that action inside the window that have **no earlier event of the same action** (NOT EXISTS on an alias; ties broken by id). This finds each ticket's *first* acknowledgement or resolution, using the partial index `ix_ticket_events_kpi_actions`. |
  | `_elapsed(first)` | 97-98 | seconds | `epoch(first.at - ticket.created_at)` |
  | `duration_statement(scope, action, window)` | 101-115 | count, average, median | over first events; the median is `percentile_cont(0.5)` |
  | `trend_statement(scope, window)` | 118-142 | per IST day plus an overall row | `GROUPING SETS ((day), ())` gives the daily rows and the total in one query; `grouping(day)` = 1 marks the total row |
  | `sla_statement(scope, window)` | 145-164 | per department: missed, met | tickets created in the window. *Missed* = an initial-response escalation of level ≥ 2 exists; *met* = not missed and acknowledged. |
  | `_event_in(action, window)` | 167-172 | EXISTS clause | |
  | `reopen_statement(scope, window)` | 175-181 | resolved count, reopened count | tickets resolved in the window, and how many of them were also reopened in the window |
  | `escalation_statement(scope, window)` | 184-194 | count per level | escalation events in the window, excluding `CREATION_CONTACT` |
  | `eta_breach_statement(scope, window)` | 197-208 | count | ETA timer `L2` steps in the window |
  | `_age_between(now, low, high)` | 211-215 | clause | created between the bucket's day bounds |
  | `snapshot_statement(scope, now)` | 218-231 | 8 counts | on active tickets: stale (`update_overdue`), overdue ETA (not paused), unacknowledged for 24h+, and the 5 aging buckets, all in one pass with `count(*) FILTER (...)` |
  | `persistent_l3_statement(scope)` | 234-249 | count | active tickets at level 3 whose current timer cycle has already had an `L3_REPEAT_n` step |
  | `department_statement(scope)` | 252-269 | per department | active count, counts per priority, and on track / warning / breached by escalation level |
  | `workload_statement(scope, column)` | 272-279 | per assignee or owner | active and breached counts (`column` is `Ticket.assignee_id` or `Ticket.owner_id`) |
  | `top_categories_statement(scope, window)` | 282-294 | top 10 | tickets created in the window by category; no category counts as "Uncategorised" |
  | `departments_statement(department_ids, requested)` | 297-306 | id, name | a requested department (even if inactive), otherwise active departments in scope |
- **Imports:** `AgingBucket` from `app/schemas/reports.py` and `CREATION_CONTACT` from `app/services/sla/escalation.py` (queries depending on schemas and services; 13.0).
- **Used by:** `services/kpis.py`.

### 4.8 Schemas (`app/schemas/`)

Pydantic models for request bodies and responses, the JSON shapes of Appendix A. There is no `__init__.py` (namespace package, like `app/queries`).

Shared conventions:
- Every model inherits `ApiModel` (`from_attributes=True`).
- Optional response fields that the contract says must be **omitted** (not `null`) use `Field(default=None, exclude_if=is_none)` (`CLAUDE.md` B23).
- Text inputs are trimmed with `StringConstraints(strip_whitespace=True, ...)`.
- Validation failures become 422 `validation_error` with `fields`, through `app/core/errors.py`.

#### `app/schemas/common.py`
- **Contents:**
  - `ApiModel`;
  - `is_none(value)`;
  - generic `Page[T]` (`items`, `total`, `page`, `page_size`);
  - `UserRef` (`id`, `name`, `email`, `title` omitted when null);
  - `SystemActor` (`{"id": "system", "name": "System"}`) and `SYSTEM_ACTOR`;
  - `type Actor = UserRef | SystemActor`.
- **Note:** this `Actor` alias has the same name as `app.policy.Actor`, a different thing (13.0).
- **Used by:** almost every schema and many services.

#### `app/schemas/auth.py`
- **`normalize_email(value)`:** trims, lower-cases and validates syntax with `email_validator` (no DNS check), raising "Enter a valid email address".
- **`NormalizedEmail`:** 3 to 320 characters plus that validator.
- **Models:**

  | Model | Fields |
  |---|---|
  | `Me` (extends `UserRef`) | `roles`, `department_id`, `spoke_departments`, `permissions`, `mfa_enabled`, `theme` (omitted when null) |
  | `LoginRequest` | `email`, `password` (1 to 1024 characters) |
  | `LoginSuccess` | `access_token`, `expires_in`, `user: Me` |
  | `MfaRequired` | `mfa_required: true`, `mfa_token` |
  | `MfaEnrolRequired` | `mfa_enrol_required: true`, `mfa_token` |
  | `MfaTokenRequest` | `mfa_token` |
  | `MfaCodeRequest` | `mfa_token`, `code` |
  | `MfaSetupResponse` | `secret`, `otpauth_uri` |
  | `MfaConfirmSuccess` (extends `LoginSuccess`) | `recovery_codes` |
  | `RefreshResponse` | `access_token`, `expires_in` |
  | `ForgotPasswordRequest` | `email` |
  | `ResetPasswordRequest` | `token`, `password` (max 1024; the strength policy is checked in the service) |
  | `PublicDepartment` | `id`, `name` |
  | `AttachmentLimits` | `max_bytes`, `max_files`, `allowed_mime_types` |
  | `PublicConfig` | `allowed_email_domains`, `departments`, `attachment_limits`, `password_min_length`, `first_response_hours` |
- **Used by:** `services/auth.py`, `services/me.py`, `services/mfa.py`, `services/policy.py`, routers `auth` and `config`.

#### `app/schemas/signup.py`
- **Types:**
  - `SIGNUP_ROLES` and `ensure_signup_role`: `SignupRole` accepts only employee, admin or super_admin, never `spoke`;
  - `PersonName`: 2 to 100 characters;
  - `DepartmentCode`: 1 to 6 characters (existence is checked in the service);
  - `Reason`: 5 to 1000 characters, trimmed. Reused by workflow and user schemas.
- **Models:**
  - `SignupBody`;
  - `SignupAccepted(message)`;
  - `VerifyEmailBody` and `VerifyEmailResult(state)`;
  - `ResendVerificationBody`;
  - `ReapplyBody`;
  - `ApproveSignupBody` (`approved_role`, `approved_department`);
  - `RejectSignupBody(reason)`;
  - `SignupRequestOut`: includes `can_approve`, computed per caller with `can_decide_signup`.
- **Password strength** (12 to 128 characters, mixed case, a digit) is checked in the service with `password_policy_error`, not in the schema. The schema only caps the length at 1024.
- **Used by:** `services/signup.py`, `services/dashboards.py`, router `signup`.

#### `app/schemas/users.py`
- **Constants:** `MAX_SPOKE_DEPARTMENTS = 50`, `ID_MAX_LENGTH = 64`.
- **Models:**

  | Model | Fields |
  |---|---|
  | `UserListItem` (extends `UserRef`) | `roles`, `state`, `department_id`, `spoke_departments`, `last_login_at`, `created_at` |
  | `UpdateRolesBody` | `spoke_departments` (up to 50 codes), `reason` |
  | `DeactivateBody` | `reason` |
  | `DeactivationResult` | `result` (`deactivated` or `protected_request_created`), `open_ticket_count`, `protected_action_id` |
  | `PromoteAdminBody` | `user_id` |
  | `CreateProtectedActionBody` | `kind`, `target_user_id`, `reason` |
  | `RejectProtectedActionBody` | `reason` |
  | `ProtectedActionOut` | `id`, `kind`, `target`, `requested_by`, `reason`, `status`, `decided_by`, `decision_reason`, `created_at`, `expires_at`, `can_decide` |
- **Used by:** `services/users.py`, `services/protected_actions.py`, routers `users`, `admins` and `protected_actions`.

#### `app/schemas/org.py`
- **Types:**
  - `ID_MAX_LENGTH = 64`;
  - `DepartmentId`: `^[A-Z]{2,6}$`, trimmed;
  - `OrgName`: 2 to 80 characters, trimmed;
  - `EntityId`: 1 to 64 characters.
- **Models:**

  | Model | Fields |
  |---|---|
  | `CategoryOut` | `id`, `department_id`, `name`, `confidential`, `active`, `sla_mode` |
  | `DepartmentOut` | `id`, `name`, `active`, `accepts_tickets`, `spokes`, `escalation_contact`, `categories`, `sla_mode` |
  | `CreateDepartmentBody` | `id`, `name` |
  | `UpdateDepartmentBody` | `name?`, `active?`, `sla_mode?` |
  | `AddSpokeBody` | `user_id` |
  | `EscalationContactBody` | `contact_id` (nullable) |
  | `CreateCategoryBody` | `name`, `confidential` |
  | `UpdateCategoryBody` | `name?`, `active?`, `confidential?`, `sla_mode?` |
  | `CreateGrantBody` | `user_id`, `category_id` |
  | `ConfidentialGrantOut` | `id`, `user`, `category`, `granted_by`, `granted_at` |
- **`SlaModeChange` and `SlaModeField` (R2-C1):** `SlaModeField.sla_mode_change()` returns `None` when the request did not mention `sla_mode` (checked with `model_fields_set`), or `SlaModeChange(value)` when it did, even if the value is `null`. This is how "leave unchanged" is told apart from "reset to inherit".
- **Imports:** `SlaMode` from `app/models/calendar.py`.
- **Used by:** `services/departments.py`, `services/categories.py`, `services/confidential_grants.py`, the three organisation routers.

#### `app/schemas/policy.py`
- **Constants:** `MIN_HOURS = 1`, `MAX_HOURS = 168`, `MAX_ETA_WARNING_HOURS = 48`, `MAX_AUTO_CLOSE_BUSINESS_DAYS = 30`, `MAX_REOPEN_WINDOW_DAYS = 90`, `MAX_REOPENS = 10`; `Hours` (1 to 168).
- **`PolicyBody`:** every `PolicyConfig` key with its range. `auto_close_business_days` may be null (auto-close off). The cross-field rules (warning below initial response, L3 above it, update warning below cadence) are in `app/services/policy_admin.py` `policy_errors` (Part 4).
- **Response model:** `PolicyConfig`, which lives in `app/services/policy.py`, not here.

#### `app/schemas/tickets.py`
- **Enums:**
  - `TicketScope` (`mine`, `assigned`, `queue`, `all`);
  - `SlaStateFilter` (`unacknowledged`, `warning`, `breached`, `stale`);
  - `OPEN_STATUS = "open"`, a pseudo-status the list endpoint accepts.
- **Models:**

  | Model | Fields |
  |---|---|
  | `AttachmentOut` | `id`, `name`, `size`, `mime`, `scan_status` |
  | `HoldOut` | `reason`, `review_date` |
  | `FeedbackOut` | `rating`, `comment` |
  | `TicketOut` | the full ticket for the API: `id` (the **ticket number**, not the UUID), title, description, department and category, priorities, status, confidential, requester, owner, assignee and collaborators (`UserRef`s), timestamps, `reopen_count`, `hold`, `resolution_summary`, `feedback`, `sla` (`SlaState`), `allowed_actions`, `attachments` |
  | `TimelineEventOut` | `id`, `at`, `actor`, `type`, `action?`, `detail?`, `body?`, `public` |
  | `CreateTicketBody` | `department_id`, `category_id?`, `title` (1 to 120), `description` (1 to 5000), `priority`, `confidential`, `attachment_ids` |
  | `CommentBody` | `body` (1 to 5000), `internal` |
  | `CollaboratorBody` | `user_id` |
- **Types:** `TicketTitle`, `TicketDescription`, `EntityId`, `CommentText`.
- **Imports:** `SlaState` from `app/services/sla/sla_object.py` (a schema depending on a service; 13.0) and `TicketEventKind` from `app/models/ticket.py`.
- **Used by:** ticket services and routers, `app/queries/tickets.py` (`SlaStateFilter`), dashboards and saved views.

#### `app/schemas/attachments.py`
- **Purpose:** re-exports `AttachmentOut` from `tickets.py`; nothing else. Used by router `attachments`.

#### `app/schemas/workflow.py`
- **Purpose:** the bodies of the ticket action endpoints. All date-times are `AwareDatetime`, so a time without a timezone is rejected.
- **Models:**

  | Model | Fields |
  |---|---|
  | `AcknowledgeBody` | `eta?`, `no_eta_reason?`, `next_checkpoint_at?` |
  | `AssignBody` | `assignee_id`, `reason?` |
  | `StatusBody` | `status`, `message?` (5 to 5000) |
  | `HoldBody` | `reason`, `review_date` |
  | `EtaBody` | `eta`, `reason` |
  | `PriorityBody` | `priority`, `reason` |
  | `ResolveBody` | `summary` (10 to 2000) |
  | `ConfirmClosureBody` | `rating?` (1 to 5), `comment?` (up to 1000) |
  | `ReasonBody` | `reason` (used by reopen, cancel and close) |
  | `TransferBody` | `department_id`, `category_id?`, `reason` |

  The combination rules (for example "ETA or a reason for having none") are enforced in the workflow services (Part 4).
- **Used by:** `app/services/workflow/*`, router `ticket_workflow`, seed.

#### `app/schemas/audit.py`
- **`AuditEntryOut`:** `id`, `at`, `actor` (`UserRef` or `SystemActor`), `action`, `object_type`, `object_id` (kept even when null), and `old_value`, `new_value`, `reason`, `detail`, each omitted when null.
- **Used by:** `services/audit_reads.py`, router `audit`.

#### `app/schemas/notifications.py`
- **Models:** `NotificationOut` (`id`, `created_at`, `read`, `critical`, `text`, `ticket_id` = ticket number or null, `kind`) and `UnreadCountOut(count)`.
- **Used by:** `services/notifications.py`, router `notifications`.

#### `app/schemas/dashboards.py`
- **Models:**

  | Model | Fields |
  |---|---|
  | `DepartmentHealthOut` | `department_id`, `name`, `on_track`, `warning`, `breached` |
  | `EmployeeDashboardOut` | `open`, `awaiting_my_response`, `resolved_to_confirm`, `closed`, `assigned_to_me`, `assigned_warning`, `assigned_breached`, `recent_updates`, `attention` |
  | `SpokeDashboardOut` | `new_unacknowledged`, `approaching_sla`, `breached`, `stale_or_eta_overdue`, `awaiting_requester`, `on_hold`, `resolved_pending_closure`, `sla_met_pct`, `avg_initial_response_seconds`, `reopen_rate_pct`, `by_department`, `attention` |
  | `AdminDashboardOut` | `open_count`, `breached_count`, `l3_count`, `stale_count`, `pending_approvals`, the same three KPI fields, `by_department`, `attention` |

  `EmployeeDashboardOut` has a `field_serializer` (lines 26-28) that dumps `recent_updates` with `exclude_none=True`, so empty optional timeline fields are dropped.
- **Used by:** `services/dashboards.py`, router `dashboards`.

#### `app/schemas/reports.py`
- **Type:** `AgingBucket` (`0_2`, `3_7`, `8_14`, `15_30`, `31_plus`).
- **Models:**
  - `KpiFiltersOut`: its `from_` field is serialized as `"from"` (a Python keyword);
  - `SlaComplianceOut`, `DurationOut`, `TrendPointOut`, `ReopenOut`, `EscalationCountsOut`, `AgingOut`, `PriorityCountsOut`, `DepartmentKpiOut`, `WorkloadRowOut`, `WorkloadOut`, `CategoryCountOut`;
  - `KpiReportOut`, which combines them all.
- **Note:** percentages are floats or `null` (no data); durations are whole seconds or `null`.
- **Used by:** `services/kpis.py`, `services/exports/tables.py`, router `reports`, `app/queries/kpis.py` (`AgingBucket`).

#### `app/schemas/exports.py`
- **Purpose:** two enums: `ExportType` (`tickets`, `kpis`) and `ExportFormat` (`csv`, `xlsx`, `pdf`).
- **Used by:** `services/exports/*`, router `exports`.

#### `app/schemas/saved_views.py`
- **Constants:** `QUERY_TEXT_MAX_LENGTH = 200`, `ID_MAX_LENGTH = 64`, `ViewName` (2 to 80 characters, trimmed).
- **`TicketListQueryModel`:** every `GET /tickets` filter as an optional field, with `extra="forbid"` so unknown keys are rejected. `app/services/saved_views.py` `normalize_query` validates a saved view's `query` with it (Part 4).
- **Other models:** `SavedViewCreate` (`name`, `query` as raw JSON), `SavedViewUpdate` (`name?`, `query?`) and `SavedViewOut` (`id`, `name`, `built_in`, `query`, `created_at`, `updated_at`; the two timestamps are null for built-in views).
- **Used by:** `services/saved_views.py`, router `saved_views`.

#### `app/schemas/calendar.py` (R2-C1)
- **Types:**
  - `TimeOfDay`: `HH:MM`, 24-hour;
  - `StrictInt`, `ISO_WEEKDAYS`;
  - `DateText`: `YYYY-MM-DD`.
- **Models:**
  - `HolidayOut(date, name)`;
  - `BusinessCalendarOut`: `timezone` is always `Asia/Kolkata`, plus `working_days`, `work_start`, `work_end`, `holidays` and `updated_at` (kept when null);
  - `CalendarBody`;
  - `HolidayBody` (`date` must be a real date, `name` is `OrgName`).
- **`CalendarBody`:** 1 to 7 strict integers. Validator `distinct_days` checks they are within 1 to 7 and distinct, so the error is reported on `working_days` and not on a list index (13.0 #6). That `work_end` comes after `work_start` is checked in the service, so the error lands on `fields.work_end`.
- **Used by:** `services/calendar.py`, router `calendar`.

#### `app/schemas/preferences.py` (R2-C2)
- **Models:**
  - `NotificationPreferencesOut` (`non_critical_email`, `digest_hour`, `critical_email` always `"always"`);
  - `NotificationPreferencesBody` (`extra="forbid"`, so sending `critical_email` is a 422; `digest_hour` is a strict integer 0 to 23).
- **Used by:** `services/preferences.py`, router `preferences`.

### 4.9 Services (`app/services/`)

Services hold the business logic. Every service follows the same pattern, so it is described once here:

- **Construction:** `SomeService(session, clock[, settings, ...])`, created by the router for each request. Many build helper services in `__init__` (for example `AuditService`).
- **Input:** the caller's `Actor` plus already-validated schema values.
- **Checks:** read the current policy (`PolicyService(session).current()`), ask `app/policy` for permission, and raise `ApiError` helpers on failure.
- **Writes:** change ORM objects, call `session.flush()` when ids or constraint checks are needed, write audit rows with `AuditService.record(...)`, and publish domain events. **Never `commit()`**: the request's `get_db` commits after the router returns.
- **Output:** a response schema.
- **Errors that must still save side effects** (failed-login counters, lockout audit rows): the service **returns** the `ApiError` instead of raising it, and the router turns it into a response with `error_response(...)`. Raising would roll back the transaction and lose the counter (`CLAUDE.md` B06). In the code below, a return type such as `LoginGranted | ApiError` marks this case.
- **Row locks:** rows that a concurrent request could change are loaded with `SELECT ... FOR UPDATE` (`with_for_update()`), so two requests cannot both change the same ticket or account at once.

#### 4.9.1 Accounts and identity

##### `app/services/me.py`
- **`MeService(session)`:**
  - `spoke_departments(user_id)`: the user's active Spoke department codes.
  - `actor_for(user)`: builds an `Actor` from a `User` row.
  - `load_active_actor(user_id)`: `None` unless the user exists and is `active`; used by `get_actor` on every authenticated request. This duplicates `app/policy/actors.py` `load_actor` (13.0).
  - `me(actor)`: builds the `Me` response, with `permissions` from `compute_permissions` and the current policy.
- **Tables:** reads `users`, `spoke_assignments`, `policy_versions`.
- **Used by:** `app/api/deps.py`, `services/auth.py`, the `GET /auth/me` route, seed.

##### `app/services/rate_limit.py`
- **Contents:**
  - `RateLimit(name, limit, window)`;
  - rules `LOGIN_PER_IP` and `LOGIN_PER_EMAIL` (10 per minute each), `FORGOT_PER_EMAIL` (3 per hour). The signup rules live in `signup.py`.
  - `window_start(now, window)`: rounds down to the start of the fixed window (epoch seconds modulo the window length).
- **`RateLimiter(session, clock).hit(rule, subject) -> int | None`** (37-54):
  1. Key = `"<rule name>:<sha256(subject)>"`. The email or IP is hashed, so the table never stores it in clear text.
  2. Upsert into `rate_limit_hits`: insert with count 1, or on conflict `count = count + 1`, returning the new count. One atomic statement, safe across processes.
  3. If the count is within the limit, return `None`; otherwise return the seconds until the window ends (at least 1). The caller turns this into 429 `rate_limited` with `details.retry_after_seconds`.
- **Note:** counting happens before the credential check, so failed and successful attempts both count.

##### `app/services/auth.py`
- **Constants:** `MAX_FAILED_LOGINS = 5`, `LOCKOUT_DURATION = 15 min`, `RESET_TOKEN_LIFETIME = 1 h`, `RESET_TEMPLATE = "password_reset"`, `INVALID_RESET_TOKEN`.
- **Result types:** `LoginGranted(body, refresh_token)`, `MfaEnrolGranted`, `RefreshGranted`. The router puts `refresh_token` into the httpOnly cookie and returns `body` as JSON.
- **`AuthService(session, clock, settings)`** builds `AuditService`, `RateLimiter`, `MfaService` and `MeService`.
- **`login(email, password)`** (86-115), returning `LoginGranted | MfaChallenge | ApiError`:
  1. Apply the per-email and per-IP rate limits (`_login_rate_limit`); if exceeded, return 429.
  2. Load the user by email `FOR UPDATE`.
  3. **Unknown email:** run `dummy_verify` (equal timing), audit `login_failed` with the typed email, return 401 `invalid_credentials`.
  4. **Locked** (`locked_until` in the future): return 429 `too_many_attempts` with the retry seconds.
  5. **Wrong password:** `_register_failure` increments `failed_login_count` and audits `login_failed`. On the 5th failure it resets the counter, sets `locked_until = now + 15 min` and audits `account_locked`. Return 401 (the same response as an unknown email: no account enumeration).
  6. **Correct password but account not active:** return 403 `account_state` with the state; for `rejected`, also the latest rejection reason (`_rejection_reason`).
  7. Reset the failure counters.
  8. Ask `MfaService.challenge`. If MFA applies, return `MfaRequired` or `MfaEnrolRequired`, carrying a short-lived MFA token instead of an access token.
  9. Otherwise `_grant`.
- **`_grant(user, actor)`** (245-257), every login-success effect:
  1. Set `last_login_at`.
  2. Audit `login_succeeded`.
  3. Issue a refresh token in a **new family** (`_issue_refresh_token`: random token, stored as a SHA-256 hash with expiry, user agent and IP).
  4. Create the access token.
  5. Return `LoginSuccess` with `Me`.
- **`mfa_setup`, `mfa_confirm`, `mfa_verify`:** delegate to `MfaService`. A successful confirm or verify also runs `_grant`; confirm additionally returns the recovery codes.
- **`refresh(raw_token)`** (137-170), refresh-token rotation:
  1. No cookie: 401.
  2. Find the token by hash, `FOR UPDATE`; unknown: 401.
  3. **Already revoked:** if it was *replaced* (rotated), someone is reusing an old token, possibly a thief. Revoke the whole family and audit `refresh_reuse_detected`. Return 401 either way.
  4. Expired: 401.
  5. User missing or not active: revoke the family, 401.
  6. Issue a replacement in the **same family**, mark the old one revoked with `replaced_by_id`, and return a new access token plus the new raw refresh token.
- **`logout(raw_token)`:** revokes the token's family and audits `logout`. Silently does nothing when there is no token or it is already revoked.
- **`forgot_password(email)`:**
  1. Rate limit 3 per hour per email.
  2. For an unknown or inactive user, return `None`: the router still answers 202 (no enumeration).
  3. Otherwise create an `email_tokens` row (purpose `reset`, 1 hour) and queue the reset email through `_enqueue_reset_email`.
- **`reset_password(raw_token, password)`:**
  1. Unknown or used token: 422 `fields.token`.
  2. Expired: 410 `token_expired`.
  3. Weak password: 422 `fields.password`.
  4. User not active: 422.
  5. Otherwise set the new hash, clear lockout, mark the token used, **revoke all the user's refresh tokens** (logs out every device) and audit `password_reset`.
- **`_enqueue_reset_email(user, raw_token)`:** `enqueue_email(..., "password_reset", {name, token, expires_minutes})`, so the email is rendered from `app/templates/email/password_reset.*.j2` like every other email (13.0 #9, fixed). The link is `<FRONTEND_BASE_URL>/reset-password?token=<raw token>`.
- **Tables:** `users`, `refresh_tokens`, `email_tokens`, `signup_requests` (rejection reason), `email_outbox`, `audit_log`, `rate_limit_hits`.

##### `app/services/mfa.py`
- **Constants:** `MFA_PURPOSE = "mfa"`, `MFA_TOKEN_LIFETIME = 5 min`, required claims (`sub`, `aud`, `purpose`, `iat`, `exp`), `MFA_ISSUER = "Ibotix Helpdesk"`, `MAX_FAILED_MFA = 5`, `MFA_LOCKOUT = 15 min`, `TOTP_WINDOW = 1` (one 30-second step either side), `TOTP_DIGITS = 6`, `RECOVERY_CODE_COUNT = 8`.
- **Module functions:**
  - `create_mfa_token` and `decode_mfa_token`: an HS256 JWT with `aud` and `purpose` both `mfa` and **no `jti`**. Because `decode_access_token` requires `jti` and this decoder requires `aud=mfa`, an MFA token can never be used as an access token, and the reverse (`CLAUDE.md` B21).
  - `mfa_required_for(actor, settings)`: true if any of the actor's roles is in `MFA_REQUIRED_ROLES`.
  - `_new_recovery_code()`: `xxxxxxxx-xxxxxxxx` (hex).
  - `_normalize(code)`: removes spaces and lower-cases.
- **`MfaService` methods:**
  - `challenge(user, actor)`: `None` when MFA is off. `MfaRequired` when the user already has MFA; `MfaEnrolRequired` when their role requires MFA but they have not enrolled; otherwise `None`.
  - `setup(token)`: needs a valid MFA token (`_token_user`) and MFA not yet enabled (409 otherwise). Generates a base32 secret, stores it **encrypted with Fernet** (`FIELD_ENCRYPTION_KEY`), and returns the secret and an `otpauth://` URI for authenticator apps.
  - `confirm(token, code)`: the setup must have been started (409 otherwise). A wrong code gives 422 `fields.code`. On success: retire any old recovery codes, create 8 new ones (stored as SHA-256 hashes), set `mfa_enabled`, audit `mfa_enabled`, and return the plain codes (shown once).
  - `verify(token, code)` returns `User | ApiError`: 409 if MFA is not enabled; 429 if locked. Accepts a matching TOTP code **or** an unused recovery code (which is then marked used and audited `mfa_recovery_code_used`). Failures go to `_register_failure`: audit `mfa_failed`, and on the 5th failure lock for 15 minutes (audit `account_locked`, 429). It uses the same `locked_until` column as password lockout.
  - `reset(email)`: CLI only (`python -m app.cli mfa-reset`). Clears the secret and codes and audits `mfa_reset`.
  - `_token_user(token)`: **404** when MFA is switched off (the MFA endpoints then "do not exist"); 401 for a bad token or an inactive user.
  - `_fernet()`: raises `RuntimeError` if `FIELD_ENCRYPTION_KEY` is empty, so a misconfiguration fails loudly with a 500.
- **Tables:** `users`, `mfa_recovery_codes`, `audit_log`.
- **External:** `pyotp`, `cryptography.fernet`, PyJWT.

##### `app/services/signup.py`
- **Constants:** `VERIFY_TOKEN_LIFETIME = 24 h`; rules `SIGNUP_PER_IP` and `SIGNUP_PER_EMAIL` (5 per hour each) and `RESEND_PER_EMAIL` (3 per hour); messages `SIGNUP_MESSAGE`, `INVALID_VERIFY_TOKEN`, `INACTIVE_DEPARTMENT`, `WRONG_PASSWORD`.
- **`SignupService(session, clock, settings)`:**
  - **`signup(body)`** (79-138):
    1. Check the email domain, then password strength, then that the requested department exists and is active. Each failure is a 422 with the field name.
    2. Apply the rate limits (429).
    3. If the email already exists: resend verification if still `pending_verification`; otherwise send an `account_exists_notice` email. Respond exactly as for a new signup (no enumeration).
    4. New user: create `users` (state `pending_verification`, global role `employee`, home department = requested department) and a `pending` `signup_requests` row; audit `signup_requested`.
    5. `_issue_verification`: invalidate old verify tokens, create a new one (24 h) and queue the `verify_email` email with the raw token.
  - **`verify_email(raw_token)`** (140-177): token checks as in `reset_password` (422, 410). The user must be `pending_verification` with a pending request. Mark the token used, set `email_verified_at`, move the state to `pending_approval`, audit `email_verified`, and publish `SignupVerified` (approvers are notified, 4.9.6).
  - **`resend_verification(email)`:** rate limit, then re-issue only for `pending_verification` users. Always the same response.
  - **`reapply(body)`** (191-239), for previously rejected users:
    1. Check domain and department.
    2. Unknown email: dummy hash, then the same 403 as a wrong password.
    3. Locked: 429.
    4. Wrong password: failure counter shared with login (audit `reapply_failed`, lockout after 5), 403 with `fields.password`.
    5. Not `rejected`: 409.
    6. Otherwise create a new pending request, update the home department, set state `pending_approval`, audit `signup_reapplied`, and publish `SignupVerified`.
  - **`list_requests(actor, status, page)`:** needs `users.approve_employee`. Lists requests except pending ones whose user has not verified yet; newest first; paged. `can_approve` is computed per row.
  - **`approve(actor, request_id, body)`** (270-313):
    1. Needs approver rights, then `can_decide_signup` with the requested **and** the approved role (403). An Admin cannot approve an `admin` signup, nor approve an employee request *as* admin.
    2. The request must be pending and the user `pending_approval` (409 otherwise).
    3. The approved department must exist and be active.
    4. Activate the user with the approved role and department; set `approved_by`.
    5. Close the request as `approved`.
    6. Email `signup_approved`.
    7. Audit `signup_approved` (security limited, because it grants roles).
    8. Publish `SignupDecided`.
  - **`reject(actor, request_id, reason)`:** the same checks. Sets the user to `rejected`, stores the reason, emails `signup_rejected` with the reason, audits `signup_rejected` and publishes `SignupDecided`.
- **Helpers:** `_check_domain`, `_check_department`, `_signup_rate_limit`, `_issue_verification`, `_wrong_password` (a 403 with a field error), `_register_failure`, `_pending_request`, `_require_approver`, `_load_for_decision` (a bad UUID or unknown id gives 404), `_ensure_decidable`, `_users`, and `_to_out`.
- **Tables:** `users`, `signup_requests`, `email_tokens`, `departments`, `email_outbox`, `audit_log`, `rate_limit_hits`.

##### `app/services/spokes.py`
- **Module functions:**
  - `user_ref(user)`: `User` to `UserRef`. Used widely; a private copy also exists in `signup.py` (`_user_ref`).
  - `active_spoke_of(department_id)` and `any_active_spoke()`: EXISTS clauses on `spoke_assignments`.
  - `department_member(department_id)`: home department **or** active Spoke of it. "Members" are who can be assigned tickets in a department.
- **`SpokeService(session, clock)`:**
  - `active_departments(user_ids)`: a map from user id to Spoke departments (one query for many users).
  - `members(department_id)`: active members, sorted by name.
  - `replace(user, department_ids, actor_id, reason)` (66-99):
    1. Lock the current assignments.
    2. Revoke those not wanted and insert the new ones.
    3. Audit `spoke_mapping_added` or `spoke_mapping_revoked` per department, with the reason.
    4. Return `(added, revoked)`.
  - `revoke_all(user_id, actor_id)`: revokes every active mapping (used on deactivation), without its own audit rows; the deactivation audit lists them.
- **Tables:** `spoke_assignments`, `users`, `audit_log`.

##### `app/services/users.py`
- **Constants:** `LOOKUP_MIN_LENGTH = 2`, `LOOKUP_LIMIT = 20`, `STAFF_ROLES`.
- **`UserService(session, clock)`:**
  - **`list_users(actor, q, role, state, department_id, page)`:** needs `can_list_users`. Hides `pending_verification` users. `q` matches name or email (ILIKE, escaped by its own `_escape`, the third copy of this helper). `role=spoke` means "has an active Spoke mapping"; `department_id` uses `department_member`.
  - **`lookup(q)`:** any authenticated user. At least 2 characters (422), at most 20 active users by name or email. Used for pickers, for example adding a collaborator.
  - **`department_members(department_id)`:** 404 for an unknown department, otherwise the members.
  - **`update_roles(actor, user_id, spoke_departments, reason)`:**
    1. `can_manage_account` (403).
    2. Unknown departments give 422 `fields.spoke_departments`.
    3. Lock the user; must be `active` (409).
    4. `SpokeService.replace`.
  - **`deactivate(actor, user_id, reason)`** (128-149):
    1. `can_change_account_state` (403); must be `active` (409).
    2. **Super Admin target:** create a protected-action request instead (`ProtectedActionService.request`) and return `result = protected_request_created`.
    3. Otherwise lock the row, re-check authority and state (409 "This account changed, try again" if it changed meanwhile) and run `AccountEffects.deactivate`.
  - **`activate(actor, user_id)`:** only for `deactivated` users that were once approved (409 otherwise). Clears the deactivation fields and audits `user_activated` with the old reason.
  - **`list_admins`, `promote_admin` (active employees only, audit `admin_promoted`), `demote_admin`:**
    - All need `admins.manage`.
    - `demote_admin` on a Super Admin gives 409 `protected_action_blocked`: that needs a protected action.
    - On an Admin, demotion to employee is audited `admin_demoted`. Both role audits are security limited.
  - **`list_item(s)`, `_to_item`:** build `UserListItem`; `roles` are computed by building a temporary `Actor`.
  - **Helpers:** `_load` (bad UUID, unknown or pending-verification user all give 404) and `_lock` (`session.refresh(user, with_for_update=True)`).
- **Tables:** `users`, `spoke_assignments`, `departments`, `audit_log`, plus everything `AccountEffects` touches.

##### `app/services/protected_actions.py`
- **Constants:** `PROTECTED_ACTION_LIFETIME = 72 h`, `CLOSED_TICKET_STATUSES`, messages.
- **`AccountEffects(session, clock)`**, the side effects of deactivating any account:
  - `open_ticket_count(user_id)`: tickets where the user is owner or assignee and the status is not resolved, closed or cancelled. It **includes confidential tickets**; this count is shown to the person deactivating (an open question in `CLAUDE.md` B09; see 13.0).
  - `deactivate(user, actor_id, reason)` (67-113):
    1. Set the state to `deactivated` with who, when and why.
    2. Revoke all refresh tokens (the user is logged out).
    3. Revoke all Spoke mappings.
    4. Clear the user as escalation contact on every department.
    5. Audit `user_deactivated` (old state, revoked Spoke departments, open ticket count, cleared departments).
    6. Publish `UserDeactivated` (admins are notified about open tickets).
    7. Return the count.
- **`ProtectedActionService(session, clock)`:**
  - `list_actions(actor, status, page)`: needs `superadmins.protect`; newest first; `can_decide` per row.
  - `create(...)`: parses the target id (422 for a bad one), then `request`.
  - **`request(actor, kind, target_id, reason)`** (152-202):
    1. Needs `superadmins.protect`.
    2. Lock **all active Super Admin rows**, ordered by id so that concurrent requests lock in the same order and cannot deadlock.
    3. The target must be another active Super Admin (422).
    4. No duplicate pending request of the same kind for the target (409).
    5. After removal at least 2 must remain (409 `protected_action_blocked`).
    6. Insert the request (expires in 72 h), audit `protected_action_requested` (security limited) and publish `ProtectedActionRequested`.
  - **`approve(actor, action_id)`** (204-238):
    1. `_load_for_decision`: locks the request; 404 if unknown; 403 unless an independent Super Admin; 409 if already decided or expired.
    2. Lock the Super Admins again and re-check that the target is still one and that the minimum still holds. This protects against two approvals racing.
    3. Then either `AccountEffects.deactivate(target)` or demote the target to `admin`.
    4. Mark the request approved, audit `protected_action_approved` and publish `ProtectedActionDecided`.
  - `reject(actor, action_id, reason)`: the same load checks; marks it rejected with the reason; audit and event.
- **Tables:** `protected_action_requests`, `users`, `refresh_tokens`, `spoke_assignments`, `departments`, `tickets` (count only), `audit_log`.

#### 4.9.2 Organisation, policy and platform services

##### `app/services/audit.py`
- **`format_utc(value)`:** an aware datetime as ISO 8601 UTC with a `Z` suffix; raises for naive values.
- **`to_json_value(value)`** (24-54): turns any Python value into JSON-safe data for the `old_value` and `new_value` JSONB columns:
  - enums become their values;
  - non-finite floats are rejected;
  - `Decimal` becomes a string;
  - datetimes become `format_utc`, dates ISO strings, UUIDs strings;
  - Pydantic models are dumped, dataclasses become dicts;
  - mappings are processed recursively;
  - sets are sorted (stable output);
  - anything else raises `TypeError`, so a bad audit value fails the request rather than being stored wrongly.
- **`AuditService(session, clock).record(*, action, object_type, object_id=None, actor_id=None, old_value=None, new_value=None, reason=None, detail=None, ticket_id=None, department_id=None, is_security_limited=False, is_confidential_ticket=False) -> AuditLog`** (62-98):
  - Adds one `audit_log` row: the client IP and user agent come from the request context (null in the worker and CLI); `created_at` comes from the clock.
  - Then flushes.
  - It is the only writer of `audit_log` (6.4); about 17 services call it.

##### `app/services/audit_reads.py`
- **`parse_actor_id(value)`:** an empty value is no filter; an invalid UUID gives 422 `fields.actor_id`.
- **`AuditReadService(session).list_entries(actor, params, *, q, actor_id, action, ticket_id, created_from, created_to)`:**
  1. Needs `audit.view_all` (403).
  2. Build `AuditFilters`; `ticket_id` is the ticket number.
  3. Page through `audit_statement(actor, filters)`, which applies the Admin scope of 4.7.
  4. Batch-load the actor users.
  5. `_entry_out` shows the `SystemActor` when `actor_id` is null.
- **Tables:** reads `audit_log`, `tickets`, `users`.

##### `app/services/policy.py`
- **`PolicyConfig`** (frozen Pydantic model): every policy key (4.5). It is the response model of `GET`/`PUT /policy` and is passed around as the "current rules".
- **`PolicyService(session)`:**
  - `current_version()`: the highest `policy_versions` row; raises `LookupError` if none (the migration always seeds version 1).
  - `current()`: its `config` validated as `PolicyConfig`.
  - `public_config(settings)`: `PublicConfig`, with allowed email domains, active departments sorted by name, upload limits from settings, `PASSWORD_MIN_LENGTH`, and the policy's `initial_response_hours` as `first_response_hours`. Served without authentication by `GET /public/config`.
- **Used by:** nearly every service, the SLA handlers, the scanner and jobs.

##### `app/services/policy_admin.py`
- **Constants:** `POLICY_LOCK_KEY = 410_001` (an advisory-lock number) and `ALL_PRIORITIES`.
- **`policy_errors(body)`:** the cross-field rules.
  - Every priority must be present in `warning_hours` and in `l3_hours`.
  - Each warning value must be below `initial_response_hours`, and each L3 value above it.
  - `update_warning_hours` must be below `update_cadence_hours`.

  It returns `{field: message}`. Since R2-C1 it no longer rejects `sla_mode = business`.
- **`PolicyAdminService(session, clock)`:**
  - `read(actor)`: Admin or Super Admin (`can_read_policy`), else 403.
  - **`replace(actor, body)`:**
    1. `can_manage_policy` (Super Admin), else 403.
    2. Validate with `policy_errors` (422).
    3. Take `pg_advisory_xact_lock(410001)` so concurrent edits are serialised.
    4. Re-read the latest version and insert `version + 1`. Rows are never updated.
    5. Audit `policy_updated` with the old and new configs.
- **Tables:** `policy_versions`, `audit_log`.

##### `app/services/departments.py`
- **Constants:** field names and messages for Spoke and contact errors.
- **`DepartmentService(session, clock)`:**
  - **`list_departments(actor)`:** everyone sees active departments; managers (`can_manage_departments`) also see inactive ones. Sorted by name.
  - **`create(actor, department_id, name)`:**
    1. Manager only.
    2. A duplicate code gives 409.
    3. The new department starts **inactive**.
    4. Audit `department_created`.
  - **`update(actor, department_id, name, active, basis=None)`:**
    1. Manager only; lock the row (404 if unknown).
    2. Rename if changed.
    3. Activating requires at least one active Spoke (409).
    4. Changed fields are audited together as `department_updated`.
    5. A changed `sla_mode` is audited separately as `sla_basis_changed` (R2-C1).
  - **`add_spoke(actor, department_id, user_id)`:** the user must be active (422 `fields.user_id`); an already active mapping gives 409. Inserts the mapping and audits `spoke_mapping_added` (no reason, `CLAUDE.md` B10).
  - **`remove_spoke(actor, department_id, user_id)`:** a bad id or no active mapping gives 404. Revokes it and audits `spoke_mapping_revoked`.
  - **`set_escalation_contact(actor, department_id, contact_id)`:** the contact must be an active **member** of the department (home department or Spoke), else 422 `fields.contact_id`; `null` clears it. Audits `escalation_contact_changed`.
  - **`one`, `to_out(departments)`:** build `DepartmentOut` for many departments with batched queries for Spokes (active mappings of active users only), categories and contacts. `accepts_tickets` = active **and** has at least one such Spoke.
- **Tables:** `departments`, `spoke_assignments`, `categories`, `users`, `policy_versions`, `audit_log`.

##### `app/services/categories.py`
- **`category_out(category)`:** `Category` to `CategoryOut` (including `sla_mode`).
- **`CategoryService(session, clock)`:**
  - `create(actor, department_id, name, confidential)`: manager only; locks the department (404 if unknown); the name must be unique in the department ignoring case (409); audits `category_created`.
  - `update(actor, category_id, name, active, confidential, basis=None)`: manager only; a bad id or unknown category gives 404; uniqueness is re-checked on rename. Changes are audited as `category_updated`; `sla_mode` changes as `sla_basis_changed`.
  - `deactivate(actor, category_id)`: sets `is_active = false` (soft delete) and audits `category_deactivated`. Calling it again is a no-op.
- **Note:** changing `confidential` does not update existing tickets' `confidential` flag (`CLAUDE.md` B10 open question; 13.0).
- **Tables:** `categories`, `departments`, `audit_log`.

##### `app/services/confidential_grants.py`
- **`ConfidentialGrantService(session, clock)`**, Super Admin only (`can_manage_grants`) for every method:
  - `list_grants(actor, category_id, user_id)`: active grants, newest first, optional filters (bad ids give 422).
  - `create(actor, user_id, category_id)`: the user must be active and the category active **and confidential** (422 otherwise); a duplicate active grant gives 409. Inserts the grant, audits `confidential_grant_added` (security limited) and publishes `ConfidentialGrantChanged` (the user is notified).
  - `revoke(actor, grant_id)`: unknown or already revoked gives 404. Sets `revoked_at`, audits `confidential_grant_revoked` and publishes the event.
- **Tables:** `confidential_grants`, `categories`, `users`, `audit_log`.

##### `app/services/calendar.py` (R2-C1)
- **Constants:** `TIMEZONE = "Asia/Kolkata"`, `DUPLICATE_HOLIDAY`.
- **Module functions:**
  - `time_text(value)`: `HH:MM`.
  - `resolve_sla_mode(category, department, policy)`: the first non-null override wins (category, then department), else the policy mode.
  - `ticket_sla_mode(session, ticket, policy)`: loads the ticket's department and category and resolves the mode.
  - `active_holidays(session)`: holidays not removed, by date.
  - `load_working_calendar(session) -> WorkingCalendar`: the stored row plus active holidays, or the defaults (Monday to Friday, 09:00 to 18:00) when no row exists.
- **`CalendarService(session, clock)`:**
  - `read(actor)`: Admin or Super Admin.
  - **`update(actor, body)`:**
    1. Super Admin.
    2. `work_end` must be after `work_start` (422 `fields.work_end`).
    3. Lock the single row, creating it first if missing with `INSERT ... ON CONFLICT DO NOTHING` (`_lock`).
    4. Only if something changed: save, set `updated_at` and `updated_by`, and audit `business_calendar_updated` with old and new values.
  - `add_holiday(actor, body)`: Super Admin; lock the row; an active holiday on that date gives 409. Inserts the holiday, touches the calendar and audits `holiday_added`.
  - `remove_holiday(actor, holiday_date)`: Super Admin; an invalid date text or no active holiday gives 404. Soft-deletes it and audits `holiday_removed`.
- **Effect on SLAs:** changes apply only to timers started afterwards; existing due times never move (Appendix R.14).
- **Tables:** `business_calendar`, `holidays`, `departments`, `categories`, `audit_log`.

##### `app/services/preferences.py` (R2-C2)
- **`EmailPreference(non_critical_email=immediate, digest_hour=9)`:** the defaults when there is no row.
- **Functions:**
  - `email_preference(session, user_id)`: the stored row or the defaults.
  - `preferences_out(preference)`: always adds `critical_email = "always"`.
- **`PreferenceService(session, clock)`:**
  - `read(actor)`: the caller's own preferences.
  - `replace(actor, body)`: an upsert (`INSERT ... ON CONFLICT (user_id) DO UPDATE`), so concurrent first saves are safe. Not audited (a personal setting).
- **Used by:** router `preferences`; `services/notifications.py` (`email_preference`).

##### `app/services/email_templates.py`
- **Contents:**
  - `TEMPLATE_DIR = app/templates/email`;
  - `SUBJECTS`: subjects of the five account emails (`verify_email`, `account_exists_notice`, `signup_approved`, `signup_rejected`, `password_reset`);
  - `NOTIFICATION_SUBJECTS`: 23 notification kinds (`ticket_created` to `notification_digest`);
  - a Jinja2 `Environment` (autoescape for `.html.j2` only, `StrictUndefined` so a missing variable is an error, not an empty string);
  - `UnknownEmailTemplateError`, `RenderedEmail`.
- **`render_email(template, context)`:** looks up the subject (unknown template raises) and renders `<template>.txt.j2` and `<template>.html.j2`.
- **Used by:** `email_outbox.py`. `tests/unit/test_email_masking.py` requires a test case for every notification subject.

##### `app/services/email_outbox.py`
- **`enqueue_email(session, clock, to, template, context, notification_id=None) -> EmailOutbox`:**
  1. Render the template with `context` plus `frontend_base_url` (from `get_settings()`, trailing slash removed). The email is rendered **now**, inside the request, so a template error fails the request.
  2. Insert a `pending` outbox row with `next_attempt_at = now`.
  3. Flush.
- **Used by:** signup, notifications (`Notifier`), the digest job. Not by `AuthService` (13.0 #9).

#### 4.9.3 Tickets: creation, reading, attachments, comments, collaborators

##### `app/services/ticket_numbers.py`
- **`TicketNumberService(session).next_number(department_code, now)`:**
  1. `year` = the IST year of `now`.
  2. Upsert `ticket_counters`: insert `last_value = 1`, or on conflict `last_value + 1`, returning the new value.
  3. Return `format_ticket_no(code, year, value)`, for example `IBX-IT-2026-000017`.
- **Why an upsert:** it is atomic, so two simultaneous ticket creations in the same department can never get the same number (`tests/integration/test_ticket_numbers.py`).
- **Note:** numbering restarts at 000001 each IST year per department. The counter row stays locked until the request commits, so creations in the same department are serialised.

##### `app/services/tickets.py`
- **`TicketService(session, clock, settings).create(actor, body) -> TicketOut`** (37-97):
  1. `_accepting_department`: the department must exist, be active and have at least one **active Spoke who is an active user**; else 422 `fields.department_id` "This department is not accepting tickets".
  2. `_category`:
     - with no category given, if the department has any active category the request fails (422 "Choose a category");
     - a bad id, or a category from another department or inactive, gives 422.
  3. `_attachments`: ids must be unique, at most `MAX_FILES_PER_TICKET`, and each must be the **caller's own, unlinked, not infected** upload, locked `FOR UPDATE`. Anything else gives 422 `fields.attachment_ids`.
  4. `confidential` = the requester asked for it **or** the category is confidential.
  5. Insert the ticket:
     - the number comes from `TicketNumberService`;
     - status `new`, `sla_started_at = now`, requested and current priority equal.
  6. Link the attachments (set `ticket_id`).
  7. Add a public timeline event, action `created`.
  8. Audit `ticket_created` (with `is_confidential_ticket`).
  9. Publish `TicketCreated`. The SLA handler starts the initial-response timer, and the notification handler notifies the department's Spokes (4.9.6).
  10. Return the ticket presented for the caller.
- **Tables:** `departments`, `spoke_assignments`, `users`, `categories`, `attachments`, `ticket_counters`, `tickets`, `ticket_events`, `audit_log`, plus whatever the handlers write.

##### `app/services/attachments.py`
- **Constants:**
  - `STORAGE_HINT = "attachments"`;
  - `MAX_NAME_LENGTH = 150`, `DEFAULT_NAME = "attachment"`;
  - `OOXML_TYPES` (DOCX, XLSX), `TEXT_TYPES` (`text/plain`, `text/csv`).
- **Module functions:**
  - `_is_utf8_text(content)`: no NUL byte and valid UTF-8.
  - `SNIFFERS`: content checks per MIME type. PDF starts with `%PDF-`; PNG with `\x89PNG`; JPEG with `FF D8 FF`; DOCX and XLSX (zip) with `PK\x03\x04`; text must be UTF-8.
  - `normalize_content_type(declared)`: drops `;charset=...` and lower-cases.
  - `content_matches(type, content)`: `False` when there is no sniffer for that type.
  - `sanitize_file_name(raw)`:
    1. Keep only the last path component.
    2. Remove control characters.
    3. Strip leading dots (no hidden files like `.htaccess`).
    4. An empty result becomes `attachment`.
    5. Shorten to 150 characters, keeping the extension.
  - `Download(attachment, stream)`.
- **`AttachmentService(session, clock, settings, storage, scanner)`:**
  - **`upload(actor, file_name, declared_type, stream)`** (107-140):
    1. Read up to `limit + 1` bytes; more than the limit gives 413 `file_too_large`.
    2. The type must be in `ALLOWED_CONTENT_TYPES` **and** the content must match it; else 415 `unsupported_file_type`.
    3. The caller may hold at most `MAX_FILES_PER_TICKET` unlinked uploads (422 `fields.file`).
    4. Save the bytes with `storage.save` under a random key.
    5. Insert the `attachments` row with the sanitised name, size, SHA-256 and the scanner result (`NoopScanner` always gives `clean`).
    6. Return `AttachmentOut`.

    The upload is not tied to a ticket yet: it is linked when the ticket is created with `attachment_ids`.
  - `unlinked_count(user_id)`: the caller's unlinked uploads.
  - **`download(actor, attachment_id)`:** `_downloadable` checks access. A download of a confidential ticket's file is audited `attachment_downloaded`. Returns the storage stream.
  - **`_downloadable`:** a bad id, an unknown file or one not `clean` gives 404. An unlinked file is downloadable only by its uploader (404 for anyone else). A linked file requires `can_view_ticket`, otherwise the same 404, so a file never reveals that a hidden ticket exists.
- **Edge case:** the file is written to disk before the row is saved. If inserting the row fails, `upload` deletes the file again (13.0 #20, fixed). Only a failure of the final commit after the route returns can still leave a file without a row. The scan now runs **before** the file is written.
- **Tables:** `attachments`, `tickets`, `audit_log`. **External:** storage and scanner adapters.

##### `app/services/ticket_reads.py`
- **Constants:**
  - `STAFF_CLASSES = {team, assignee}`;
  - `OPEN_STATUSES`: everything except resolved, closed and cancelled. The pseudo-status `open` expands to this set.
- **`TicketListQuery`** (frozen dataclass): the parsed list query: scope (default `mine`), `q`, statuses as raw strings, priorities, and the remaining filters plus `sort`.
- **Module functions:**
  - `parse_statuses(values)`: `open` expands as above; an unknown status gives 422 `fields.status`.
  - `parse_uuid(value, field)`: blank means `None`; an invalid UUID gives 422.
- **`TicketPresenter(session, clock)`** turns tickets into `TicketOut` with a **fixed number of queries for any page size** (`CLAUDE.md` B13):
  - `present(actor, tickets)` (118-156):
    1. One query each for: the current policy, collaborators of all the tickets, the caller's grants on their categories, the caller's escalation-contact departments, all referenced users, categories, attachments and SLA timers.
    2. Then, per ticket in Python: `relationship_from` → `ActorContext` → `_ticket_out`.
  - `_ticket_out(...)`:
    - `hold` is included only when the status is `on_hold` and both hold fields are set;
    - `feedback` only when a rating or comment exists;
    - `sla` = `build_sla_state(ticket, timers)` (4.9.5);
    - `allowed_actions` = `compute_allowed_actions(ctx, ticket, policy, now)`.
  - `present_one`, `context(actor, ticket)` and `contexts(actor, tickets)`: contexts only, used by the workflow and timeline code.
- **`attachment_out(attachment)`:** `Attachment` to `AttachmentOut`.
- **`TicketReadService(session, clock)`:**
  - **`load_visible(actor, ticket_no, for_update=False)`:** selects the ticket by number **through the visibility clause** and, with `for_update`, locks it (`FOR UPDATE OF tickets`). Missing or invisible gives 404 `not_found`. `CLAUDE.md` requires every ticket mutation to load the ticket this way.
  - `get_ticket(actor, ticket_no)`: `load_visible` plus `present_one`.
  - `list_tickets(actor, query, params)`: validate the sort (422), build filters, run `ticket_list_statement`, page it, and present the page.
  - **`filters(actor, query)`** (328-370), scope rules:

    | Scope | Clause | Rule |
    |---|---|---|
    | `mine` | `mine_clause` (requester or collaborator) | anyone |
    | `assigned` | assignee = me | anyone |
    | `queue` | the caller's Spoke departments, or one of them via `department_id` | non-Spokes get 403; a department the caller is not a Spoke of gets 403 |
    | `all` | no extra clause | needs `tickets.view_all` (403 otherwise) |

    `escalation_level` outside 0 to 3 gives 422. Visibility is always applied on top, by `ticket_list_statement`.
  - **`timeline(actor, ticket_no)`** (372-393):
    1. `load_visible` (404).
    2. **Staff** = actor class `team` or `assignee`. Staff see every event; others see only `is_public` events.
    3. Batch-load the actors.
    4. `_event_out`: non-staff see `public_detail` instead of `detail` when one exists. A null actor becomes `SystemActor`.
- **Tables:** read-only on `tickets`, `ticket_collaborators`, `confidential_grants`, `departments`, `users`, `categories`, `attachments`, `sla_timers`, `ticket_events`, `policy_versions`.

##### `app/services/comments.py`
- **`CommentService(session, clock).add(actor, ticket_no, body) -> TimelineEventOut`** (37-85):
  1. The action is `internal_note` if `body.internal`, else `comment`.
  2. `Workflow.begin` locks the visible ticket and checks the action is allowed (404, 403 or 409; 4.9.4). Internal notes are allowed only for team and assignee.
  3. Insert a `ticket_events` row of kind `comment` or `internal_note`, public unless internal, and bump `updated_at`.
  4. If the author is team or assignee, set `last_team_update_at`. This counts as a progress update for the SLA.
  5. **Requester replies to an `awaiting_requester` ticket** with a public comment: `_resume` moves the status back to `in_progress`, clears `awaiting_since`, and records a **system** (actor null) public `status_changed` timeline event plus audit `ticket_status_changed`. It queues a `TicketStatusChanged` event.
  6. Publish, in order: the optional `TicketStatusChanged`, then `CommentAdded`, then `TeamUpdateRecorded` for team comments.
  7. Return the new timeline entry.
- **Note:** comments themselves are **not** written to `audit_log`; the timeline is their record.
- **Tables:** `ticket_events`, `tickets`, `users`, `audit_log` (only when the status changes).

##### `app/services/collaborators.py`
- **`CollaboratorService(session, clock)`:**
  - **`add(actor, ticket_no, body)`:**
    1. `Workflow.begin` with `manage_collaborators` (team only).
    2. The target must be an active user (422 `fields.user_id`) and not the requester (422).
    3. An existing collaborator gives 409.
    4. Insert the `ticket_collaborators` row, then `_record`.
    5. Return the ticket (`Workflow.respond`).
  - **`remove(actor, ticket_no, user_id)`:** same check. A bad id, or a user who is not a collaborator, gives 404. Deletes the row, then `_record`.
  - **`_record`:** a **non-public** timeline event (`collaborator_added` or `collaborator_removed`); audit `ticket_collaborator_added` or `_removed`, security limited when the ticket is confidential; publish `CollaboratorChanged`.
- **Effect:** collaborators can always see the ticket, even a confidential one, without a grant (`is_visible`). Only people who can already see the ticket as team can add them.
- **Tables:** `ticket_collaborators`, `ticket_events`, `tickets`, `users`, `audit_log`.

#### 4.9.4 Ticket workflow (`app/services/workflow/`)

Every lifecycle action goes through the same skeleton, `Workflow`, so each one locks, authorises, records and notifies in the same way.

##### `app/services/workflow/common.py`
- **Constants and helpers:**
  - `TICKET_OBJECT = "ticket"`;
  - `TIME_FORMAT = "%d %b %Y, %H:%M IST"` with `format_time(value)` (IST text used in timeline details);
  - `status_label(status)`: `in_progress` becomes `in progress`;
  - `event_data(**values)`: the values made JSON-safe with `to_json_value`, for `ticket_events.data`.
- **`TimelineEntry(action, detail, public, public_detail=None, data=None)`** and **`AuditEntry(action, old_value=None, new_value=None, reason=None)`:** frozen dataclasses describing what to record.
- **`Workflow(session, clock)`:**

  | Method | What it does |
  |---|---|
  | `policy()` | the current `PolicyConfig` |
  | `lock(actor, ticket_no)` | `TicketReadService.load_visible(..., for_update=True)`: 404 if missing or invisible, otherwise the ticket row locked until commit |
  | `context(actor, ticket)` | the `ActorContext` (via `TicketPresenter.context`) |
  | `is_allowed`, `denial`, `authorize` | `is_action_allowed`; `classify_denial` turned into `ApiError` 403 or 409; raise if not allowed |
  | **`begin(actor, ticket_no, action)`** | `lock`, then `context`, then `now`, then `authorize`. Returns `(ticket, ctx, now)`. The standard first line of every action. |
  | **`record(ticket, actor_id, now, timeline, audit)`** | inserts one `ticket_events` row (kind `audit`, with action, detail, public detail, public flag, data), bumps `ticket.updated_at`, and writes the matching `audit_log` row (object `ticket`, object id = ticket number, department, `is_confidential_ticket`) |
  | `add_comment(ticket, actor_id, now, body)` | a public comment event (used by "ask requester") |
  | `publish(*events)` | flushes, then publishes each event in order. **Handlers run here, inside the transaction**, so timers and notifications see the new state. |
  | `respond(actor, ticket)` | flush, then present the ticket for the actor |

- **Rule recorded in `CLAUDE.md` B12:** services must set every ticket field **before** publishing, because handlers read the ticket.

##### `app/services/workflow/progress.py`
- **Constants:**
  - `FUTURE`;
  - `START_STATUSES` (acknowledged, assigned, reopened);
  - `RESUME_STATUSES` (awaiting requester, on hold);
  - `ASSIGN_MOVES_TO_ASSIGNED` (acknowledged, reopened);
  - `STATUS_TARGETS` (`in_progress`, `awaiting_requester`).
- **`ProgressService(session, clock)` methods:**
  - **`acknowledge(actor, ticket_no, body)`** (57-96):
    1. `begin(..., acknowledge)`: team, status `new`.
    2. **ETA given:** it must be in the future (422 `fields.eta`); store it and clear the checkpoint.
    3. **No ETA:** `_checkpoint` requires both `no_eta_reason` and a future `next_checkpoint_at`; each missing or past field becomes its own 422 field error.
    4. Set the caller as **owner**, the status to `acknowledged`, `acknowledged_at`, and `last_team_update_at`.
    5. Record: public `acknowledged` event; audit `ticket_acknowledged` with the old and new status, owner, ETA and checkpoint.
    6. Publish `TicketAcknowledged` and `TeamUpdateRecorded`. The initial-response timer is met; progress-update and ETA timers start.
  - **`assign(actor, ticket_no, body)`** (98-140):
    1. `begin(..., assign)`: team, working statuses.
    2. `_assignee`:
       - the id must be valid and a different, active user (422);
       - **a Spoke of the department, or the owner,** may assign any department member (`department_member`) without a reason;
       - **an Admin or Super Admin** may assign anyone, but a `reason` is required (422 `fields.reason`);
       - anyone else gets 422 "Choose an active member of the department".
    3. From `acknowledged` or `reopened` the status moves to `assigned`.
    4. Record: public `assigned` event. The reason is in `detail` (staff only); `public_detail` has just "Assigned to X". Audit `ticket_assigned` with the reason.
    5. Publish `TicketAssigned`, plus `TicketStatusChanged` if the status moved (the SLA handler needs it for `reopened`; `CLAUDE.md` B15).
  - **`change_status(actor, ticket_no, body)`** (142-164):
    1. Only `in_progress` or `awaiting_requester` targets are accepted (422).
    2. The action checked depends on the move: to `awaiting_requester` it is `ask_requester`; from awaiting or on hold it is `resume`; otherwise `start_work`.
    3. **Awaiting requester:** a `message` is required (422). Set `awaiting_since` and add the message as a public comment.
    4. **In progress:** clear `awaiting_since` and the hold fields.
    5. Set the status and `last_team_update_at`; record a public `status_changed` event and audit `ticket_status_changed`; publish `TicketStatusChanged` and `TeamUpdateRecorded`.
  - **`hold(actor, ticket_no, body)`:** `hold` action (in progress only); `review_date` must be in the future. Sets `on_hold`, the reason and the review date. The public `hold` event includes the reason. Audit `ticket_hold`; status events published.
  - **`revise_eta(actor, ticket_no, body)`:**
    1. The new ETA must be in the future and different from the current one (422).
    2. `is_extension` = there was an ETA and the new one is later.
    3. Record a public `eta_revised` event (the reason only in staff `detail`) and audit `ticket_eta_revised`.
    4. Publish `TicketEtaChanged` (with `old`, `new`, `is_extension` and `reason`) and `TeamUpdateRecorded`.
  - **`change_priority(actor, ticket_no, body)`:** the priority must differ (422). The `priority_changed` event is **not public** (staff only); audit `ticket_priority_changed`; publish `TicketPriorityChanged`. The SLA handler recomputes the initial-response thresholds if it is still unmet.
- **Tables:** `tickets`, `ticket_events`, `audit_log`, `users`, `spoke_assignments`, plus the handlers' writes.

##### `app/services/workflow/closure.py`
- **`reopen_denied(ticket, policy) -> ApiError`:** a 409 `invalid_transition` whose message says why: maximum reopens reached, or the reopen window passed. `details` holds `reopen_count`, `max_reopens`, `reopen_window_days` and `reopen_window_ends_at`, so the frontend can explain it.
- **`ClosureService(session, clock)` methods:**
  - `resolve(actor, ticket_no, body)`: `resolve` action (team or assignee, in progress, never the requester). Sets `resolved`, `resolved_at`, the summary and `last_team_update_at`. Public `resolved` event "Resolved: <summary>"; audit `ticket_resolved`; publish `TicketResolved` (the auto-close timer starts).
  - `confirm_closure(actor, ticket_no, body)`: the requester, status `resolved`. Stores the optional rating (1 to 5) and comment, then `close_ticket` with `CloseReason.CONFIRMED`.
  - `close(actor, ticket_no, body)`: `close_admin` (team, resolved). `close_ticket` with `CloseReason.ADMIN` and the reason.
  - **`reopen(actor, ticket_no, body)`** (94-132):
    1. Lock and build the context; check `reopen`.
    2. If refused as `invalid_transition` while the status is resolved or closed, the refusal comes from the limits, so `reopen_denied` gives the detailed 409.
    3. Otherwise: status `reopened`, `reopen_count + 1`; clear `resolved_at`, `closed_at`, the summary, `last_team_update_at`, the ETA and the checkpoint; set `sla_started_at = now` (a fresh SLA cycle).
    4. Public `reopened` event (the previous resolution in `data`); audit `ticket_reopened`; publish `TicketReopened`.
  - `cancel(actor, ticket_no, body)`: team in active statuses, or the requester while `new`. Sets `cancelled` and `cancel_reason`; public `cancelled` event; audit `ticket_cancelled`; publish `TicketCancelled`.
- **`close_ticket(flow, ticket, actor_id, now, close_reason, detail, reason=None, feedback=None)`** (170-203): the shared closing logic. Sets `closed`, `closed_at` and `close_reason`; records a public `closed` event and audit `ticket_closed` (with feedback); publishes `TicketClosed`. Also used by the auto-close job with `actor_id = None`.

##### `app/services/workflow/transfer.py`
- **`TransferService(session, clock).transfer(actor, ticket_no, body)`** (231-291):
  1. `begin(..., transfer)`: team, active statuses.
  2. The target must differ from the current department (422).
  3. `_accepting_department` and `_category`: the same rules as ticket creation. **The two helpers are copied from `tickets.py`** (13.0).
  4. Move the ticket:
     - set the new department and category;
     - `confidential` stays true if it was true, and becomes true if the new category is confidential; it is **never downgraded**;
     - status `new`; clear owner, assignee, ETA, checkpoint, hold and `awaiting_since`;
     - `sla_started_at = now`.
  5. Record: public `transferred` event (the reason only in staff `detail`); audit `ticket_transferred` with the full old and new values.
  6. Publish `TicketTransferred`, then return the ticket **presented for the actor**. After a transfer the caller may no longer be able to see it; the response is still built for them (`CLAUDE.md` B16).

##### `app/services/workflow/system.py`
- **`close_system(session, clock, ticket_id) -> bool`:** used by the `auto_close` worker job. Locks the ticket by id (`populate_existing`, so it is reloaded fresh). If it is still `resolved`, calls `close_ticket` with actor `None`, `CloseReason.AUTO` and the detail "Closed automatically after the confirmation period", then flushes and returns `True`. Otherwise returns `False`. It does not commit; the job does.

#### 4.9.5 SLA engine (`app/services/sla/`)

**The idea in plain words.** Each ticket can have up to six timers, one row per kind in `sla_timers`:

| Timer | What it measures |
|---|---|
| `initial_response` | how long until a Spoke acknowledges the ticket |
| `progress_update` | how long since the team last posted an update |
| `eta` | whether the promised date (or next checkpoint) passes |
| `requester_reminder` | how long the ticket has waited for the requester |
| `hold_review` | when an on-hold ticket must be looked at again |
| `auto_close` | when a resolved ticket closes automatically |

The first three escalate: level 1 (warning) at `warning_at`, level 2 (breach) at `due_at`, level 3 at `l3_at`, then L3 repeats every `escalation_repeat_hours`. The ticket's `escalation_level` is the highest level among those three timers. Times come from the policy (4.5), multiplied by `SLA_TIME_SCALE`. In **business** mode they count working time only (R2-C1).

Who moves the timers:
- **Event handlers** (`app/services/handlers/sla_handlers.py`) start, restart, pause and stop timers when the ticket changes.
- The **scanner** (worker job `sla_scan`) notices passed thresholds and records escalation steps.

##### `app/services/sla/working_time.py` (R2-C1)
- **`WorkingCalendar(working_days, work_start, work_end, holidays)`:** a frozen dataclass whose defaults are Monday to Friday, 09:00 to 18:00, no holidays. `__post_init__` rejects an empty or invalid weekday set and `start >= end`.
  - `is_working_day(day)`: weekday in the set and not a holiday.
  - `hours_of(day)`: that day's opening and closing instants in IST.
- **`DEFAULT_CALENDAR`.**
- **`add_working_time(calendar, start, amount)`:** walks day by day from `start` (in IST). It skips non-working days and holidays, starts at opening time when `start` is before it, and uses up `amount` only inside opening hours. Returns the UTC instant when `amount` of working time has passed. A start outside hours effectively moves to the next working minute. Negative amounts raise.
- **`working_time(calendar, start, end)`:** the working time between two instants (the inverse of the above).
- The SQL function `working_seconds` (migration `r2c1`) computes the same thing inside PostgreSQL for the scanner.

##### `app/services/sla/due_time.py`
- `SlaModeName = Literal["calendar", "business"]`.
- `scaled_hours(hours, scale)`: `timedelta(hours = hours × scale)`.
- `calculate_due(start, hours, mode, scale, calendar=DEFAULT_CALENDAR)`: `calendar` mode adds wall-clock time; `business` mode calls `add_working_time`.
- `add_business_days(start, days, calendar=DEFAULT_CALENDAR)`: moves forward one IST day at a time, counting only the calendar's working days (holidays excluded), keeping the time of day. It is **not** scaled by `SLA_TIME_SCALE`; used for auto-close.

##### `app/services/sla/levels.py`
- **`SLA_TIMER_KINDS`:** initial response, progress update, ETA.
- **Predicates:** `is_active(timer)` (not met and not stopped); `is_running(timer)` (active and not paused).
- **`timer_level(timer, now)`:** 0 for non-SLA kinds or timers that are not running; otherwise 3 if `now >= l3_at`, 2 if `now >= due_at`, 1 if `now >= warning_at`, else 0.
- **`ticket_timers(session, ticket)`:** the ticket's timers.
- **`apply_levels(ticket, timers, now)`:** writes each timer's `level`; sets `ticket.escalation_level` = the maximum over SLA kinds and `ticket.update_overdue` = progress update at level 1 or more.
- **`recompute_ticket(session, clock, ticket)`:** `apply_levels` with the clock, then flush. Used by the scanner.

##### `app/services/sla/timers.py`
- **Constants:** `TERMINAL_STATUSES` (closed, cancelled), `PAUSABLE_KINDS` (progress update, ETA).
- **`Timers(session, ticket, policy, scale)`** loads the ticket's timers into a dict by kind.
  - `mode` and `calendar` (lazy properties): `ticket_sla_mode` (category, then department, then policy) and `load_working_calendar`, loaded only when first needed.
  - `_due(start, hours)`: `calculate_due` in the ticket's mode.
  - `start(kind, now, due_at, warning_at, l3_at)`: creates the row with cycle 1, or, if one exists, calls `restart`.
  - `restart(...)`: `cycle + 1`, new times, and resets pause, level, met and stopped. **The previous cycle is overwritten**, which is why history lives in `escalation_events` and `ticket_events`.
  - `pause(kind, now)`, `resume(kind, now)`: `resume` adds the paused seconds to `paused_seconds`. The thresholds are **not** shifted by the paused time (**Unclear - needs confirmation** whether that is intended; the stored due times stay as they were).
  - `mark_met(kind, now)`, `stop(kind, now)`, `stop_all(now)`, `is_active(kind)`.
  - **Starters** (times relative to `start`, all through `_due`, so business mode applies):

    | Starter | Times |
    |---|---|
    | `start_initial_response(start)` | warning `warning_hours[priority]`, due `initial_response_hours`, L3 `l3_hours[priority]` |
    | `start_progress_update(start)` | warning `update_warning_hours`, due `update_cadence_hours`, L3 2 × cadence |
    | `start_eta(now)` | due = the ETA (or the next checkpoint when there is no ETA); warning = due − `eta_warning_hours` (wall-clock); L3 = due + cadence. With no ETA and no checkpoint, the timer is stopped. |
    | `start_requester_reminder(start)` | due `requester_reminder_hours` |
    | `start_hold_review(now)` | due = `hold_review_date` |
    | `start_auto_close(start)` | due = `add_business_days(start, auto_close_business_days)`; stopped if auto-close is off |
  - `recompute_initial_response_thresholds()`: after a priority change, recompute warning and L3 of an active initial-response timer from its original start.
  - **`reconcile(now)`** (idempotent; makes the timers match the status whatever happened before):
    - terminal status: stop everything;
    - `new` or `reopened`: ensure an initial-response timer, stop the rest;
    - `resolved`: initial response and ETA met; progress, reminder and hold stopped; auto-close started (or stopped if off);
    - working statuses: initial response met, auto-close stopped, progress and ETA started if missing.

      Within the working statuses, `awaiting_requester` pauses progress and ETA and starts the reminder; `on_hold` pauses them and starts the hold review; otherwise it resumes them and stops the reminder and hold review.

##### `app/services/sla/sla_object.py`
- **`SlaState`** (Pydantic): `level`, `kind`, `paused`, `stopped`, `due_at`, `label`. This is `TicketOut.sla`.
- **`build_sla_state(ticket, timers)`** (Appendix R.5):

  | Situation | `SlaState` |
  |---|---|
  | closed or cancelled | stopped, label "Closed" or "Cancelled" |
  | resolved | paused, `due_at` = the auto-close due time, label "Awaiting closure" |
  | on hold or awaiting requester | paused, label "Timer paused" |
  | otherwise | the **governing** timer: among running initial-response, progress and ETA timers, the highest level, ties broken by the earliest `due_at` |

  The governing timer's label is "... due" below level 2 and "... overdue" from level 2 (for example "Initial response overdue"). With no running timer the label is "On track".

##### `app/services/sla/escalation.py`
- **`CREATION_CONTACT = "CREATION_CONTACT"`:** the step key used when a **critical** ticket is created, to alert the department's escalation contact at once.
- **`resolve_recipients(session, ticket, level, *, creation_contact=False)`:** who is told about an escalation.

  | Step | Recipients |
  |---|---|
  | creation contact | the escalation contact; if none, all Admins; if none, all Super Admins |
  | level 1 | the team: owner, assignee, department Spokes |
  | level 2 | the team plus the escalation contact plus all Admins (Super Admins only if there is no contact and no Admin) |
  | level 3 | all Super Admins and Admins |

  For **confidential** tickets only, recipients who cannot see the ticket are removed (`_visible_only`, which loads each user's `Actor`). If nobody with a management role remains for level 2+ or creation contact, the Super Admins are added. Results are unique and sorted by name.
- **`record_step(session, ticket, timer_kind, cycle, level, step_key, at, recipient_ids) -> bool`:** `INSERT ... ON CONFLICT DO NOTHING` on the unique (ticket, timer, cycle, step) key. Returns whether a new row was written, so each step happens once even with two workers.
- **Note:** helpers `_active_user`, `_department_spokes` and `_active_users_with_role` duplicate those in `handlers/recipients.py` (13.0).

##### `app/services/sla/scanner.py` (worker job `sla_scan`)
- **Constants:** `SCAN_LOCK_KEY = 7_420_019`, `BATCH_SIZE = 100`, `REPEAT_PREFIX = "L3_REPEAT_"`; `Step(key, level)`.
- **Module functions:**
  - `repeat_index(timer, now, repeat, calendar=None)`: how many repeat intervals have passed since `l3_at` (working time in business mode).
  - `due_steps(timer, ticket, now, repeat, calendar=None)`: every step whose threshold has passed: `CREATION_CONTACT` (critical initial response), `L1`, `L2`, `L3`, and the current `L3_REPEAT_n`.
  - `steps_to_emit(new_steps)`: of the newly recorded steps, one per level (the latest), plus the creation contact. After an outage the worker records all missed steps but sends only one alert per level (`docs/BACKUP-RESTORE.md`).
  - `step_detail(...)`: timeline text such as "L2 initial response breach".
  - `business_basis(policy_mode)`: SQL expression for "this ticket is in business mode".
  - `candidate_timers(now, repeat, policy_mode)`: running SLA timers of non-terminal tickets whose **current** step (repeat, L3, L2 or L1, in that order) is not yet recorded, or whose creation-contact step is pending. The repeat index is computed in SQL (`working_seconds` for business-mode tickets), ordered by `due_at`.
- **`SlaScanner(session, clock, scale).run()`:**
  1. `pg_try_advisory_xact_lock(7420019)`. If another worker holds it, return 0 at once: only one scanner runs at a time.
  2. Select up to 100 candidates `FOR UPDATE SKIP LOCKED`.
  3. For each, in a savepoint, `_process`:
     1. Lock the ticket `SKIP LOCKED`; skip it if busy, terminal or not running.
     2. `record_step` for each due step, with recipients from `resolve_recipients`.
     3. If anything is new: `recompute_ticket`, then per emitted step write a non-public `escalation` timeline event (system actor) and audit `ticket_escalation`.
     4. Publish `SlaWarningRaised` (L1) or `EscalationRaised` (L2+, or creation contact). The notification handlers send the alerts.
  4. Return the number of timers processed.
- **Lock order:** the scanner never waits for a lock (SKIP LOCKED); the other jobs lock the ticket before the timer (`CLAUDE.md` B19).

#### 4.9.6 Domain-event handlers and notifications

##### `app/services/handlers/__init__.py`
- **`register_all(target=bus)`:** clears the bus, then registers the SLA handlers **first** and the notification handlers **second**. The order matters: notifications read the timer state the SLA handlers have just updated (for example the cycle in dedupe keys).
- **Called by:** `create_app`, `app/seed/run.py`, tests.

##### `app/services/handlers/sla_handlers.py`
- **`_apply(action)`** wraps each handler:
  1. Reload the ticket.
  2. Read the current policy and build `Timers` with `get_settings().sla_time_scale`.
  3. Run the action.
  4. `timers.reconcile(event.occurred_at)`.
  5. Flush; `apply_levels`; flush.

  The event's `occurred_at` is "now", so replays and tests are deterministic.
- **Handlers:**

  | Event | Action |
  |---|---|
  | `TicketCreated` | start initial response at `sla_started_at` |
  | `TicketAcknowledged` | initial response met; start progress update and ETA |
  | `TeamUpdateRecorded` | restart progress update, only if it is running (not paused) |
  | `TicketStatusChanged` | to awaiting requester: pause progress and ETA, start the reminder. To on hold: pause them, start the hold review. From either back to in progress: stop reminder and hold review, restart progress, resume ETA. From reopened to in progress or assigned: initial response met, start progress. |
  | `TicketEtaChanged` | restart the ETA timer |
  | `TicketPriorityChanged` | recompute initial-response thresholds |
  | `TicketResolved` | ETA met; stop progress, reminder and hold review; start auto-close |
  | `TicketClosed`, `TicketCancelled` | stop all |
  | `TicketReopened` | set `sla_started_at`; stop auto-close, ETA and progress; start a new initial-response cycle |
  | `TicketTransferred` | set `sla_started_at`; stop progress, ETA, reminder and hold review; start a new initial-response cycle |

##### `app/services/handlers/recipients.py`
- **`Recipient(user, email)`** and **`Recipients(*excluded)`:** a builder.
  - `add(users, email=...)` skips `None` and excluded ids (always the acting user: people are never notified of their own actions, `CLAUDE.md` B26).
  - Adding the same user twice keeps `email = True` if either add asked for it.
  - `items()` sorts by name.
- **Helpers:** `active_user`, `active_users_with_roles`, `department_spokes`, `collaborators`, `requester`, `owner_and_assignee`.
- **`visible_only(session, ticket, entries)`:** keeps recipients who can see the ticket (`load_actor` plus `can_view_ticket`). Every ticket notification goes through it, so a person who cannot see a ticket never hears about it. This is how confidential tickets stay hidden from notifications.

##### `app/services/handlers/notification_handlers.py`
- **`deliver(session, at, entries, message)`:** `Notifier(session, at).send(user, message, email=entry.email)` for each recipient.
- **`_for_ticket(planner)`:** reloads the ticket, asks the planner for `(Recipients, Message)` (or `None`), filters with `visible_only`, and delivers.
- **Ticket planners.** "P" = portal notification only; "P+E" = portal plus email (subject to the recipient's email preference, `Notifier.send` below). The acting user is always excluded.

  | Event | Kind | Recipients |
  |---|---|---|
  | created | `ticket_created` | requester P+E (normally the actor, so excluded), department Spokes P+E |
  | acknowledged | `ticket_acknowledged` | requester P+E (text includes owner and ETA or next update) |
  | assigned | `ticket_assigned` | new assignee P+E; requester and Spokes P |
  | status changed | `status_changed` | requester P+E; owner and assignee P |
  | comment | `comment_added` | **team author**: requester and collaborators P+E. **Non-team author**: owner, assignee and Spokes P+E. **Internal note**: owner, assignee and Spokes P only (kind `internal_note`, no email). |
  | ETA changed | `eta_changed` | requester P+E ("set", "extended" or "changed") |
  | priority changed | `priority_changed` | owner and assignee P (no email template) |
  | transferred | `transferred` | requester, old and new department Spokes P+E (old Spokes are dropped by `visible_only` if they lost access) |
  | resolved | `resolved` | requester P+E with the summary |
  | closed | `closed` | requester P+E; owner and assignee P |
  | reopened | `reopened` | owner, assignee and Spokes P+E; requester P |
  | cancelled | `cancelled` | requester P+E; owner and assignee P |
  | collaborator added | `collaborator_added` | the new collaborator P+E (nothing on removal) |
  | SLA warning (L1) | `sla_warning` | `resolve_recipients(level)` P+E; dedupe key `sla_warning:{ticket}:{timer}:{cycle}:L{level}` |
  | escalation | `escalation` | only level ≥ 2 or creation contact; `resolve_recipients` P+E; **critical**; dedupe key `escalation:{ticket}:{timer}:{cycle}:{step}` |
- **Account handlers** (no ticket, so no visibility filter):

  | Event | Kind | Recipients | Critical |
  |---|---|---|---|
  | `SignupVerified` | `signup_pending` | Admins and Super Admins for employee requests; Super Admins only for admin and super-admin requests; the applicant excluded | no |
  | `UserDeactivated` | `user_deactivated_open_tickets` | Admins and Super Admins, only when open tickets > 0 | yes |
  | `ProtectedActionRequested` | `protected_action_requested` | other Super Admins | yes |
  | `ProtectedActionDecided` | `protected_action_decided` | the requester and Super Admins | yes |
  | `ConfidentialGrantChanged` | `confidential_grant_changed` | the affected user ("granted" or "revoked", checked live) | no |
- **`register_notification_handlers(target)`:** registers all 20 handlers.

##### `app/services/notifications.py`
- **`CONFIDENTIAL_TEMPLATE = "confidential_ticket_update"`.**
- **`Message(kind, text, template, context, critical=False, ticket_id=None, dedupe_key=None)`.**
- **`confidential_text(ticket)`:** `"Update on <ticket number>"`.
- **`ticket_message(ticket, *, kind, text, email=True, extras=None, critical=False, dedupe_key=None)`:**
  - Builds a summary context (number, department, status label, priority).
  - For a **confidential** ticket, the portal text becomes `Update on IBX-...`, the email template becomes `confidential_ticket_update`, and the context is only the summary: no title, comment body or resolution ever leaves the system.
  - Otherwise the template is named after the kind, and the context adds the title, text and extras.
  - `email=False` means no template (portal-only kinds).
- **`Notifier(session, at).send(user, message, *, email) -> notification id | None`:**
  1. `INSERT ... ON CONFLICT (user_id, dedupe_key) DO NOTHING RETURNING id`. If the dedupe key already exists, return `None` (no duplicate).
  2. No email wanted or no template: stop.
  3. **Critical** messages always go out immediately.
  4. Otherwise the recipient's `non_critical_email` preference decides (R2-C2): `immediate` queues the email with `enqueue_email` (the user's name added to the context); `daily_digest` adds a `digest_items` row for the digest job; `off` sends nothing.
- **`NotificationService(session, clock)`:**
  - `list_own(actor, unread, params)`: the caller's notifications, newest first, **hiding rows whose ticket the caller can no longer see** (`_own` joins tickets and applies `visible_ticket_clause`). Ticket ids are shown as numbers.
  - `unread_count(actor)`: the same filter.
  - `mark_read(actor, id)`: someone else's id or an unknown one gives 404.
  - `mark_all_read(actor)`: one UPDATE.
- **Tables:** `notifications`, `digest_items`, `email_outbox`, `tickets`, `notification_preferences`.

#### 4.9.7 Reporting: dashboards, KPIs, exports, saved views

##### `app/services/dashboards.py`
- **Constants:** `ATTENTION_LIMIT = 6`, `RECENT_UPDATES_LIMIT = 10`, `URGENCY = "urgency"`.
- **`DashboardService(session, clock)`.** Every count goes through `_count`, which always adds `visible_ticket_clause(actor)`.
  - **`employee(actor)`** (anyone), where "requested" = requester is me and "assigned" = assignee is me:

    | Field | Counts |
    |---|---|
    | `open` | my requested tickets that are active |
    | `awaiting_my_response` | requested, status awaiting requester |
    | `resolved_to_confirm` | requested, status resolved |
    | `closed` | requested, status closed |
    | `assigned_to_me` | assigned and active |
    | `assigned_warning` | assigned, active, level 1 |
    | `assigned_breached` | assigned, active, level ≥ 2 |

    `recent_updates`: the last 10 **public** events on tickets I requested or am assigned, showing `public_detail` when present. `attention`: up to 6 of those tickets with escalation level above 0 or awaiting the requester, in urgency order.
  - **`spoke(actor)`:** needs `tickets.view_department` (403). The scope is the caller's Spoke departments.

    | Field | Counts |
    |---|---|
    | `new_unacknowledged` | status new |
    | `approaching_sla` | active, level 1 |
    | `breached` | level ≥ 2 |
    | `stale_or_eta_overdue` | update overdue, or active with an overdue ETA |
    | `awaiting_requester`, `on_hold`, `resolved_pending_closure` | by status |
    | the KPI fields | from `KpiService.dashboard` |

    `attention`: up to 6 active tickets by urgency.
  - **`admin(actor)`:** needs `tickets.view_all` (403). `open_count`, `breached_count` (level ≥ 2), `l3_count`, `stale_count`, `pending_approvals`, the KPI fields, and `attention`.
  - **`_pending_approvals(actor)`:** pending requests of verified users that **this** actor may decide (`can_decide_signup`), counted in Python.
- **Tables:** `tickets`, `ticket_events`, `users`, `signup_requests`, plus the KPI reads.

##### `app/services/kpis.py`
- **Constants:** `DEFAULT_WINDOW = 30 days`, `MAX_WINDOW = 366 days`.
- **Types:** `KpiQuery(start, end, department_id, priorities)` and `DashboardKpis(sla_met_pct, avg_initial_response_seconds, reopen_rate_pct, by_department)`.
- **Helpers:**
  - `percent(part, whole)`: one decimal, or `None` when `whole` is 0 ("no data", not 0%);
  - `whole_seconds`.
- **`KpiService(session, clock)`:**
  - **`report(actor, query) -> KpiReportOut`** (94-148):
    1. Needs report access (403).
    2. `_window`: defaults to the last 30 days ending now. `from >= to` gives 422 `fields.to`; more than 366 days gives 422 `fields.from`.
    3. `_known_department`: an unknown department gives 422.
    4. `report_scope` (403 for a Spoke asking about another department).
    5. Build the scope clauses: **visibility clause** plus departments plus priorities.
    6. Run the aggregates of 4.7: SLA per department (summed for the totals), reopen, initial-response trend and total (one GROUPING SETS query), snapshot counts, resolution turnaround, escalations, ETA breaches, persistent L3, departments, workload by assignee and by owner, top categories.
    7. `_initial_response` fills **every IST day** in the window, with zero counts for days without data.
    8. `_workload`: named users sorted by active count, then name; "unassigned" or "no owner" rows (user `null`) last.
  - **`dashboard(actor, department_ids)`:** the last 30 days, no priority filter. Returns the three KPI fields and `by_department` (on track, warning, breached). It does **not** check permissions itself; the dashboard endpoints already have.
- **Performance:** each aggregate is one SQL statement. The perf test requires a p95 under 500 ms with 50,000 tickets (`tests/perf/test_kpi_performance.py`).

##### `app/services/exports/__init__.py`
- **Constants:** `ROW_LIMITS` (CSV and XLSX 50,000, PDF 2,000), `CHUNK = 1,000` (batch size for loading related rows), `REPORT_NAMES`.
- **`ExportFile(filename, media_type, chunks)`.**
- **`ticket_filter_values(query, sort)`:** the applied filters as text (`key=value`, datetimes in UTC), for the file header and the audit row.
- **`ExportService(session, clock).export(actor, export_type, export_format, query, start, end)`** (87-125):
  1. Needs report access (403).
  2. **Tickets:** `report_scope` (403 for another department). The filters are the same as `GET /tickets` (`TicketReadService.filters`), narrowed to the Spoke's departments when the caller lacks `reports.view_org`. Count first; over the format's limit gives 422 `fields.format` ("narrow the filters"; the export is refused, not truncated). Then load the tickets, related users, categories and timers in chunks, and build one table with `ticket_table`.
  3. **KPIs:** call `KpiService.report` and turn it into seven tables with `kpi_tables`.
  4. Audit `report_exported` with `{type, format, filters, row_count}`. It is security limited when the export contains (tickets) or covers (KPIs) any confidential ticket.
  5. Return the file: name `ibotix-<type>-<YYYYMMDD-HHMM IST>.<format>`, the media type, and the byte chunks from `render`.

  All database work and the audit row happen **inside the service**, before the router starts streaming, because `DbSession` commits before the response body is sent.
- **Note:** up to 50,000 ORM ticket objects are held in memory, and XLSX and PDF files are built fully in memory (13.0).

##### `app/services/exports/tables.py`
- **Types and constants:** `Cell` (str, int, float or None), `Row`; `TICKET_COLUMNS` (19 columns, from Ticket to Reopen count); `Table(title, columns, rows)`; `Document(report, header, tables)`.
- **Functions:**
  - `ist_text(value)`: `YYYY-MM-DD HH:MM +05:30`.
  - `yes_no`, `row_count`.
  - `build_document(report, generated_by, generated_at, filters, tables)`: header rows `Report`, `Generated by`, `Generated at`, `Filters` and `Rows`.
  - `ticket_table(tickets, users, categories, timers)`: names instead of ids; the SLA column is `build_sla_state(...).label`.
  - `kpi_tables(report)`: Summary, Initial response trend, Aging, Departments, Workload by assignee, Workload by owner, Top categories.
- No database access and no formatting logic beyond text.

##### `app/services/exports/writers.py`
- **Constants:**
  - `FORMULA_PREFIXES` (`=`, `+`, `-`, `@`, tab, carriage return);
  - `MEDIA_TYPES`;
  - Excel sheet-title rules (31 characters, no `[]:*?/\`);
  - PDF layout values.
- **Functions:**
  - **`safe_cell(value)`:** a text value starting with a formula character gets a leading `'`. This prevents **CSV/Excel formula injection**: a ticket titled `=HYPERLINK(...)` cannot run as a formula when the file is opened.
  - **`csv_chunks(document)`:** writes the header block, a blank line, an optional table title (when there are several tables), the column row, then the rows, yielding the bytes as it goes, so CSV is streamed.
  - **`sheet_title(title, used)`:** a valid, unique sheet name.
  - **`xlsx_bytes(document)`:** an openpyxl write-only workbook, one sheet per table, with the header block on the first sheet.
  - **`pdf_bytes(document)`:** a reportlab A4 landscape document: title, header lines, then each table with wrapped, escaped cells.
  - **`render(document, format)`:** returns an iterator of byte chunks for any format.

##### `app/services/saved_views.py`
- **Constants:** `BUILT_IN_PREFIX = "builtin."`, `MAX_VIEWS_PER_USER = 50`, `AWAITING_LONGER_THAN = 48 h`, `ID_FIELDS`, `TIME_FIELDS`.
- **`BuiltInView(key, name, spokes_only, query)`** and **`BUILT_IN_VIEWS`** (computed per request, never stored):

  | id | Name | Query | Shown to |
  |---|---|---|---|
  | `builtin.department_breached` | My Department - SLA Breached | `{scope: queue, sla_state: breached}` | Spokes |
  | `builtin.no_update_24h` | No Update > 24h | `{scope, sla_state: stale}` | everyone |
  | `builtin.unassigned_today` | Unassigned Today | `{scope, unassigned: true, created_from: start of today IST}` | everyone |
  | `builtin.escalated_l3` | Escalated L3 | `{scope, escalation_level: 3}` | everyone |
  | `builtin.awaiting_requester_48h` | Awaiting Requester > 48h | `{scope, awaiting_before: now − 48 h}` | everyone |

  `scope` = `built_in_view_scope(actor)`: `queue` for Spokes, `all` for staff, otherwise `mine`.
- **`normalize_query(raw)`:**
  1. Validate with `TicketListQueryModel` (unknown keys rejected); errors become `fields["query.<key>"]`.
  2. Check the status values, id fields and sort key.
  3. Return the cleaned JSON with `None` values dropped and datetimes as UTC `Z` strings.

  This is "one parser for both": a view's query is validated exactly like a `GET /tickets` query.
- **`view_out(view)`.**
- **`SavedViewService(session, clock)`:**
  - `list_views(actor)`: built-ins first, then own active views by name, ignoring case.
  - `create(actor, body)`: normalise; lock the owner's `users` row (serialises concurrent creates); more than 50 active views gives 409; a duplicate name (ignoring case) gives 409; insert.
  - `update(actor, view_id, body)`: normalise; lock; `_own`; re-check the name; save.
  - `delete(actor, view_id)`: soft delete (`deleted_at`).
  - `_own(actor, view_id)`: a built-in id gives 403; a non-UUID, unknown, deleted or **someone else's** view gives 404 (other users' views are invisible, not forbidden).
- **Tables:** `saved_views`, `users` (lock), `policy_versions`.

### 4.10 Routers (`app/api/routers/`)

A **router** is the thin HTTP layer: it declares the URL, method, request body and response model, pulls in the dependencies, calls **one** service method and returns the result. `CLAUDE.md` says "routers are thin": there is no business logic, permission check or SQL in this folder. Section 7 lists every route with its rules; this section describes each file.

**Shared building blocks (from `app/api/deps.py`, 4.4):**

| Dependency | What it gives the route |
|---|---|
| `DbSession` | a SQLAlchemy session from `get_db`, with `scope="function"`, so the transaction **commits before the response is sent** (`app/core/db.py`) |
| `ClockDep` | the `Clock` (real time, or a frozen clock in tests) |
| `SettingsDep` | the `Settings` stored on `app.state` by `create_app` |
| `CurrentActor` | the authenticated `Actor`. `get_actor` reads `Authorization: Bearer <token>`, decodes the JWT, reloads the user, and gives 401 `unauthenticated` if anything fails or the user is not active. It also sets `request.state.user_id` for the access log. |
| `require_allowed_origin` | 403 if an `Origin` header is present and not in `CORS_ORIGINS`. Used only on the two cookie-based routes (refresh, logout) as CSRF protection. |
| `PageParams` (`app/core/pagination.py`) | `page` (default 1) and `page_size` (default 25, maximum 100) query parameters |

**Two error-return styles.**
- Most routes let the service **raise** an `ApiError`. The exception handler in `app/core/errors.py` turns it into the JSON error envelope, and `get_db` rolls back.
- A few routes need the database work to be **kept** even when the answer is an error: a failed login must still save the failure counter and audit row. Those services **return** the `ApiError`, and the router answers with `error_response(request, error)` so `get_db` still commits (`CLAUDE.md` B06). This applies to `login`, `mfa_verify`, `refresh`, `forgot_password`, `signup`, `resend_verification` and `reapply`.

**How they are mounted** (`app/main.py` lines 76-100): `health.router` is mounted at the root (`/health/...`); every other router is included in one `APIRouter(prefix="/api/v1")`.

#### `app/api/routers/__init__.py`
- Empty file that makes the folder a package.

#### `app/api/routers/health.py`
- Described in 4.4 (the three probes and the worker staleness rule). It is the only router mounted outside `/api/v1`, and it uses `Depends(get_db, scope="function")` directly instead of the `DbSession` alias, with the same effect.

#### `app/api/routers/config.py`
- **Purpose:** the one public data endpoint, `GET /public/config` (prefix `/public`).
- **Route:** `public_config(db, settings)` calls `PolicyService(db).public_config(settings)`. It needs no token, so the signup page can show the allowed email domains, departments, upload limits, minimum password length and first-response hours before anyone logs in.

#### `app/api/routers/auth.py`
- **Purpose:** login, MFA, token refresh, logout, current user, and password reset (prefix `/auth`).
- **Constants:** `REFRESH_COOKIE = "refresh_token"` and `REFRESH_COOKIE_PATH = "/api/v1/auth"`. The browser sends the cookie **only** to auth URLs, never to ticket endpoints.
- **Helpers:**
  - `_set_refresh_cookie(response, token, settings)`: an `httponly` cookie, so JavaScript cannot read it. `max_age` is `REFRESH_TOKEN_DAYS` days; `secure` and `samesite` come from `COOKIE_SECURE` and `COOKIE_SAMESITE`.
  - `_clear_refresh_cookie`: deletes it with the same attributes. A browser deletes a cookie only when the attributes match.
- **Routes:**
  - `login`: the result can be four things. An `ApiError` becomes an error response. `MfaRequired` or `MfaEnrolRequired` is returned as is (no cookie). A `LoginGranted` sets the cookie and returns `LoginSuccess`. The `response_model` is the union of the three success shapes.
  - `mfa_setup`, `mfa_confirm`, `mfa_verify`: the MFA token travels **in the body**, not in a header, so these routes do not use `CurrentActor`. Confirm and verify set the refresh cookie on success.
  - `refresh` and `logout`: read the cookie through `RefreshCookie` (`Cookie(alias="refresh_token")`) and are protected by `require_allowed_origin`. `logout` always answers 204 and clears the cookie, even when there was no cookie.
  - `me`: `MeService(db).me(actor)`.
  - `forgot_password`: 202 with an empty body, unless the rate limit returns an error. Unknown emails get the same 202.
  - `reset_password`: 204.

#### `app/api/routers/signup.py`
- **Purpose:** self-registration and the approval queue. It has no prefix, because its paths sit under both `/auth/...` and `/signup-requests`.
- **Routes:**
  - `signup` (202, `SignupAccepted`), `verify_email` (`VerifyEmailResult(state=...)`), `resend_verification` (202), `reapply` (202): public. The first, third and fourth use the "returned error" style.
  - `list_signup_requests`: paged. The `status` query parameter is read into `status_filter` (`Query(alias="status")`), so the Python name does not shadow FastAPI's `status` module.
  - `approve_signup_request`, `reject_signup_request`.
  - The three `/signup-requests` routes use `response_model_exclude_none=True`, so null optional fields are left out of the JSON (`CLAUDE.md` B08).

#### `app/api/routers/users.py`
- **Purpose:** the user directory and account management.
- **Constant:** `QUERY_MAX_LENGTH = 200`.
- **Routes:**
  - `list_users`: filters `q`, `role`, `state` and `department_id` (maximum 6 characters), plus paging.
  - `lookup_users`: `q` defaults to `""`; the service requires at least 2 characters. The actor parameter is named `_actor` because the route only needs a logged-in user, and the service does not use it.
  - `department_members` (`GET /departments/{id}/members`): lives in this file, not in `departments.py`, because it returns `UserRef`s from `UserService`. Also uses `_actor`.
  - `update_roles` (replace Spoke departments), `deactivate_user`, `activate_user`.

#### `app/api/routers/admins.py`
- **Purpose:** promote and demote Admins (Super Admin only, checked in `UserService`).
- **Routes:** `list_admins`, `promote_admin` (body `user_id`), `demote_admin` (path `user_id`). All three return `UserListItem`.

#### `app/api/routers/protected_actions.py`
- **Purpose:** the "two Super Admins" approval flow for removing a Super Admin (B09).
- **Routes:** `list_protected_actions` (paged, `status` filter), `create_protected_action`, `approve_protected_action`, `reject_protected_action`. All use `response_model_exclude_none=True`.

#### `app/api/routers/departments.py`
- **Purpose:** departments, their Spokes and escalation contacts.
- **Routes:**
  - `list_departments`, `create_department` (returns **200**, not 201, as the contract says; `CLAUDE.md` B10).
  - `update_department`: passes `body.sla_mode_change()`. That method tells "field absent" (no change) apart from `"sla_mode": null` (clear the override) (`app/schemas/org.py`, R2-C1).
  - `add_spoke`, `remove_spoke`, `set_escalation_contact` (`PUT`, `contact_id` may be `null`).

#### `app/api/routers/categories.py`
- **Purpose:** categories inside a department.
- **Routes:** `create_category` (`POST /departments/{id}/categories`, returns 200), `update_category` (also uses `sla_mode_change()`), `delete_category` (204; it is a **soft** delete, `CategoryService.deactivate`).

#### `app/api/routers/confidential_grants.py`
- **Purpose:** who may see confidential tickets of a category.
- **Routes:** `list_grants` (optional `category_id` and `user_id` filters), `create_grant` (returns 200), `revoke_grant` (204).

#### `app/api/routers/policy.py`
- **Purpose:** read and replace the versioned SLA and workflow policy.
- **Routes:** `read_policy` and `replace_policy` (`PUT`). The response model is the service-layer `PolicyConfig`, not a schema in `app/schemas/`.

#### `app/api/routers/calendar.py` (R2-C1)
- **Purpose:** the business-hours calendar and holidays.
- **Routes:** `read_calendar`, `update_calendar` (`PUT`), `add_holiday` (**201**, returns the whole calendar), `remove_holiday` (`DELETE /calendar/holidays/{date}`, 204; `date` is `YYYY-MM-DD` text, parsed by the service).

#### `app/api/routers/tickets.py`
- **Purpose:** list, create and read tickets, and the timeline.
- **Constants:** `QUERY_MAX_LENGTH = 200`, `ID_MAX_LENGTH = 64`.
- **`ticket_list_query(...)`** (now in `app/api/params.py`, 13.0 #29) is a dependency function that turns about 20 query parameters into one `TicketListQuery` dataclass:
  - `status` and `status[]` are **both** accepted and merged; so are `priority` and `priority[]`. Different frontend libraries encode arrays differently (`CLAUDE.md` B13).
  - `status` values are raw strings here, so `open` (a pseudo-status) can be expanded by the service.
  - `awaiting_before` is an `AwareDatetime` (a time zone is required), but `created_from` and `created_to` are plain `datetime` (13.0 #28).
- **`TicketListParams`** (in `app/api/params.py`): `Annotated[TicketListQuery, Depends(ticket_list_query)]`. Shared by `tickets.py` and `exports.py`, so an export accepts exactly the same filters as the list. `created_from` and `created_to` without a time zone are read as UTC (`assume_utc`, 13.0 #28).
- **Routes:** `list_tickets`, `create_ticket` (201), `get_ticket`, `get_timeline` (`response_model_exclude_none=True`, so a non-staff viewer's events have no null `detail` field).
- **Note:** the path parameter is called `id`, but it holds the **ticket number** (`IBX-IT-2026-000017`), not the UUID. All ticket routes work this way.

#### `app/api/routers/ticket_workflow.py`
- **Purpose:** the twelve lifecycle actions. Each route is one line that calls `ProgressService`, `ClosureService` or `TransferService` and returns the updated `TicketOut`.

  | Route function | Service method | Body |
  |---|---|---|
  | `acknowledge` | `ProgressService.acknowledge` | `AcknowledgeBody` |
  | `assign` | `ProgressService.assign` | `AssignBody` |
  | `change_status` | `ProgressService.change_status` | `StatusBody` |
  | `hold` | `ProgressService.hold` | `HoldBody` |
  | `revise_eta` | `ProgressService.revise_eta` | `EtaBody` |
  | `change_priority` | `ProgressService.change_priority` | `PriorityBody` |
  | `resolve` | `ClosureService.resolve` | `ResolveBody` |
  | `confirm_closure` | `ClosureService.confirm_closure` | `ConfirmClosureBody` |
  | `reopen`, `cancel`, `close` | `ClosureService.reopen` / `cancel` / `close` | `ReasonBody` |
  | `transfer` | `TransferService.transfer` | `TransferBody` |

  All return 200 with the ticket as the caller now sees it.

#### `app/api/routers/ticket_comments.py`
- **Purpose:** comments and collaborators.
- **Routes:** `add_comment` (**201**, returns the new `TimelineEventOut`, nulls excluded), `add_collaborator` and `remove_collaborator` (both return the `TicketOut`).

#### `app/api/routers/attachments.py`
- **Purpose:** upload and download files.
- **`_service(db, clock, settings)`:** builds `AttachmentService` with `build_storage(settings)` and `build_scanner(settings)` (4.4). These are created on each request; they are cheap objects.
- **Routes:**
  - `upload_attachment`: a multipart form with one field `file` (`UploadFile`). The route passes the file name, declared content type and the underlying file object to the service. 201.
  - `download_attachment`: returns a `StreamingResponse` with:
    - `Content-Disposition: attachment; filename*=UTF-8''<percent-encoded name>`. `attachment` forces a download instead of rendering in the browser, and the RFC 5987 encoding handles non-ASCII names safely;
    - `X-Content-Type-Options: nosniff` (the browser must trust the declared type);
    - `Content-Length`.

#### `app/api/routers/notifications.py`
- **Purpose:** the portal notification list.
- **Routes:** `list_notifications` (paged, `unread` filter, nulls excluded), `unread_count`, `mark_all_read` (204), `mark_read` (204).
- **Order matters:** `/notifications/read-all` is declared **before** `/notifications/{id}/read`. Both are POST and the paths differ in segment count, so they cannot collide, but keeping fixed paths first is the safe FastAPI habit.

#### `app/api/routers/preferences.py` (R2-C2)
- **Purpose:** the caller's own email preferences. Tagged `notifications` in the OpenAPI document.
- **Routes:** `read_preferences` and `replace_preferences` (`PUT /me/notification-preferences`).

#### `app/api/routers/dashboards.py`
- **Routes:** `employee_dashboard`, `spoke_dashboard` and `admin_dashboard`, each calling the matching `DashboardService` method.

#### `app/api/routers/audit.py`
- **Purpose:** the audit log viewer.
- **Constants:** `TEXT_MAX_LENGTH = 200`, `ID_MAX_LENGTH = 64`.
- **Route:** `list_audit`, with filters `q`, `actor_id`, `action`, `ticket_id` (a ticket number), and `from` and `to`, read into `created_from` and `created_to` with `Query(alias=...)` because `from` is a Python keyword. It has no `ClockDep`; `AuditReadService` does not need time.

#### `app/api/routers/reports.py` (R2-A)
- **Route:** `kpi_report` (`GET /reports/kpis`). It builds a `KpiQuery` from `from`, `to` (both `AwareDatetime`), `department_id` and `priority` / `priority[]` (merged as in tickets), then calls `KpiService.report`.

#### `app/api/routers/exports.py` (R2-B)
- **Route:** `export_report` (`GET /reports/export`).
  - Required query parameters: `type` (`tickets` or `kpis`) and `format` (`csv`, `xlsx` or `pdf`).
  - Also accepts all the ticket-list filters (`TicketListParams` from `app/api/params.py`) and `from` and `to`.
- **Behaviour:** `ExportService.export` does **all** the database work and the audit row before returning, because `DbSession` has committed by the time the body streams. The router wraps `export.chunks` in a `StreamingResponse` with `Content-Disposition: attachment; filename="<name>"`.

#### `app/api/routers/saved_views.py` (R2-B)
- **Routes:** `list_saved_views`, `create_saved_view` (201), `update_saved_view` (`PATCH`), `delete_saved_view` (204, soft delete).

### 4.11 Worker jobs (`app/worker/jobs/`)

The worker loop itself (`Worker.tick`, `_run_job`, `_beat`, signals) is described in 4.4. This section covers the seven jobs it runs, **in registry order** (`registered_jobs()` in `app/worker/jobs/__init__.py`).

**The pattern every job follows** (`CLAUDE.md` B07, B19):
1. Select a batch of **ids** that look due (no locks), then `commit()`.
2. For each id, lock the row(s) with `SKIP LOCKED`, so a second worker skips rows the first is handling.
3. Re-check that the row is still due. Time passed, and another process may have acted.
4. Do the work and `commit()` **per item**, so one bad item does not undo the others.
5. Return the count, which goes into the log line and `worker_heartbeat.details`.

**Lock order.** Every job locks the **ticket first, then the timer**, the same order as the API's event handlers, so they cannot deadlock. The scanner is the exception: it locks timers first, but never waits (`SKIP LOCKED` on both).

#### `app/worker/jobs/sla_scan.py`
- **`run(session, context)`:** `SlaScanner(session, clock, settings.sla_time_scale).run()`, then commit. All logic is in the scanner (4.9.5): one scanner at a time through an advisory lock, batches of 100, one savepoint per timer.
- **Returns:** the number of timers processed.

#### `app/worker/jobs/reminders.py`
- **Purpose:** the two non-escalating reminders (R.7 scheduler rows, B19).
- **Contents:**
  - `BATCH_SIZE = 100`.
  - `Reminder(status, step_key, kind)`.
  - `REMINDERS`, a read-only mapping:

    | Timer | Ticket must be | Step key | Notification kind | Recipient |
    |---|---|---|---|---|
    | `requester_reminder` | `awaiting_requester` | `REMINDER` | `requester_reminder` | the requester |
    | `hold_review` | `on_hold` | `HOLD_REVIEW` | `hold_review_due` | the owner |
- **`due_reminders(session, clock)`:** per kind, the ticket ids whose timer is active (not met, not stopped), past `due_at`, on a ticket still in the right status, with **no `escalation_events` row yet** for this timer, cycle and step key. Oldest first, up to 100 per kind.
- **`send_reminder(session, clock, ticket_id, kind) -> bool`:**
  1. Lock the ticket `FOR UPDATE SKIP LOCKED` (`populate_existing`, so it is re-read fresh). Stop if it is busy or no longer in the status.
  2. Lock the timer and re-check it is active and due.
  3. Recipient: the requester or the owner, if active (`active_user`), filtered by `visible_only`.
  4. `record_step(..., level 1, step_key)`: `ON CONFLICT DO NOTHING` makes the reminder happen **once per timer cycle**. If it returns `False`, someone else already sent it.
  5. Build the message with `ticket_message` (masked for confidential tickets), dedupe key `<kind>:<ticket id>:<cycle>`, and `deliver` it.
- **`run`:** collects, commits, then sends one by one, committing each.
- **Note:** a new cycle (for example after the ticket goes back to awaiting the requester) gets a new reminder, because the timer's cycle increases.

#### `app/worker/jobs/auto_close.py`
- **Purpose:** close resolved tickets the requester never confirmed.
- **`due_ticket_ids`:** active `auto_close` timers past `due_at` on `resolved` tickets, up to 100.
- **`close_due(session, clock, ticket_id) -> bool`:** lock the ticket `SKIP LOCKED`, check it is still `resolved`, lock the timer, check it is active and due, then `close_system` (4.9.4). That records a public `closed` event with actor `NULL`, audit `ticket_closed` with reason `auto`, and publishes `TicketClosed`, so the SLA handler stops all timers and the requester is notified.
- **Race safety:** if the requester confirms or reopens at the same moment, the ticket row lock serialises the two. The loser sees a status other than `resolved` and does nothing (`tests/integration/test_scheduler_idempotency.py`, `test_concurrent_auto_close_closes_once`).

#### `app/worker/jobs/protected_action_expiry.py`
- **Purpose:** expire protected-action requests nobody decided within 72 h.
- **`expired_ids`:** `pending` requests with `expires_at <= now`, up to 100.
- **`expire(session, clock, request_id) -> bool`:**
  1. Lock the request `SKIP LOCKED` and re-check it is still pending and expired.
  2. Set status `expired`; audit `protected_action_expired` (no actor, security limited).
  3. Notify the **requester** with kind `protected_action_decided` ("The request to deactivate Super Admin X expired"), template `protected_action_decided`, **critical**. `ACTION_VERBS` is imported from `notification_handlers.py`.
- **Note:** an approval or rejection notifies the requester **and** the Super Admins, but an expiry notifies only the requester. That matches the B19 row in `CLAUDE.md` ("requester P+E+C").

#### `app/worker/jobs/housekeeping.py`
- **Purpose:** delete data that is no longer needed.
- **Constants:**

  | Constant | Value | Deletes |
  |---|---|---|
  | `UNLINKED_ATTACHMENT_AGE` | 24 h | uploads never attached to a ticket, **and their files** |
  | `EMAIL_TOKEN_AGE` | 7 days | email tokens used or expired more than 7 days ago |
  | `REFRESH_TOKEN_AGE` | 30 days | refresh tokens revoked or expired more than 30 days ago |
  | `RATE_LIMIT_AGE` | 1 day | old rate-limit windows |
- **Functions:**
  - `purge_attachments(session, storage, now)`: locks up to 100 old unlinked rows `SKIP LOCKED`, deletes them, **commits**, and only then deletes the files. If the commit failed, no file is lost; if a file delete fails, it is logged and an orphan file remains. Rows first, then files (`CLAUDE.md` B19).
  - `purge_email_tokens`, `purge_rate_limits`: bulk `DELETE ... RETURNING id`.
  - `purge_refresh_tokens`: deletes old tokens, **except** one that is still referenced by a newer, not-yet-old token's `replaced_by_id`. Keeping that chain intact lets reuse detection (8.2) keep working.
  - `housekeeping(session, clock, storage)`: runs all four and commits.
- **`run`:** builds the storage with `build_storage(context.settings)`.
- **Not purged:** `email_outbox` (including rendered bodies that contain one-time links, 13.0 #19), `notifications`, `digest_items`, `escalation_events`. `audit_log` and `ticket_events` are kept on purpose (immutable). See 13.0 #31.

#### `app/worker/jobs/digest.py` (R2-C2)
- **Purpose:** send each daily-digest user one email per IST day. The step-by-step trace is flow 8.7.
- **Constants:** `DIGEST_TEMPLATE = "notification_digest"`, `MAX_ITEMS = 50`, `BATCH_SIZE = 100`, `DATE_FORMAT = "%d %b %Y"`.
- **Functions:**
  - `due_users(session, now)`: users whose preference is `daily_digest`, with `digest_hour <=` the current IST hour, pending items (not sent, not dropped), and no digest row for today's IST date.
  - `visible_tickets(session, actor, ticket_ids)`: the tickets among those ids the user can see **now** (`visible_ticket_clause`).
  - `item_entry(notification, ticket)`: `{text, ticket_id}`. For a confidential ticket the text is replaced with `confidential_text` ("Update on IBX-..."), even if the stored notification text was not masked.
  - `send_digest(session, clock, user_id) -> bool`:
    1. Lock the user's pending items `SKIP LOCKED`.
    2. If the user is gone or inactive, drop them all.
    3. Drop items about tickets the user can no longer see.
    4. Insert the `notification_digests` row with `ON CONFLICT DO NOTHING` (one per user per day).
    5. Mark the kept items sent.
    6. `enqueue_email` with up to 50 entries and `more` = the rest.
  - `run`: commit after `due_users`, then after each user.
- **Edge case:** if a user switches from `daily_digest` to `immediate` or `off` while items are pending, `due_users` never selects them again. The items stay pending forever and are neither sent nor dropped (13.0 #32).

#### `app/worker/jobs/send_outbox.py`
- **Purpose:** deliver queued emails. It runs **last**, so emails queued by the earlier jobs in the same tick go out at once.
- **Constants:** `BATCH_SIZE = 20`, `MAX_ATTEMPTS = 5`, `MAX_ERROR_LENGTH = 1000`, `BACKOFF = (1 min, 5 min, 30 min, 120 min)`.
- **`send_outbox(session, clock, sender)`:** up to 20 times: lock **one** due `pending` row (oldest first, `FOR UPDATE SKIP LOCKED`), deliver it, commit. Claiming one row at a time keeps each row locked until its own commit, so a second worker can never pick it up, and a crash re-sends at most the one email in flight (13.0 #36, fixed).
- **`_deliver(row, sender, now)`:** builds `OutgoingEmail` from the stored subject and bodies (already rendered when queued) and calls `sender.send`. On success: `sent`, `sent_at`, error cleared.
- **`_record_failure`:** `attempts + 1`, `last_error` = `"<ExceptionType>: <message>"` (cut to 1,000 characters). After 5 attempts, `failed`; otherwise `next_attempt_at = now + BACKOFF[attempts - 1]`.
- **Delivery guarantee:** *at least once*: if the process dies after the SMTP server accepted the message but before the commit, that one row is still `pending` and is sent again.
- **`_redact_token(row)`:** when a row reaches a final state (`sent` or `failed`), a `token` in its context is replaced by `[redacted]` in the context and both bodies. Verification and reset links therefore do not stay in the database (13.0 #19, fixed). Rows still waiting for a retry keep the token, because they must be sent.

### 4.12 Seed data and CLI

#### `app/seed/__init__.py`
- Empty package marker.

#### `app/seed/data.py`
- **Purpose:** the demo organisation (Appendix S of the build guide) as **plain data**. There is no database code in this file.
- **Constants:** `SEED_PASSWORD = "Ibotix2026Demo"` (every seeded user) and `EMAIL_DOMAIN = "ibotix.ai"`.
- **`email_for(name)`:** `"Asha Verma"` → `asha.verma@ibotix.ai`.
- **Seed dataclasses:** `CategorySeed`, `DepartmentSeed` (code, name, categories, contact), `PersonSeed` (name, department, title, role, Spoke departments, state; `email` property), `SignupSeed`, `GrantSeed`, `TicketSeed`.
- **Step dataclasses:** one per workflow action, each with `by` (who acts) and `hours_ago`: `Acknowledge`, `Assign`, `StartWork`, `AskRequester`, `Hold`, `Comment`, `AddCollaborator`, `Resolve`, `ConfirmClosure`, `Reopen`, `Cancel`, `Transfer`. `TicketStep` is their union.
- **`DEPARTMENTS`** (9):

  | Code | Name | Categories (confidential marked *) | Escalation contact |
  |---|---|---|---|
  | IT | IT & Infrastructure | Hardware, Software & Licences, Network & VPN, Access Request | Arjun Malhotra |
  | ENG | Engineering / Product | Build & CI, Dev Environment, Product Bug | Nikhil Bose |
  | HR | HR / People Operations | Employee Records*, Payroll, Leave & Attendance, Onboarding | Kavya Menon |
  | ADM | Administration & Facilities | Facilities, Travel & Transport | Suresh Pillai |
  | FIN | Finance & Accounts | Reimbursement, Invoices & Payments, Budget Request | Anil Desai |
  | SEC | Information Security / Compliance | Security Incident*, Phishing & Malware, Access Review | Pooja Reddy |
  | SAL | Sales / Business Development | CRM Access, Proposal Support | none |
  | OPS | Project Delivery / Operations | Project Staffing, Delivery Escalation | Manish Agarwal |
  | LEG | Legal / Contracts | Contract Review*, NDA Request, Compliance Query | Deepa Krishnan |

- **`PEOPLE`** (29):
  - employees and Spokes; for example Rohan Mehta is a Spoke of IT and ENG, and Neha Kapoor of HR;
  - one Admin (Priya Nair) and two Super Admins (Karan Shah, Mira Kulkarni);
  - eight department heads (the escalation contacts);
  - users in every non-active state: pending approval (Kabir Sethi, Ritu Bansal, Farhan Qureshi), rejected (Nitin Saxena), deactivated (Gaurav Thakur), pending verification (Leena Das).
- **`SIGNUPS`:** their signup requests (one per role level, plus one rejection with a reason).
- **`GRANTS`:** Neha Kapoor on HR "Employee Records", Vikram Singh on SEC "Security Incident". `GRANT_ISSUER = "Karan Shah"`.
- **`TICKETS`** (17), chosen so every status and several SLA levels exist. They include:
  - untouched `new` tickets (one `critical` in SEC);
  - acknowledged, in progress with a comment, awaiting the requester, on hold;
  - resolved, closed with a rating, reopened, cancelled;
  - a confidential HR ticket;
  - a transferred ticket;
  - an assigned ticket with a collaborator.
- **Observations:**
  - ADM has no Spoke, so its `accepts_tickets` is false in the demo.
  - Leena Das (pending verification) gets no verification token; she would use "resend verification".

  **Unclear - needs confirmation** whether both are intended by Appendix S.

#### `app/seed/run.py`
- **Constants:** `ORG_AGE = 60 days` (when the organisation "was created"), `SIGNUP_AGE = 1 day`, `DECISION_AGE = 12 h`.
- **`SeedRefused`:** raised when `ENV=prod`.
- **`SeedResult(created, users, tickets)`.**
- **`seed(session, settings, clock)`:**
  1. Refuse in prod.
  2. **Idempotency marker:** if the first person's email already exists, return `created=False` and change nothing.
  3. `register_all()`, because the seed runs outside the API, but tickets must still trigger the SLA and notification handlers.
  4. `Seeder(...).run()`.
- **`Seeder`** uses its own `FrozenClock`, moved to each event's time with `_at(hours_ago)`, so tickets get realistic histories ("created 30 hours ago, acknowledged 28 hours ago"):
  - `_departments`, `_people` (one Argon2 hash computed once and reused), `_contacts`, `_spokes` (audited `spoke_mapping_added`), `_category_rows`;
  - `_grants`: through `ConfidentialGrantService`, so audits and notifications are real;
  - `_signups`: inserts the requests directly, with the rejection audited;
  - `_deactivations`;
  - `_ticket(item)`: creates the ticket through **`TicketService.create`**, then `_apply`s each step through the **real services** (`ProgressService`, `ClosureService`, `CommentService`, `CollaboratorService`, `TransferService`), matched with `match step: case Acknowledge(): ...`. Seeded data therefore follows every business rule, and includes timeline events, audit rows and notifications;
  - `_settle(numbers)`: at the real "now", runs `Timers.reconcile` and `recompute_ticket` for each ticket, then one `SlaScanner.run()`. Old tickets get the escalation levels and alerts they would have accumulated.
- **Does not commit;** the CLI does.

#### `app/cli.py`
- **Purpose:** operator commands: `python -m app.cli <command>`.
- **Constants:**
  - `ADMIN_PASSWORD_ENV = "ADMIN_PASSWORD"`;
  - `DEFAULT_DEPARTMENT = "ADM"` and `DEFAULT_DEPARTMENT_NAME`;
  - `BACKEND_ROOT`;
  - `RESETTABLE = {dev, test}`.
- **`CliContext(session_factory, settings, clock, out, environ, prompt)`:** everything the commands need, injected so tests can pass fakes. Output goes through `context.out.write`, never `print` (`CLAUDE.md`).
- **Commands:**

  | Command | Function | What it does |
  |---|---|---|
  | `create-super-admin --email --name [--department ADM] [--department-name ...]` | `create_super_admin` | Validates the inputs with the API's own types (`NormalizedEmail`, `PersonName`, `DepartmentId`, `OrgName`). Reads the password from `ADMIN_PASSWORD` or prompts with `getpass`, and checks it with `password_policy_error`. Refuses an existing email. Creates the department if missing (active), then an **active, verified, approved Super Admin**. Audits `super_admin_created` (security limited, no actor). This is how the first account is made on a fresh database. |
  | `seed` | `seed_data` | `seed(...)`, then commit. Prints "Seeded N users and M tickets" or "already present". Refused in prod. |
  | `reset-db` | `reset_db` | dev and test only: `DROP SCHEMA public CASCADE`, `CREATE SCHEMA public`, then `alembic upgrade head`. **Destroys all data.** |
  | `export-openapi <path>` | `export_openapi` | Writes `create_app(settings).openapi()` as sorted, indented JSON. |
  | `mfa-reset --email` | `mfa_reset` | `MfaService.reset`: clears a user's MFA so they can enrol again (for a lost phone). |
- **`build_parser`**, **`run(argv, context)`** (the testable entry point) and **`main(argv=None)`** (builds the real context with `SessionLocal`, `SystemClock`, `sys.stdout`, `os.environ` and `getpass.getpass`). Exit code 0 on success, 1 on a handled failure.

### 4.13 Email templates (`app/templates/email/`)

Every email has a **subject** in `app/services/email_templates.py` (`SUBJECTS` or `NOTIFICATION_SUBJECTS`) and **two files**: `<name>.txt.j2` (plain text) and `<name>.html.j2` (HTML). They are rendered by `render_email` with `StrictUndefined`, so a missing variable is an error, and with HTML autoescaping, so a ticket title cannot inject markup. Every context also gets `frontend_base_url`. Notification emails get `name`, the recipient's name, from `Notifier.send`.

**Base layouts:**
- `_ticket.txt.j2` and `_ticket.html.j2`: greeting, `text`, an empty `{% block detail %}`, then ticket number, title, department, status and priority, and a link `<FRONTEND_BASE_URL>/tickets/<ticket number>`. Most ticket templates are a single line, `{% extends "_ticket.txt.j2" %}`.

**Account emails** (rendered from contexts built in the signup and auth services):

| Template | Context | Content |
|---|---|---|
| `verify_email` | `name`, `token`, `expires_hours` | link `/verify-email?token=<urlencoded>` |
| `password_reset` | `name`, `token`, `expires_minutes` | link `/reset-password?token=...`. Used by `AuthService._enqueue_reset_email`. |
| `account_exists_notice` | `name` | someone tried to sign up with your address; links to login and forgot password |
| `signup_approved` | `name` | you can sign in |
| `signup_rejected` | `name`, `reason` (nullable) | the reason line only when present; reapply link |

**Ticket notification emails** (kind = template name):

| Template | Extra detail block |
|---|---|
| `ticket_created`, `ticket_assigned`, `status_changed`, `transferred`, `closed`, `reopened`, `cancelled`, `collaborator_added`, `sla_warning`, `escalation`, `requester_reminder`, `hold_review_due` | none (base layout only) |
| `ticket_acknowledged` | owner, and ETA or "Next update by" |
| `comment_added` | "<author> wrote:" and the comment body |
| `eta_changed` | "The ETA was extended/changed from X to Y" |
| `resolved` | the resolution summary and a link to confirm or reopen |
| `confidential_ticket_update` | **replaces all of the above for confidential tickets**: "There is an update on a confidential ticket", with only number, department, status and priority. No title, comment or resolution. |

**Account and administration notifications:** `signup_pending` (applicant, email, requested role, department), `user_deactivated_open_tickets` (user name, open-ticket count), `protected_action_requested` (requester, action, target), `protected_action_decided` (action, target, status approved, rejected or expired), `confidential_grant_changed` (granted or revoked, category).

**Digest:** `notification_digest`: date, count, a list of items (text plus a link when the item has a ticket) and "and N more".

**Tests:** `tests/unit/test_email_templates.py` (every account template renders, HTML escapes, tokens are URL-encoded, a missing value raises) and `tests/unit/test_email_masking.py` (every notification subject has a case; confidential emails are masked).

### 4.14 Tests (`tests/`)

**108 Python files.** At the release gate, 2,197 tests passed (13.0 and section 12). All tests run against a **real PostgreSQL** database (`TEST_DATABASE_URL`). Mocks are used only for the clock (`FrozenClock`) and email (`InMemorySender`).

#### Shared infrastructure

##### `tests/conftest.py`
- **Constants:** `FROZEN_NOW = 2026-10-27 04:30 UTC` (10:00 IST), `MIGRATION_SEEDED_TABLES = {policy_versions}`, `IMMUTABLE_TABLES = {audit_log, ticket_events}` (truncated in cleanup, because their triggers block DELETE).
- **Fixtures:**

  | Fixture | Scope | What it does |
  |---|---|---|
  | `test_database_url` | session | `Settings(env=test).test_database_url`; refuses anything that is not PostgreSQL |
  | `migrated_engine` | session | drops and recreates the `public` schema, then `alembic upgrade head`. **Every test run starts from a freshly migrated database**, which also tests the migrations. |
  | `isolated_env` | autouse | removes every setting's environment variable, `chdir`s into a temporary folder (so no `.env` is read) and clears the `get_settings` cache |
  | `db` | function | one connection, an outer transaction, and a `Session` with `join_transaction_mode="create_savepoint"`. Service and route "commits" become savepoint releases, and **everything is rolled back after the test**. Fast and isolated. |
  | `committed_db` | function | a real session that really commits, for concurrency tests. Cleanup deletes policy versions above 1, clears escalation contacts, truncates `ticket_events`, and deletes every other table in reverse dependency order. |
  | `clock` | function | `FrozenClock(FROZEN_NOW)` |
  | `settings` | function | `Settings(env=test)` |
  | `client` | function | `create_app(settings)` with `get_db` overridden to `transactional(db)` and `get_clock` to the frozen clock, wrapped in FastAPI's `TestClient` |
- **Cleanup of immutable tables:** both immutable tables are truncated by `committed_db` itself. Before the fix of 13.0 #33, six test files truncated `audit_log` by hand.
- **Test function:** `test_database_url` checks the fixture.

##### `tests/factories.py`
- **Plain functions** (no factory library) that insert rows directly with the ORM and flush:
  - `make_department`, `make_user` (placeholder password hash unless one is given), `make_category`, `make_spoke_assignment`, `make_confidential_grant`;
  - `make_signup_request`, `make_email_token`, `make_refresh_token`, `make_protected_action`, `make_rate_limit_hit`, `make_policy_version`;
  - `make_ticket`: fills status-dependent fields (owner for owned statuses, assignee, `resolved_at` and so on); takes `eta`, `escalation_level`, `update_overdue`;
  - `make_ticket_counter`, `make_collaborator`, `make_ticket_event`, `make_attachment`, `make_timer`, `make_escalation_event`, `make_notification`, `make_outbox_email`.
- **`make_ticket_world(db)` → `TicketWorld`:**
  - departments IT and HR;
  - the 11 `WORLD_ACTORS`: requester, assignee, collaborator, spoke, spoke_with_grant, other_spoke, admin, admin_with_grant, super_admin, employee_with_grant, unrelated;
  - a normal and a confidential ("Investigations") category with grants;
  - four tickets: normal, secret, HR and closed.

  This is the standard fixture for visibility tests: one ticket, eleven viewpoints.
- **Important:** factory tickets have **no SLA timers** and bypass the services. Use `make_timer` or the real services when timers matter (`CLAUDE.md` B15).

##### `tests/scenarios/conftest.py` and `tests/scenarios/helpers.py`
- **`build_org(db)` → `Org`:** a small organisation (departments, people, HR and IT contacts) with a real Argon2 password.
- **`Portal`:** a test driver that speaks HTTP like the frontend:
  - `get`, `post` and `delete` as a named person;
  - `raise_ticket`, `acknowledge`;
  - **`advance(by)` and `set_time(at)`** to move the frozen clock;
  - **`run_jobs(*names)` and `scan()`** to run worker jobs in-process;
  - inspection helpers: `notified`, `notification_count`, `steps`, `step_keys`, `audit_actions`, `emails_to`.

  Scenarios read like the user stories in the build guide.

#### Test files by folder

**`tests/unit/`** (fast; pure functions or small database checks):

| File | What it proves |
|---|---|
| `test_allowed_actions.py` | the `ACTION_RULES` matrix for every actor class and status, confidential or not; the requester never resolves; reopen window and count use policy values |
| `test_audit.py` | `to_json_value` conversions and rejections; `record` uses the clock and request context; `audit_log` and `ticket_events` reject UPDATE and DELETE |
| `test_clock.py` | `SystemClock` is aware UTC; `FrozenClock` advance and set; IST conversion |
| `test_config.py` | defaults, comma lists, empty MFA roles disable MFA, wildcard CORS rejected, prod rules, `.env` read |
| `test_db_session.py` | `transactional` commits and rolls back; PostgreSQL with `pg_trgm`; database enums match the contract |
| `test_due_time.py`, `test_working_time.py` | scaling; calendar versus business due times; business days in IST, not scaled; working time skips holidays and custom hours |
| `test_email_masking.py`, `test_email_templates.py` | see 4.13 |
| `test_errors.py` | every `ErrorCode` has a status; helper details and fields |
| `test_events.py` | events are frozen; handlers run in registration order, dispatch by exact type, share the caller's transaction; the handler count is compared with a freshly registered bus |
| `test_export_writers.py` | `safe_cell` formula neutralising; CSV, XLSX and PDF layout; valid unique sheet titles |
| `test_flags.py` | `compute_permissions` for every role and the Admin toggle |
| `test_levels.py` | `timer_level` thresholds; `apply_levels`; `build_sla_state` labels |
| `test_mfa_service.py` | MFA token round trip and expiry; MFA and access tokens are not interchangeable; challenge rules; setup, confirm, verify and reset; endpoints hidden when off |
| `test_models_identity_org.py`, `test_models_ticket.py` | lowercase enum storage, server defaults, CHECK and UNIQUE constraints (department code format, case-insensitive email, ticket number format, rating range, escalation level range, and others) |
| `test_pagination.py` | page bounds, sort whitelist, `fetch_page` |
| `test_permissions_signup.py`, `test_permissions_users.py` | the approval chain; account management rules; minimum two Super Admins |
| `test_relationships.py`, `test_visibility.py` | `load_actor`; relationship flags; visibility for every actor class; **`visible_ticket_clause` and `is_visible` agree** (`test_clause_and_loaded_decision_agree`) |
| `test_security.py` | Argon2 hashing, password policy, access-token claims (no role claims) and expiry |
| `test_workflow_common.py` | IST formatting; `Workflow.begin` locks, returns 404 for hidden tickets, classifies denials |

**`tests/api/`** (HTTP through `TestClient`, one file per router area): `test_auth.py` (37 tests: login, cookies, refresh rotation and reuse, logout, forgot and reset), `test_mfa.py`, `test_signup.py`, `test_signup_approvals.py`, `test_users.py`, `test_admins.py`, `test_protected_actions.py`, `test_departments.py`, `test_categories.py`, `test_confidential_grants.py`, `test_policy.py`, `test_calendar.py`, `test_ticket_create.py` (numbering, IST year boundary, category and attachment rules), `test_ticket_list.py` (scopes, filters, sorting), `test_ticket_detail.py` (visibility matrix; **hidden and missing give identical 404s**), `test_ticket_timeline.py`, `test_comments.py`, `test_collaborators.py`, `test_attachments.py` (types, sniffing, size, file names, download access), the four `test_workflow_*.py` files (every action, its validation, actor classes and wrong-status 409s), `test_notifications.py`, `test_notification_preferences.py`, `test_audit.py`, `test_dashboards.py`, `test_kpis.py`, `test_exports.py`, `test_saved_views.py`, `test_health.py` (probes and CORS), `test_error_envelope.py` (every error code's envelope; 405 becomes 404), and **`test_contract_shapes.py`** (950 lines: seeds once per module and checks every response against Appendix A field by field with `Shape` checkers).

**`tests/integration/`** (several components together, often with `committed_db` and threads): `test_sla_handlers.py` (each event's timer effect), `test_sla_scan.py` (steps per priority, catch-up after an outage), `test_escalation_recipients.py` (recipient and fallback chains), `test_notification_handlers.py` (30 tests: recipients and masking per event), `test_outbox.py` (rendering, retries, backoff), `test_digest_job.py`, `test_reminders.py`, `test_auto_close.py`, `test_housekeeping.py`, `test_business_mode.py` (mode resolution; **the SQL `working_seconds` matches the Python**), `test_ticket_numbers.py` (concurrent creations), `test_scheduler_idempotency.py` (two scanners, auto-closers and reminder jobs act once), `test_worker_loop.py` (job order, a failing job does not stop the tick, heartbeat, SIGTERM, `main()` registers the event handlers), `test_seed.py` (counts, every status, idempotent, logins, confidential visibility), `test_cli.py`.

**`tests/scenarios/`** (20 numbered user stories from the build guide, through `Portal`): 01 raise and route, 02 acknowledge, 03 no-ack escalation L1→L3, 04 delegation, 05 progress and stale, 06 ETA extension, 07 transfer, 08 resolve, confirm and reopen limits, 09 Admin limits, 10 a Super Admin manages an Admin, 11 unauthorised access is a plain 404, 12 the signup chain, 13 protected actions, 14 confidential tickets, 15 critical priority, 16 escalation fallback, 17 scheduler restart catch-up, **18 concurrency** (20 parallel creations, two acknowledgements, two schedulers, two outbox workers), 19 auto-close, 20 MFA toggle.

**`tests/security/`:**
- **`test_authorization_matrix.py`:** **every route in `routes.txt` × 6 actors** (anonymous, employee, Spoke, Admin, Super Admin, Admin with the toggle off) against expected outcomes: `U` 401, `F` 403, `H` 404, `A` allowed. Two meta-tests fail if a contract route, or any route exposed by the app, has no matrix entry. A new endpoint therefore cannot be added without deciding its access rules.
- **`test_confidentiality_leaks.py`:** one confidential ticket, checked from outsiders' and insiders' viewpoints across lists, counts, dashboards, search, detail, exports in every format, notifications and emails. The hidden ticket must match a missing one exactly.
- **`test_auth_hardening.py`** (17 tests): login and reapply lockouts; every rate limit; refresh-token reuse revokes the family; foreign `Origin` refused; tampered tokens; a deactivated user's token stops working; no account enumeration; **public endpoints never return 401**; security headers and `no-store`; oversized bodies rejected before parsing; CORS only for configured origins; **the role is never taken from the token** (always reloaded from the database).

**`tests/perf/`:**
- `test_list_performance.py`: inserts a large data set via `scripts/perf_seed.py`; asserts the ticket list p95 is under 300 ms and that list queries **avoid sequential scans** on `tickets` (`EXPLAIN`).
- `test_kpi_performance.py`: KPI p95 under 500 ms with 50,000 tickets.
- `tests/perf/conftest.py` **skips them when coverage is active** (`--cov`), because instrumentation distorts timings (13.0 #34). Run them with plain `pytest tests/perf`.

## 5. Code-Section Walkthrough

To avoid repeating every function twice, the step-by-step walkthroughs sit next to each file in section 4. Each one gives the function's location, inputs and outputs, the steps, the tables and services it touches, and its error cases. This index points to the most important ones.

| Code | Location | Walkthrough |
|---|---|---|
| `Settings` validators, `get_settings` | `app/core/config.py` | 4.3 |
| `get_db` / `transactional` (per-request commit) | `app/core/db.py` lines 26-37 | 4.3 |
| `ApiError`, `error_response`, `_validation_fields` | `app/core/errors.py` | 4.3 |
| `EventBus.register` / `publish` | `app/core/events.py` lines 150-171 | 4.3 |
| `create_access_token`, `decode_access_token`, `dummy_verify` | `app/core/security.py` | 4.3 |
| `RequestContextMiddleware`, `BodySizeLimitMiddleware` | `app/core/request_context.py`, `security_headers.py` | 4.3 |
| `create_app` | `app/main.py` lines 50-101 | 4.4 |
| `get_actor` (authentication of every request) | `app/api/deps.py` lines 40-52 | 4.4 |
| `Worker.tick` / `_run_job` / `_beat` | `app/worker/main.py` | 4.4 |
| `LocalStorage.save` / `_path` | `app/integrations/storage/local.py` | 4.4 |
| `compute_permissions` | `app/policy/flags.py` lines 33-54 | 4.6 |
| `is_visible`, `visible_ticket_clause` | `app/policy/visibility.py` | 4.6 |
| `ACTION_RULES`, `is_action_allowed`, `classify_denial` | `app/policy/allowed_actions.py` | 4.6 |
| `report_scope` | `app/policy/reports.py` lines 29-41 | 4.6 |
| `filter_clauses`, `apply_sort`, `mine_clause` | `app/queries/tickets.py` | 4.7 |
| `_first_event`, `trend_statement`, `snapshot_statement` | `app/queries/kpis.py` | 4.7 |
| `AuthService.login`, `refresh`, `reset_password` | `app/services/auth.py` | 4.9.1 |
| `MfaService.verify`, `confirm` | `app/services/mfa.py` | 4.9.1 |
| `SignupService.signup`, `verify_email`, `approve` | `app/services/signup.py` | 4.9.1 |
| `UserService.deactivate`, `AccountEffects.deactivate` | `app/services/users.py`, `protected_actions.py` | 4.9.1 |
| `ProtectedActionService.request`, `approve` | `app/services/protected_actions.py` | 4.9.1 |
| `RateLimiter.hit` | `app/services/rate_limit.py` lines 37-54 | 4.9.1 |
| `PolicyAdminService.replace` | `app/services/policy_admin.py` | 4.9.2 |
| `CalendarService.update`, `add_holiday` | `app/services/calendar.py` | 4.9.2 |
| `TicketService.create` | `app/services/tickets.py` lines 37-97 | 4.9.3 |
| `AttachmentService.upload`, `_downloadable` | `app/services/attachments.py` | 4.9.3 |
| `TicketPresenter.present`, `TicketReadService.filters`, `timeline` | `app/services/ticket_reads.py` | 4.9.3 |
| `CommentService.add` | `app/services/comments.py` lines 37-85 | 4.9.3 |
| `Workflow.begin` / `record` / `publish` | `app/services/workflow/common.py` | 4.9.4 |
| `ProgressService.acknowledge`, `assign`, `change_status` | `app/services/workflow/progress.py` | 4.9.4 |
| `ClosureService.reopen`, `close_ticket` | `app/services/workflow/closure.py` | 4.9.4 |
| `TransferService.transfer` | `app/services/workflow/transfer.py` | 4.9.4 |
| `add_working_time`, `calculate_due` | `app/services/sla/working_time.py`, `due_time.py` | 4.9.5 |
| `Timers.reconcile` and the starters | `app/services/sla/timers.py` | 4.9.5 |
| `build_sla_state` | `app/services/sla/sla_object.py` | 4.9.5 |
| `resolve_recipients`, `record_step` | `app/services/sla/escalation.py` | 4.9.5 |
| `SlaScanner.run` / `_process`, `candidate_timers` | `app/services/sla/scanner.py` | 4.9.5 |
| SLA event handlers (`_apply`) | `app/services/handlers/sla_handlers.py` | 4.9.6 |
| Notification planners, `visible_only` | `app/services/handlers/notification_handlers.py`, `recipients.py` | 4.9.6 |
| `ticket_message`, `Notifier.send` | `app/services/notifications.py` | 4.9.6 |
| `KpiService.report` | `app/services/kpis.py` lines 94-148 | 4.9.7 |
| `ExportService.export`, `safe_cell` | `app/services/exports/` | 4.9.7 |
| `normalize_query`, `SavedViewService` | `app/services/saved_views.py` | 4.9.7 |
| `_set_refresh_cookie`, `login` (returned-error style) | `app/api/routers/auth.py` | 4.10 |
| `ticket_list_query` / `TicketListParams` | `app/api/params.py` | 4.10 |
| `download_attachment` headers | `app/api/routers/attachments.py` | 4.10 |
| `export_report` streaming | `app/api/routers/exports.py` | 4.10 |
| `health.worker` staleness check | `app/api/routers/health.py` | 4.10 |
| `send_reminder`, `close_due`, `expire` (lock, re-check, act) | `app/worker/jobs/reminders.py`, `auto_close.py`, `protected_action_expiry.py` | 4.11 |
| `purge_attachments`, `purge_refresh_tokens` | `app/worker/jobs/housekeeping.py` | 4.11 |
| `due_users`, `send_digest` | `app/worker/jobs/digest.py` | 4.11, 8.7 |
| `send_outbox`, `_record_failure` | `app/worker/jobs/send_outbox.py` | 4.11 |
| `seed`, `Seeder._apply`, `_settle` | `app/seed/run.py` | 4.12 |
| `create_super_admin`, `run` | `app/cli.py` | 4.12 |


## 6. Data Layer

### 6.1 Conventions shared by every table

| Convention | Detail | Source |
|---|---|---|
| Primary keys | UUID `id` generated in Python (`uuid.uuid4`), except: `departments.id` (the department code), `ticket_counters` (department code + year), `ticket_collaborators` (ticket + user), `worker_heartbeat.name`, `business_calendar.id` (always 1), `notification_preferences.user_id` | `app/models/base.py` `UuidPk` |
| Timestamps | Always `timestamptz`, always set by the service from the injected clock (no database defaults for `created_at` and `updated_at`) | `Base.type_annotation_map`, `Timestamps` |
| Enum columns | `VARCHAR(32)` plus a CHECK constraint listing the lowercase values | `enum_type` |
| Soft deletes | Rows are not deleted when a business object "goes away". `users.state = deactivated`, `categories.is_active = false`, `spoke_assignments.revoked_at`, `confidential_grants.revoked_at`, `holidays.removed_at`, `saved_views.deleted_at` | the models below |
| Deletes that do happen | Expired tokens and rate-limit rows, abandoned unlinked attachments (housekeeping job), and collaborator rows on removal | 6.4 |
| Relationships | Foreign keys only; no ORM `relationship()` | all model files |

Notation in the tables below: **PK** primary key, **FK** foreign key, **UQ** unique, **IX** indexed, **NN** not null.

### 6.2 Tables

#### Identity and accounts

**`users`** (`User`, `app/models/identity.py`): everyone with an account, in any state.

| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `email` | varchar(320) | NN; CHECK `email = lower(email)`; UQ on `lower(email)` |
| `name` | varchar(120) | NN |
| `title` | varchar(120) | nullable (job title) |
| `password_hash` | varchar(255) | NN (Argon2id) |
| `home_department_id` | varchar(6) | NN, FK → `departments.id`, IX |
| `global_role` | enum `global_role` | NN, default `employee`; CHECK `global_role <> 'spoke'` (Spoke is never a stored role) |
| `state` | enum `account_state` | NN |
| `email_verified_at` | timestamptz | nullable |
| `approved_by_id`, `approved_at` | UUID FK → `users`, timestamptz | nullable |
| `deactivated_by_id`, `deactivated_at`, `deactivation_reason` | UUID FK → `users`, timestamptz, text | nullable |
| `failed_login_count` | int | NN, default 0, CHECK ≥ 0 |
| `locked_until` | timestamptz | nullable (login lockout) |
| `last_login_at` | timestamptz | nullable |
| `mfa_enabled` | bool | NN, default false |
| `mfa_secret_encrypted` | text | nullable (Fernet-encrypted TOTP secret) |
| `mfa_failed_count` | int | NN, default 0, CHECK ≥ 0 |
| `theme` | enum `theme` | nullable |
| `created_at`, `updated_at` | timestamptz | NN |

**`signup_requests`** (`SignupRequest`): a person's request to join, and its decision.

| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | NN, FK → `users`, IX; partial UQ: one `pending` request per user |
| `requested_role` | enum | NN; CHECK `<> 'spoke'` |
| `requested_department_id` | varchar(6) | NN, FK → `departments` |
| `approved_role`, `approved_department_id` | enum, varchar(6) FK | nullable (the decider may change both) |
| `status` | enum `signup_status` | NN, default `pending` |
| `decided_by_id`, `decision_reason`, `decided_at` | UUID FK → `users`, text, timestamptz | nullable |
| `created_at`, `updated_at` | timestamptz | NN |

**`email_tokens`** (`EmailToken`): one-time links for email verification and password reset.

| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | NN, FK → `users` |
| `purpose` | enum `email_token_purpose` | NN (`verify`, `reset`) |
| `token_hash` | varchar(64) | NN, UQ (SHA-256 of the raw token; the raw token exists only in the email) |
| `expires_at`, `used_at` | timestamptz | `expires_at` NN |
| `created_at`, `updated_at` | timestamptz | NN |

**`refresh_tokens`** (`RefreshToken`): login sessions.

| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | NN, FK → `users` |
| `family_id` | UUID | NN, IX. All tokens descended from one login share a family; reuse of a rotated token revokes the family (`docs/SECURITY.md`). |
| `token_hash` | varchar(64) | NN, UQ |
| `expires_at`, `revoked_at` | timestamptz | `expires_at` NN |
| `replaced_by_id` | UUID | FK → `refresh_tokens.id` (the next token after rotation) |
| `user_agent`, `ip_address` | varchar(512), varchar(45) | nullable |
| `created_at`, `updated_at` | timestamptz | NN |

**`mfa_recovery_codes`** (`MfaRecoveryCode`): `id` PK; `user_id` NN FK → `users`; `code_hash` varchar(255) NN (SHA-256, per `CLAUDE.md` B21); `used_at` (a code is retired by setting it); `created_at`, `updated_at`.

**`protected_action_requests`** (`ProtectedActionRequest`): requests to deactivate or demote a Super Admin, which another Super Admin must approve.

| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `kind` | enum `protected_action_kind` | NN |
| `target_user_id`, `requested_by_id` | UUID | NN, FK → `users` |
| `status` | enum | NN, default `pending` |
| `decided_by_id`, `decided_at` | UUID FK, timestamptz | nullable. CHECK `decider_is_independent`: the decider is neither the requester nor the target. |
| `reason` | text | NN |
| `decision_reason` | text | nullable |
| `expires_at` | timestamptz | NN (the worker expires old requests) |
| `created_at`, `updated_at` | timestamptz | NN |

**`rate_limit_hits`** (`RateLimitHit`): fixed-window counters. `id` PK; `key` varchar(255) NN (rule plus subject, for example a login per IP; the exact key format is in `app/services/rate_limit.py`, Part 4); `window_start` timestamptz NN; `count` int NN ≥ 0; UQ (`key`, `window_start`).

#### Organisation and policy

**`departments`** (`Department`, `app/models/org.py`)

| Column | Type | Rules |
|---|---|---|
| `id` | varchar(6) | PK; CHECK `^[A-Z]{2,6}$` (for example `IT`, `HR`) |
| `name` | varchar(120) | NN |
| `is_active` | bool | NN, default **false**. Cannot be activated without an active Spoke (rule in `app/services/departments.py`). |
| `escalation_contact_user_id` | UUID | FK → `users`, IX, nullable |
| `sla_mode` | enum (`calendar`, `business`) | nullable; null means inherit the policy (R2-C1) |
| `created_at`, `updated_at` | timestamptz | NN |

**`spoke_assignments`** (`SpokeAssignment`): who is a Spoke of which department, with history. `id` PK; `user_id` NN FK → `users`; `department_id` NN FK → `departments`; `granted_by_id` FK; `granted_at` NN; `revoked_by_id` FK; `revoked_at`. Partial UQ (`user_id`, `department_id`) WHERE `revoked_at IS NULL`.

**`categories`** (`Category`)

| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `department_id` | varchar(6) | NN, FK → `departments` |
| `name` | varchar(120) | NN; UQ (`department_id`, `lower(name)`) |
| `is_confidential` | bool | NN, default false. Tickets in a confidential category are confidential. |
| `is_active` | bool | NN, default true (deleting a category sets false) |
| `sla_mode` | enum | nullable (R2-C1) |
| `created_at`, `updated_at` | timestamptz | NN |

**`confidential_grants`** (`ConfidentialGrant`): extra people allowed to see a confidential category's tickets. `id` PK; `user_id` NN FK → `users`; `category_id` NN FK → `categories`; `granted_by_id`, `granted_at` NN; `revoked_by_id`, `revoked_at`. Partial UQ (`user_id`, `category_id`) WHERE `revoked_at IS NULL`.

**`policy_versions`** (`PolicyVersion`, `app/models/policy.py`): `id` PK; `version` int NN UQ, CHECK ≥ 1; `config` JSONB NN (keys in 4.5); `created_by_id` FK → `users` (null for the seeded version 1); `created_at` NN.

#### Tickets

**`tickets`** (`Ticket`, `app/models/ticket.py`)

| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `ticket_no` | varchar(32) | NN, UQ; CHECK `^IBX-[A-Z]{2,6}-[0-9]{4}-[0-9]{6}$`; trigram GIN index |
| `origin_department_code` | varchar(6) | NN; CHECK `^[A-Z]{2,6}$`. The department the number was issued for; it stays the same after a transfer. |
| `department_id` | varchar(6) | NN, FK → `departments` (current department) |
| `category_id` | UUID | FK → `categories`, nullable |
| `title` | varchar(120) | NN; trigram GIN index |
| `description` | text | NN |
| `requested_priority`, `priority` | enum | NN (what the requester asked for vs. the current priority) |
| `confidential` | bool | NN, default false |
| `status` | enum `ticket_status` | NN, default `new` |
| `requester_id` | UUID | NN, FK → `users` |
| `owner_id`, `assignee_id` | UUID | FK → `users`, nullable |
| `sla_started_at` | timestamptz | NN, IX (when the current SLA cycle began; reset on reopen and transfer) |
| `acknowledged_at` | timestamptz | nullable |
| `eta` | timestamptz | nullable, IX (promised resolution time) |
| `next_checkpoint_at` | timestamptz | nullable (used instead of the ETA when no ETA is given, per `CLAUDE.md` B12) |
| `last_team_update_at` | timestamptz | nullable |
| `hold_reason`, `hold_review_date` | text, timestamptz | nullable |
| `awaiting_since` | timestamptz | nullable |
| `resolution_summary`, `resolved_at` | text, timestamptz | nullable |
| `closed_at`, `close_reason` | timestamptz, enum `close_reason` | nullable |
| `cancel_reason` | text | nullable |
| `reopen_count` | int | NN, default 0, CHECK ≥ 0 |
| `feedback_rating` | smallint | nullable, CHECK 1 to 5 |
| `feedback_comment` | text | nullable |
| `escalation_level` | smallint | NN, default 0, CHECK 0 to 3 (cached from the SLA timers) |
| `update_overdue` | bool | NN, default false (cached) |
| `created_at`, `updated_at` | timestamptz | NN |

**`ticket_counters`** (`TicketCounter`): `department_code` varchar(6) and `year` int (composite PK, both checked); `last_value` int NN ≥ 0. Incremented with an upsert to allocate the next ticket number (`app/services/ticket_numbers.py`, Part 4).

**`ticket_collaborators`** (`TicketCollaborator`): `ticket_id` FK → `tickets` and `user_id` FK → `users` (composite PK; `user_id` also IX); `added_by_id` FK; `added_at` NN.

**`ticket_events`** (`TicketEvent`): the ticket timeline. **Immutable** (6.5).

| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `ticket_id` | UUID | NN, FK → `tickets`; IX (`ticket_id`, `at`) |
| `at` | timestamptz | NN |
| `actor_id` | UUID | FK → `users`, nullable (null = system) |
| `kind` | enum `ticket_event_kind` | NN (`comment`, `internal_note`, `audit`) |
| `action` | varchar(64) | nullable, for example `acknowledged`, `resolved`, `escalation` (lists in `CLAUDE.md` B15 to B19) |
| `detail` | text | full description for staff |
| `public_detail` | text | the version shown to non-staff (often without the reason) |
| `body` | text | comment text |
| `is_public` | bool | NN, default false |
| `data` | JSONB | structured extras (for example `timer_kind`, `cycle`, `level`) |

**`attachments`** (`Attachment`)

| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `ticket_id` | UUID | FK → `tickets`, nullable (null = uploaded but not yet linked) |
| `uploader_id` | UUID | NN, FK → `users` |
| `file_name` | varchar(255) | NN (sanitised original name, shown to users) |
| `content_type` | varchar(255) | NN |
| `size_bytes` | bigint | NN, CHECK ≥ 0 |
| `storage_key` | varchar(255) | NN, UQ (key in `LocalStorage`) |
| `sha256` | varchar(64) | NN |
| `scan_status` | enum `scan_status` | NN, default `pending` |
| `created_at` | timestamptz | NN; partial IX where `ticket_id IS NULL` |

#### SLA

**`sla_timers`** (`SlaTimer`, `app/models/sla.py`)

| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `ticket_id` | UUID | NN, FK → `tickets`; UQ (`ticket_id`, `kind`) |
| `kind` | enum `timer_kind` | NN |
| `cycle` | int | NN, default 1, CHECK ≥ 1 (incremented on restart) |
| `started_at` | timestamptz | NN |
| `warning_at`, `due_at`, `l3_at` | timestamptz | `due_at` NN. Level 1 at `warning_at`, 2 at `due_at`, 3 at `l3_at`. |
| `paused_at` | timestamptz | nullable |
| `paused_seconds` | int | NN, default 0, CHECK ≥ 0 |
| `level` | smallint | NN, default 0, CHECK 0 to 3 |
| `met_at`, `stopped_at` | timestamptz | nullable (a timer is active while both are null) |

Partial index `ix_sla_timers_active_due_at` on `due_at` WHERE `met_at`, `stopped_at` and `paused_at` are all null.

**`escalation_events`** (`EscalationEvent`): `id` PK; `ticket_id` NN FK → `tickets`; `timer_kind` enum NN; `cycle` int NN ≥ 1; `level` smallint NN 1 to 3; `step_key` varchar(64) NN (for example `L1`, `L2`, `L3`, `L3_REPEAT_2`, `CREATION_CONTACT`, `REMINDER`, `HOLD_REVIEW`); `at` NN, IX; `recipient_ids` UUID[] NN, default `{}`. UQ (`ticket_id`, `timer_kind`, `cycle`, `step_key`).

#### Notifications, email, worker

**`notifications`** (`Notification`, `app/models/notification.py`): `id` PK; `user_id` NN FK → `users`; `ticket_id` FK → `tickets` (nullable, IX); `kind` varchar(64) NN; `text` text NN (already masked for confidential tickets); `critical` bool NN default false; `dedupe_key` varchar(255) nullable, partial UQ (`user_id`, `dedupe_key`); `created_at` NN; `read_at`. IX (`user_id`, `read_at`, `created_at DESC`).

**`email_outbox`** (`EmailOutbox`)

| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `notification_id` | UUID | FK → `notifications`, nullable (null for account emails and digests) |
| `to_address` | varchar(320) | NN |
| `template` | varchar(64) | NN |
| `context` | JSONB | NN, default `{}` |
| `subject`, `body_text`, `body_html` | varchar(255), text, text | NN (rendered when queued) |
| `status` | enum `email_status` | NN, default `pending` |
| `attempts` | int | NN, default 0, CHECK ≥ 0 |
| `next_attempt_at` | timestamptz | NN; IX (`status`, `next_attempt_at`) |
| `last_error` | text | nullable |
| `sent_at`, `created_at` | timestamptz | `created_at` NN |

**`worker_heartbeat`** (`WorkerHeartbeat`): `name` varchar(64) PK (always `"worker"`); `last_seen_at` NN; `details` JSONB NN default `{}` (`{"jobs": {...}, "failed": [...]}`).

#### Release 2 tables

**`saved_views`** (`SavedView`): `id` PK; `owner_id` NN FK → `users`, IX; `name` varchar(80) NN; `query` JSONB NN (a validated ticket-list filter); `deleted_at`; `created_at`, `updated_at`. Partial UQ (`owner_id`, `lower(name)`) WHERE `deleted_at IS NULL`.

**`business_calendar`** (`BusinessCalendar`): `id` smallint PK, CHECK `id = 1`; `working_days` smallint[] NN, CHECK 1 to 7 entries, all within 1..7 (ISO weekdays, 1 = Monday); `work_start`, `work_end` time NN, CHECK start < end; `updated_by_id` FK → `users`; `updated_at` nullable.

**`holidays`** (`Holiday`): `id` PK; `holiday_date` date NN; `name` varchar(80) NN; `created_by_id` FK, `created_at` NN; `removed_by_id` FK, `removed_at`. Partial UQ (`holiday_date`) WHERE `removed_at IS NULL`.

**`notification_preferences`** (`NotificationPreference`): `user_id` UUID PK and FK → `users`; `non_critical_email` enum NN; `digest_hour` smallint NN, CHECK 0 to 23; `updated_at` NN.

**`notification_digests`** (`NotificationDigest`): `id` PK; `user_id` NN FK → `users`; `digest_date` date NN; `item_count` int NN; `created_at` NN. UQ (`user_id`, `digest_date`): one digest per user per IST day.

**`digest_items`** (`DigestItem`): `id` PK; `user_id` NN FK → `users`; `notification_id` NN FK → `notifications`, UQ; `digest_id` FK → `notification_digests`, IX; `queued_at` NN; `sent_at`, `dropped_at`. Partial IX (`user_id`, `queued_at`) WHERE `sent_at IS NULL AND dropped_at IS NULL`.

#### Database objects that are not tables

| Object | Created by | Purpose |
|---|---|---|
| Extension `pg_trgm` | `b02` | trigram search indexes |
| Function `reject_ticket_event_change()` + trigger `ticket_events_immutable` | `b04` | blocks UPDATE and DELETE on `ticket_events` |
| Function `reject_audit_log_change()` + trigger `audit_log_immutable` | `b05` | blocks UPDATE and DELETE on `audit_log` |
| Function `working_seconds(start_at, end_at)` | `r2c1` | seconds of working time between two instants, using the business calendar (defaults if the table is empty) and active holidays; used by the SLA scanner for business-mode repeat escalations |

### 6.3 ER diagram

Foreign keys to `users` that only record who did something (`approved_by_id`, `deactivated_by_id`, `granted_by_id`, `revoked_by_id`, `decided_by_id`, `added_by_id`, `created_by_id`, `updated_by_id`, `removed_by_id`, and `audit_log.actor_id`, `ticket_events.actor_id`) are omitted to keep the diagram readable.

```mermaid
erDiagram
    departments ||--o{ users : "home_department_id"
    users |o--o{ departments : "escalation_contact_user_id"
    departments ||--o{ spoke_assignments : ""
    users ||--o{ spoke_assignments : ""
    departments ||--o{ categories : ""
    categories ||--o{ confidential_grants : ""
    users ||--o{ confidential_grants : ""

    users ||--o{ signup_requests : "user_id"
    departments ||--o{ signup_requests : "requested / approved department"
    users ||--o{ email_tokens : ""
    users ||--o{ refresh_tokens : ""
    refresh_tokens |o--o| refresh_tokens : "replaced_by_id"
    users ||--o{ mfa_recovery_codes : ""
    users ||--o{ protected_action_requests : "target / requester"

    departments ||--o{ tickets : "department_id"
    categories |o--o{ tickets : "category_id"
    users ||--o{ tickets : "requester / owner / assignee"
    tickets ||--o{ ticket_collaborators : ""
    users ||--o{ ticket_collaborators : ""
    tickets ||--o{ ticket_events : "timeline"
    tickets |o--o{ attachments : "ticket_id (null = unlinked)"
    users ||--o{ attachments : "uploader_id"
    tickets ||--o{ sla_timers : "one per kind"
    tickets ||--o{ escalation_events : ""

    users ||--o{ notifications : ""
    tickets |o--o{ notifications : ""
    notifications |o--o{ email_outbox : "notification_id"
    tickets |o--o{ audit_log : "ticket_id"
    departments |o--o{ audit_log : "department_id"

    users ||--o{ saved_views : "owner_id"
    users ||--o| notification_preferences : ""
    users ||--o{ notification_digests : ""
    notifications ||--o| digest_items : ""
    notification_digests |o--o{ digest_items : ""
```

Tables with no foreign keys: `policy_versions` (only `created_by_id`), `rate_limit_hits`, `ticket_counters`, `worker_heartbeat`, `business_calendar` and `holidays` (only "who" columns).

### 6.4 Who reads and writes each table

Built from the code: "Writes" lists where rows are created (constructor, `insert`), updated (`update`, or assignment to an attribute of a loaded row) or deleted. "Reads" lists the modules that query the model. Paths are relative to `app/`.

| Table | Writes (file:line) | Reads (main modules) |
|---|---|---|
| `users` | create: `services/signup.py:105`, `cli.py:93`, `seed/run.py:155`. Update: `services/users.py:159` (state), `services/protected_actions.py:70` (state, role), `services/signup.py:163, 206, 220` (state, password, department), `services/auth.py:107` (login counters), `services/mfa.py:128` (MFA fields) | `policy/actors.py`, `services/me.py`, `services/auth.py`, `services/users.py`, `services/spokes.py`, almost every service that shows names |
| `signup_requests` | create: `services/signup.py:117, 211`, `seed/run.py:240`. Decide: `services/signup.py:284` | `services/signup.py`, `services/auth.py`, `services/dashboards.py`, `handlers/notification_handlers.py` |
| `email_tokens` | create: `services/auth.py:197`, `services/signup.py:381`. Mark used: `services/signup.py:371`. Delete expired: `worker/jobs/housekeeping.py:51` | `services/auth.py`, `services/signup.py` |
| `refresh_tokens` | create: `services/auth.py:300`. Revoke and rotate: `services/auth.py:165, 237, 317`, `services/protected_actions.py:76`. Delete expired: `worker/jobs/housekeeping.py:67` | `services/auth.py` |
| `mfa_recovery_codes` | create: `services/mfa.py:144`. Mark used: `services/mfa.py:255` | `services/mfa.py` |
| `protected_action_requests` | create: `services/protected_actions.py:175`. Decide: `services/protected_actions.py:293`. Expire: `worker/jobs/protected_action_expiry.py:46` | the same, plus `handlers/notification_handlers.py` |
| `rate_limit_hits` | upsert: `services/rate_limit.py:42`. Delete old: `worker/jobs/housekeeping.py:80` | `services/rate_limit.py` |
| `departments` | create: `services/departments.py:44`, `cli.py:84`, `seed/run.py:132`. Update: `services/departments.py:73` (name, active, contact, `sla_mode`), `services/protected_actions.py:90` (clears `escalation_contact_user_id` when that user is deactivated, inside `AccountEffects.deactivate`) | `policy/relationships.py`, `policy/visibility.py`, `services/departments.py`, `services/calendar.py`, `services/sla/escalation.py`, `services/sla/scanner.py`, `queries/kpis.py`, and others |
| `spoke_assignments` | create: `services/departments.py:121`, `services/spokes.py:87`, `seed/run.py:183`. Revoke: `services/departments.py:157`, `services/spokes.py:81` | `policy/actors.py`, `services/me.py`, `services/spokes.py`, `services/departments.py`, `services/tickets.py` |
| `categories` | create: `services/categories.py:44`, `seed/run.py:210`. Update: `services/categories.py:80` | `services/categories.py`, `services/tickets.py`, `services/ticket_reads.py`, `services/calendar.py`, `services/sla/scanner.py`, `queries/kpis.py`, exports |
| `confidential_grants` | create: `services/confidential_grants.py:80`. Revoke: `services/confidential_grants.py:112` | `policy/relationships.py`, `policy/visibility.py`, `services/ticket_reads.py`, `handlers/notification_handlers.py` |
| `policy_versions` | create: `services/policy_admin.py:59` (and the `b03` seed row) | `services/policy.py` (read by nearly everything through `PolicyService`) |
| `tickets` | create: `services/tickets.py:43`. Update: `services/workflow/progress.py`, `closure.py`, `transfer.py`, `system.py`, `services/comments.py:93`, `services/sla/levels.py:44` (escalation level), `handlers/sla_handlers.py` (`sla_started_at`) | `queries/tickets.py`, `services/ticket_reads.py`, policy, dashboards, KPIs, exports, worker jobs |
| `ticket_counters` | upsert: `services/ticket_numbers.py:18` | the same |
| `ticket_collaborators` | create: `services/collaborators.py:32`. Delete: `services/collaborators.py:49` | `policy/relationships.py`, `policy/visibility.py`, `queries/tickets.py`, `handlers/recipients.py`, `services/ticket_reads.py` |
| `ticket_events` | create only: `services/tickets.py:67`, `services/workflow/common.py:100, 130`, `services/comments.py:41`, `services/collaborators.py:73` | `services/ticket_reads.py` (timeline), `services/dashboards.py`, `queries/kpis.py`, `handlers/notification_handlers.py` |
| `attachments` | create: `services/attachments.py:128`. Link to ticket: `services/tickets.py:65`. Delete unlinked: `worker/jobs/housekeeping.py:38` | `services/attachments.py`, `services/ticket_reads.py`, `services/tickets.py` |
| `sla_timers` | create: `services/sla/timers.py:74`. Update: `services/sla/timers.py` (restart, pause, resume, met, stop), `services/sla/levels.py` (level) | `services/sla/*`, `worker/jobs/auto_close.py`, `worker/jobs/reminders.py`, `services/ticket_reads.py`, `queries/kpis.py`, exports |
| `escalation_events` | insert ON CONFLICT: `services/sla/escalation.py:131` | `services/sla/scanner.py`, `worker/jobs/reminders.py`, `queries/kpis.py` |
| `notifications` | insert ON CONFLICT: `services/notifications.py:89`. Mark read: `services/notifications.py:183` and `mark_read` | `services/notifications.py`, `worker/jobs/digest.py` |
| `email_outbox` | create: `services/email_outbox.py:23`, `services/auth.py:339` (the password-reset email: `AuthService` builds its text and HTML inline and adds the outbox row itself instead of calling `enqueue_email`, see 13.0 #9). Status, attempts: `worker/jobs/send_outbox.py:53` | `worker/jobs/send_outbox.py` |
| `worker_heartbeat` | upsert: `worker/main.py:97` | `api/routers/health.py` |
| `audit_log` | create only: `services/audit.py:79` (`AuditService.record`, used by about 17 services) | `queries/audit.py`, `services/audit_reads.py` |
| `saved_views` | create: `services/saved_views.py:156`. Update and soft delete: `services/saved_views.py:169` | `services/saved_views.py` |
| `business_calendar` | upsert: `services/calendar.py:159` | `services/calendar.py` (`load_working_calendar`), the `working_seconds` SQL function |
| `holidays` | create: `services/calendar.py:114`. Soft delete: `remove_holiday` | `services/calendar.py`, `working_seconds` |
| `notification_preferences` | upsert: `services/preferences.py:51` | `services/preferences.py`, `worker/jobs/digest.py` |
| `notification_digests` | insert ON CONFLICT: `worker/jobs/digest.py:112` | `worker/jobs/digest.py` |
| `digest_items` | create: `services/notifications.py:118`. Mark sent or dropped: `worker/jobs/digest.py:126` | `worker/jobs/digest.py` |

### 6.5 Database-level protections

1. **Immutable history.** Triggers `ticket_events_immutable` (`b04`) and `audit_log_immutable` (`b05`) run `BEFORE UPDATE OR DELETE ... FOR EACH ROW` and raise `restrict_violation`. `b05` also revokes UPDATE and DELETE on both tables from `PUBLIC`. In the full Docker stack and production, the app connects as `ibotix_app`, which has no UPDATE, DELETE or TRUNCATE on these tables (`docker-compose.full.yml`, `docs/OPERATIONS.md`). Row-level triggers do not fire on `TRUNCATE`; the test suite relies on that to clean these tables (`CLAUDE.md`: "truncates IMMUTABLE_TABLES").
2. **CHECK constraints** encode rules the database itself enforces:
   - lowercase emails;
   - no stored `spoke` role;
   - ticket number and department code formats;
   - escalation level 0 to 3;
   - rating 1 to 5;
   - a protected action's decider must be independent;
   - non-negative counters;
   - calendar hours and weekdays valid.
3. **Partial unique indexes** let history coexist with "only one active" rules:
   - one active Spoke mapping or grant;
   - one pending signup per user;
   - one active holiday per date;
   - one live saved-view name per owner.
4. **Idempotency keys:**
   - `escalation_events` (ticket, timer, cycle, step);
   - `notifications` (user, dedupe key);
   - `notification_digests` (user, date);
   - `digest_items.notification_id`;
   - `ticket_counters` upsert.

   The worker can therefore be retried, or run twice, without duplicates.
5. **What the database does *not* enforce:** visibility of confidential tickets, role permissions and state transitions are enforced only in application code (`app/policy/`, services). A direct SQL user with write access bypasses them.

## 7. API / Endpoint Reference

This section lists all 88 routes: the 85 in `contract/routes.txt` (the contract the frontend relies on, checked by `scripts/check_contract.py --full`) plus the 3 health probes. The exact JSON shapes are in the OpenAPI document (`python -m app.cli export-openapi`, or `/docs` whenever `ENV` is not `prod`) and in Appendix A of `Backend_Build_Guide_v2.md`. This section explains **who may call each route and what happens inside**.

### 7.1 Rules that apply to every route

| Topic | Rule | Source |
|---|---|---|
| Base URL | `/api/v1` for everything except `/health/*` | `app/main.py` `API_PREFIX` |
| Authentication | `Authorization: Bearer <access token>` (a JWT, lifetime `ACCESS_TOKEN_MINUTES`). Missing, invalid or expired token, or a user who is no longer active: **401** `unauthenticated`. | `app/api/deps.py` `get_actor` |
| Public routes | Marked **Public** below. They never return 401 (`CLAUDE.md` hard rule), except the MFA and refresh routes, whose *token in the body or cookie* can be invalid. | |
| Error format | `{"error": {"code", "message", "fields"?, "details"?, "request_id"}}`; the same `request_id` is in the `X-Request-ID` response header. `fields` maps a field name to a message (422); `details` carries extra data such as `retry_after_seconds`. | `app/core/errors.py` `error_response` |
| Error codes | `unauthenticated` and `invalid_credentials` 401; `forbidden` and `account_state` 403; `not_found` 404 (also used for 405); `conflict`, `invalid_transition` and `protected_action_blocked` 409; `token_expired` 410; `file_too_large` 413; `unsupported_file_type` 415; `validation_error` 422; `too_many_attempts` and `rate_limited` 429; `server_error` 500. | `ErrorCode`, `ERROR_STATUS` |
| Hidden tickets | A ticket you may not see gives the **same 404** as a ticket that does not exist, on every route. | `TicketReadService.load_visible` |
| 403 or 409 on a ticket action | 403 `forbidden` if your role could never do it; 409 `invalid_transition` if your role could, but not in the ticket's current status. | `classify_denial` |
| Path ids | A malformed or unknown id **in the path** gives 404. A malformed or unknown id **in the body** gives 422 with a field error. | `CLAUDE.md` B09 |
| Paging | `page` (from 1) and `page_size` (1 to 100, default 25). Response `{"items", "total", "page", "page_size"}`. | `app/core/pagination.py` |
| Optional fields | Left out of the JSON instead of being `null`, where the contract says so. | `CLAUDE.md` B23 |
| Upload size | A request body larger than `MAX_UPLOAD_BYTES` + 64 KiB is cut off with 413 before it reaches the route. | `BodySizeLimitMiddleware` |
| Commit timing | The database transaction commits **before** the response is sent. If the commit fails, the client gets a 500, not a false success. | `get_db`, `DbSession` |

**Role shorthand used below:**
- **Any user**: any active, logged-in user.
- **Admin+**: Admin or Super Admin.
- **SA**: Super Admin.
- **Dept managers**: holders of `departments.manage`. That is a Super Admin always, and an Admin only when the policy key `admins_can_manage_departments` is true.
- **Team** (on a ticket): a Spoke of the ticket's department, the owner, an Admin or a Super Admin, provided they can see the ticket.

### 7.2 Health (no prefix, Public)

| Method and path | Response | Handler | Behaviour |
|---|---|---|---|
| `GET /health/live` | `{"status":"ok"}` | `health.live` | Always 200; no database access. |
| `GET /health/ready` | `{"status":"ok"}` | `health.ready` | Runs `SELECT 1`; 500 if the database is down. |
| `GET /health/worker` | `{"status":"ok"}` or **503** `{"status":"stale"}` | `health.worker` | Stale when the `worker_heartbeat` row is missing or older than 3 × `WORKER_TICK_SECONDS`. |

### 7.3 Public configuration and authentication

| # | Method and path | Auth | Request | Success | Handler → service | What happens, and the errors |
|---|---|---|---|---|---|---|
| 1 | `GET /public/config` | Public | — | 200 `PublicConfig` | `config.public_config` → `PolicyService.public_config` | Allowed email domains, active departments, upload limits, minimum password length, first-response hours. |
| 2 | `POST /auth/signup` | Public | `SignupBody`: `name`, `email`, `password`, `requested_role` (employee, admin, super_admin), `requested_department` | 202 `{"message"}` | `signup.signup` → `SignupService.signup` | Creates a `pending_verification` user and a pending request, then emails a 24 h verification link. An existing email gets the same 202 (no enumeration). 422 for a wrong domain, a weak password or an inactive department; 429 after 5 per hour per IP or email. |
| 3 | `POST /auth/verify-email` | Public | `{"token"}` | 200 `{"state"}` | `SignupService.verify_email` | Marks the email verified and moves the user to `pending_approval`; approvers are notified. 422 for an unknown or used token; 410 `token_expired`. |
| 4 | `POST /auth/resend-verification` | Public | `{"email"}` | 202, empty | `SignupService.resend_verification` | Re-sends only for `pending_verification` users. Always 202, except 429 after 3 per hour. |
| 5 | `POST /auth/reapply` | Public | `ReapplyBody`: `email`, `password`, `requested_role`, `requested_department` | 202, empty | `SignupService.reapply` | Only for `rejected` accounts: opens a new pending request. 403 with `fields.password` for a wrong password or unknown email; 429 when locked; 409 if the account is not rejected. |
| 6 | `POST /auth/login` | Public | `{"email","password"}` | 200 `LoginSuccess` (`access_token`, `expires_in`, `user`) and a `refresh_token` cookie; **or** 200 `{"mfa_required":true,"mfa_token"}`; **or** 200 `{"mfa_enrol_required":true,"mfa_token"}` | `auth.login` → `AuthService.login` | 401 `invalid_credentials` (wrong password or unknown email, same answer); 403 `account_state` (not active, with the rejection reason if rejected); 429 `too_many_attempts` (locked 15 min after 5 failures) or `rate_limited` (10 per minute per IP or email). |
| 7 | `POST /auth/mfa/setup` | Public, MFA token | `{"mfa_token"}` | 200 `{"secret","otpauth_uri"}` | `AuthService.mfa_setup` → `MfaService.setup` | Stores a new TOTP secret, Fernet-encrypted. **404** when MFA is switched off (`MFA_REQUIRED_ROLES` empty); 401 for a bad token; 409 if MFA is already on. |
| 8 | `POST /auth/mfa/confirm` | Public, MFA token | `{"mfa_token","code"}` | 200 `LoginSuccess` + `recovery_codes` (8, shown once) and the cookie | `MfaService.confirm`, then `_grant` | 422 `fields.code` for a wrong code; 409 if setup was not started. |
| 9 | `POST /auth/mfa/verify` | Public, MFA token | `{"mfa_token","code"}` (TOTP or recovery code) | 200 `LoginSuccess` and the cookie | `MfaService.verify`, then `_grant` | 422 for a wrong code; 429 after 5 failures (15 min lock); 409 if MFA is not enabled. |
| 10 | `POST /auth/refresh` | Cookie | `refresh_token` cookie; allowed `Origin` | 200 `{"access_token","expires_in"}` and a new cookie | `AuthService.refresh` | Rotates the token. Reusing an old token revokes the whole family (theft detection). 401 when missing, unknown, revoked, expired or the user is inactive; 403 for a foreign `Origin`. |
| 11 | `POST /auth/logout` | Cookie | the cookie; allowed `Origin` | 204, cookie cleared | `AuthService.logout` | Revokes the token's family. Always 204. |
| 12 | `POST /auth/forgot-password` | Public | `{"email"}` | 202, empty | `AuthService.forgot_password` | Emails a 1 h reset link to active users only; always 202 except 429 after 3 per hour. |
| 13 | `POST /auth/reset-password` | Public | `{"token","password"}` | 204 | `AuthService.reset_password` | Sets the password, clears lockout and **logs out every device** (revokes all refresh tokens). 422 for a bad token or weak password; 410 when expired. |
| 14 | `GET /auth/me` | Any user | — | 200 `Me` (profile, roles, Spoke departments, `permissions` flags) | `auth.me` → `MeService.me` | The frontend calls this after login to decide which screens to show. |

### 7.4 Users, signup approvals, Admins, protected actions

| # | Method and path | Auth | Request | Success | Handler → service | What happens, and the errors |
|---|---|---|---|---|---|---|
| 15 | `GET /users` | `users.manage_roles` or `admins.manage` | query `q`, `role`, `state`, `department_id`, paging | 200 `Page[UserListItem]` | `UserService.list_users` | User directory with Spoke departments. 403 otherwise. |
| 16 | `GET /users/lookup` | Any user | `q` (at least 2 characters) | 200 `list[UserRef]` (up to 20) | `UserService.lookup` | Active users by name or email, for pickers. 422 if `q` is too short. See 13.0 #26. |
| 17 | `GET /departments/{id}/members` | Any user | — | 200 `list[UserRef]` | `UserService.department_members` | People whose home department is `{id}` or who are its active Spokes. 404 for an unknown department. See 13.0 #30. |
| 18 | `PATCH /users/{id}/roles` | `users.manage_roles`; an Admin only on `employee` targets | `{"spoke_departments":[...], "reason"}` | 200 `UserListItem` | `UserService.update_roles` → `SpokeService.replace` | Replaces the user's Spoke departments; audits each added or revoked mapping. 409 if the account is not active; 403. |
| 19 | `POST /users/{id}/deactivate` | as #18; never yourself | `{"reason"}` | 200 `{"result","open_ticket_count","protected_action_id"}` (the id is `null` unless a protected action was created) | `UserService.deactivate` | Normal users: deactivated at once. Their refresh tokens and Spoke mappings are revoked, the audit records `user_deactivated`, and Admins are told if open tickets remain. **Super Admin target:** a protected-action request is created instead (`result: protected_request_created`). 409 if not active. |
| 20 | `POST /users/{id}/activate` | as #19 | — | 200 `UserListItem` | `UserService.activate` | Only a deactivated, previously approved account (409 otherwise). Audits `user_activated`. |
| 21 | `GET /signup-requests` | `users.approve_employee` (Admin+) | `status`, paging | 200 `Page[SignupRequestOut]` with `can_approve` per row | `SignupService.list_requests` | Hides requests whose email is not yet verified. |
| 22 | `POST /signup-requests/{id}/approve` | `can_decide_signup`: Admin+ for employee; SA for admin and super_admin; never your own | `{"approved_role","approved_department"}` | 200 `SignupRequestOut` | `SignupService.approve` | Activates the user with the approved role and department, emails `signup_approved`, audits (security limited). 403; 409 if no longer pending; 422 for an inactive department. |
| 23 | `POST /signup-requests/{id}/reject` | as #22 | `{"reason"}` (5 to 1000) | 200 `SignupRequestOut` | `SignupService.reject` | Sets the user to `rejected` and emails the reason. |
| 24 | `GET /admins` | SA (`admins.manage`) | — | 200 `list[UserListItem]` | `UserService.list_admins` | All Admins and Super Admins. |
| 25 | `POST /admins` | SA | `{"user_id"}` | 200 `UserListItem` | `UserService.promote_admin` | Active employee → Admin; audit `admin_promoted` (security limited). 422 for an unknown id; 409 if not an active employee. |
| 26 | `DELETE /admins/{user_id}` | SA | — | 200 `UserListItem` | `UserService.demote_admin` | Admin → employee. A Super Admin target gives 409 `protected_action_blocked` (use #28). |
| 27 | `GET /protected-actions` | SA (`superadmins.protect`) | `status`, paging | 200 `Page[ProtectedActionOut]` with `can_decide` | `ProtectedActionService.list_actions` | Newest first. |
| 28 | `POST /protected-actions` | SA | `{"kind": "deactivate_super_admin" or "demote_super_admin", "target_user_id", "reason"}` | 200 `ProtectedActionOut` | `ProtectedActionService.create` → `request` | The target must be another active Super Admin (422). 409 for a duplicate pending request; 409 `protected_action_blocked` if fewer than 2 Super Admins would remain. Expires after 72 h. Other Super Admins are notified (critical). |
| 29 | `POST /protected-actions/{id}/approve` | SA who is neither requester nor target | — | 200 `ProtectedActionOut` | `ProtectedActionService.approve` | Re-checks the minimum of 2 Super Admins under lock, then deactivates the target or demotes them to Admin. Audit `protected_action_approved` (security limited). 403 if not independent; 409 if expired, decided or the target changed. |
| 30 | `POST /protected-actions/{id}/reject` | as #29 | `{"reason"}` | 200 `ProtectedActionOut` | `ProtectedActionService.reject` | Closes the request as rejected. |

### 7.5 Organisation: departments, categories, grants, policy, calendar

| # | Method and path | Auth | Request | Success | Handler → service | What happens, and the errors |
|---|---|---|---|---|---|---|
| 31 | `GET /departments` | Any user | — | 200 `list[DepartmentOut]` (Spokes, categories, contact, `accepts_tickets`, `sla_mode`) | `DepartmentService.list_departments` | Dept managers also see inactive departments. |
| 32 | `POST /departments` | Dept managers | `{"id": "^[A-Z]{2,6}$", "name"}` | **200** `DepartmentOut` | `DepartmentService.create` | Starts **inactive**. 409 for a duplicate code. |
| 33 | `PATCH /departments/{id}` | Dept managers | `{"name"?, "active"?, "sla_mode"?}` (`null` sla_mode clears the override) | 200 | `DepartmentService.update` | Activating needs an active Spoke (409). Audits `department_updated` and, for a mode change, `sla_basis_changed`. |
| 34 | `POST /departments/{id}/spokes` | Dept managers | `{"user_id"}` | 200 | `DepartmentService.add_spoke` | 422 if the user is not active; 409 if already a Spoke. |
| 35 | `DELETE /departments/{id}/spokes/{user_id}` | Dept managers | — | 200 | `DepartmentService.remove_spoke` | 404 if there is no active mapping. |
| 36 | `PUT /departments/{id}/escalation` | Dept managers | `{"contact_id": id or null}` | 200 | `DepartmentService.set_escalation_contact` | The contact must be an active member of the department (422). |
| 37 | `POST /departments/{id}/categories` | Dept managers | `{"name","confidential"?}` | **200** `CategoryOut` | `CategoryService.create` | 409 for a duplicate name (ignoring case) in the department. |
| 38 | `PATCH /categories/{id}` | Dept managers | `{"name"?,"active"?,"confidential"?,"sla_mode"?}` | 200 | `CategoryService.update` | Existing tickets keep their `confidential` flag (13.0 #22). |
| 39 | `DELETE /categories/{id}` | Dept managers | — | 204 | `CategoryService.deactivate` | Soft delete (`is_active = false`). |
| 40 | `GET /confidential-grants` | SA (`confidential.manage`) | `category_id`, `user_id` | 200 `list[ConfidentialGrantOut]` | `ConfidentialGrantService.list_grants` | Active grants only. |
| 41 | `POST /confidential-grants` | SA | `{"user_id","category_id"}` | **200** | `ConfidentialGrantService.create` | The category must be active and confidential (422); 409 for a duplicate. The user is notified. |
| 42 | `DELETE /confidential-grants/{id}` | SA | — | 204 | `ConfidentialGrantService.revoke` | 404 if unknown or already revoked. |
| 43 | `GET /policy` | Admin+ | — | 200 `PolicyConfig` | `PolicyAdminService.read` | The current policy version. |
| 44 | `PUT /policy` | SA (`policy.manage`) | `PolicyBody`: every key (hours per priority, cadence, reminders, auto-close days, reopen window, max reopens, `sla_mode`, `admins_can_manage_departments`) | 200 `PolicyConfig` | `PolicyAdminService.replace` | Inserts version + 1 under an advisory lock. 422 for cross-field errors (warning < due < L3). Applies to timers started afterwards. |
| 45 | `GET /calendar` | Admin+ | — | 200 `BusinessCalendarOut` (working days, hours, holidays) | `CalendarService.read` | Defaults (Monday to Friday, 09:00 to 18:00) if never saved. |
| 46 | `PUT /calendar` | SA | `{"working_days":[1..7], "work_start":"HH:MM", "work_end":"HH:MM"}` | 200 | `CalendarService.update` | 422 if the end is not after the start. Audits `business_calendar_updated`. |
| 47 | `POST /calendar/holidays` | SA | `{"date":"YYYY-MM-DD","name"}` | **201**, the full calendar | `CalendarService.add_holiday` | 409 for a duplicate active date. |
| 48 | `DELETE /calendar/holidays/{date}` | SA | — | 204 | `CalendarService.remove_holiday` | 404 for a bad date or no active holiday. |

### 7.6 Tickets: list, create, read, timeline, comments, collaborators, attachments

| # | Method and path | Auth | Request | Success | Handler → service | What happens, and the errors |
|---|---|---|---|---|---|---|
| 49 | `GET /tickets` | Any user (scope rules) | `scope` (`mine` default, `assigned`, `queue`, `all`), `q`, `status`/`status[]` (also `open`), `priority`/`priority[]`, `department_id`, `category_id`, `sla_state`, `escalation_level` (0 to 3), `requester_id`, `assignee_id`, `confidential`, `overdue_eta`, `unassigned`, `awaiting_before`, `created_from`, `created_to`, `sort`, paging | 200 `Page[TicketOut]` | `tickets.list_tickets` → `TicketReadService.list_tickets` | The visibility clause is **always** applied. `queue` needs Spoke rights on the department (403); `all` needs `tickets.view_all` (403). 422 for an unknown status, sort or id. |
| 50 | `POST /tickets` | Any user (`tickets.create`) | `CreateTicketBody`: `department_id`, `category_id`?, `title`, `description`, `priority`, `confidential`?, `attachment_ids`? | **201** `TicketOut` | `TicketService.create` | Number `IBX-<DEPT>-<YEAR>-<6 digits>`; status `new`. Starts the initial-response SLA and notifies the department's Spokes. A **critical** ticket alerts the escalation contact at once (next scanner run). 422 if the department is not accepting tickets, the category is wrong or missing, or an attachment is not your own unlinked upload. |
| 51 | `GET /tickets/{ticket_no}` | Any user who can see it | — | 200 `TicketOut` including `sla` and `allowed_actions` | `TicketReadService.get_ticket` | 404 if hidden or missing. |
| 52 | `GET /tickets/{ticket_no}/timeline` | as #51 | — | 200 `list[TimelineEventOut]` | `TicketReadService.timeline` | Team and assignee see every event; others see public events only, with `public_detail` as the text. |
| 53 | `POST /tickets/{ticket_no}/comments` | `comment`: all participants; `internal_note`: team and assignee | `{"body","internal"?}` | **201** `TimelineEventOut` | `ticket_comments.add_comment` → `CommentService.add` | A team comment counts as a progress update (restarts the update timer). A requester's public reply on `awaiting_requester` moves the ticket back to `in_progress`. 409 on closed or cancelled tickets. |
| 54 | `POST /tickets/{ticket_no}/collaborators` | Team (`manage_collaborators`) | `{"user_id"}` | 200 `TicketOut` | `CollaboratorService.add` | The collaborator can now see the ticket, even a confidential one. 422 for an inactive user or the requester; 409 if already added. |
| 55 | `DELETE /tickets/{ticket_no}/collaborators/{user_id}` | Team | — | 200 `TicketOut` | `CollaboratorService.remove` | 404 if not a collaborator. |
| 56 | `POST /attachments` | Any user | multipart, field `file` | **201** `AttachmentOut` | `attachments.upload_attachment` → `AttachmentService.upload` | Stored unlinked until used in #50. 413 over `MAX_UPLOAD_BYTES`; 415 for a type not allowed or content that does not match it; 422 for too many unlinked uploads. |
| 57 | `GET /attachments/{id}/download` | the uploader (unlinked), or anyone who can see the ticket | — | 200 file stream | `AttachmentService.download` | 404 for hidden, unknown or unclean files. Downloads from confidential tickets are audited. |

### 7.7 Ticket workflow

All return 200 `TicketOut`, take the ticket number in the path, lock the ticket (`Workflow.begin`), check `ACTION_RULES`, write a timeline event and an audit row, and publish domain events (SLA handlers, then notifications). Errors common to all: 404 hidden or missing; 403 or 409 as in 7.1; 422 for body errors.

| # | Method and path | Allowed for (status) | Request | Effect |
|---|---|---|---|---|
| 58 | `POST /tickets/{no}/acknowledge` | Team, not the requester (`new`) | `eta` **or** (`no_eta_reason` + `next_checkpoint_at`), all future | Caller becomes owner; status `acknowledged`; initial response met; update and ETA timers start. |
| 59 | `POST /tickets/{no}/assign` | Team (working statuses) | `assignee_id`, `reason`? | A Spoke or the owner picks a department member, no reason needed; an Admin+ may pick anyone but must give a reason. From acknowledged or reopened → `assigned`. |
| 60 | `POST /tickets/{no}/transfer` | Team (active statuses) | `department_id`, `category_id`?, `reason` | Moves to the other department, resets to `new`, clears owner, assignee, ETA and hold, starts a new SLA cycle. Confidential is never downgraded. The caller may lose access afterwards. |
| 61 | `POST /tickets/{no}/priority` | Team (active statuses) | `priority` (must differ), `reason` | Staff-only timeline event; recomputes initial-response thresholds if still unmet. |
| 62 | `POST /tickets/{no}/eta` | Team, assignee (working statuses) | `eta` (future, different), `reason` | Restarts the ETA timer; the requester is told "set", "extended" or "changed". |
| 63 | `POST /tickets/{no}/status` | Team, assignee | `status` = `in_progress` or `awaiting_requester`, `message` (required for awaiting) | `in_progress` from acknowledged, assigned or reopened (`start_work`) or from awaiting or on hold (`resume`). `awaiting_requester` from in progress (`ask_requester`): pauses update and ETA timers and starts the requester reminder. |
| 64 | `POST /tickets/{no}/hold` | Team, assignee (`in_progress`) | `reason`, `review_date` (future) | Status `on_hold`; timers paused; hold-review timer starts. |
| 65 | `POST /tickets/{no}/resolve` | Team, assignee; **never the requester** (`in_progress`) | `summary` | Status `resolved`; auto-close timer starts (`auto_close_business_days`). |
| 66 | `POST /tickets/{no}/confirm-closure` | Requester (`resolved`) | `rating` (1 to 5)?, `comment`? | Closes with reason `confirmed` and stores the feedback. |
| 67 | `POST /tickets/{no}/reopen` | Requester, team (`resolved`, `closed`) | `reason` | Within `reopen_window_days` and under `max_reopens`, else 409 with `details` (count, maximum, window end). Status `reopened`, new SLA cycle. |
| 68 | `POST /tickets/{no}/cancel` | Team (active statuses); requester only while `new` | `reason` | Status `cancelled`; all timers stop. |
| 69 | `POST /tickets/{no}/close` | Team (`resolved`) | `reason` | Closes with reason `admin` without waiting for the requester. |

### 7.8 Notifications and preferences

| # | Method and path | Auth | Request | Success | Handler → service | What happens |
|---|---|---|---|---|---|---|
| 70 | `GET /notifications` | Any user | `unread` (bool), paging | 200 `Page[NotificationOut]` | `NotificationService.list_own` | Own notifications, newest first. Rows about tickets you can no longer see are hidden. |
| 71 | `GET /notifications/unread-count` | Any user | — | 200 `{"count"}` | `NotificationService.unread_count` | Same visibility filter. The frontend polls it for the bell badge. |
| 72 | `POST /notifications/{id}/read` | Any user | — | 204 | `NotificationService.mark_read` | 404 if it is not yours. |
| 73 | `POST /notifications/read-all` | Any user | — | 204 | `NotificationService.mark_all_read` | One UPDATE. |
| 74 | `GET /me/notification-preferences` | Any user | — | 200 `{"non_critical_email","digest_hour","critical_email":"always"}` | `PreferenceService.read` | Defaults `immediate`, hour 9, when never saved. |
| 75 | `PUT /me/notification-preferences` | Any user | `{"non_critical_email": "immediate", "daily_digest" or "off", "digest_hour": 0-23}` | 200 | `PreferenceService.replace` | Upsert; not audited. Sending `critical_email` gives 422 (extra fields forbidden). |

### 7.9 Audit, dashboards, reports, exports, saved views

| # | Method and path | Auth | Request | Success | Handler → service | What happens, and the errors |
|---|---|---|---|---|---|---|
| 76 | `GET /audit` | Admin+ (`audit.view_all`) | `q`, `actor_id`, `action`, `ticket_id` (number), `from`, `to`, paging | 200 `Page[AuditEntryOut]` | `AuditReadService.list_entries` | Super Admins see everything. Admins do not see security-limited rows or rows about tickets they cannot see. |
| 77 | `GET /dashboard/employee` | Any user | — | 200 `EmployeeDashboardOut` | `DashboardService.employee` | Counts for my requested and assigned tickets, recent public updates, up to 6 tickets needing attention. |
| 78 | `GET /dashboard/spoke` | `tickets.view_department` (Spokes) | — | 200 `SpokeDashboardOut` | `DashboardService.spoke` | Queue counts for my departments plus 30-day KPIs. 403 for non-Spokes. |
| 79 | `GET /dashboard/admin` | `tickets.view_all` (Admin+) | — | 200 `AdminDashboardOut` | `DashboardService.admin` | Organisation counts, pending approvals I can decide, KPIs. |
| 80 | `GET /reports/kpis` | `reports.view_org` (Admin+) or a Spoke | `from`, `to` (with time zone; default last 30 days, max 366), `department_id`, `priority`/`priority[]` | 200 `KpiReportOut` | `reports.kpi_report` → `KpiService.report` | A Spoke is limited to their own departments (403 for another). 422 for a bad window or unknown department. Visibility always applied. |
| 81 | `GET /reports/export` | as #80 | `type` (`tickets`, `kpis`), `format` (`csv`, `xlsx`, `pdf`), the #49 filters, `from`, `to` | 200 file download | `exports.export_report` → `ExportService.export` | Refused with 422 `fields.format` above 50,000 rows (CSV, XLSX) or 2,000 (PDF). Formula-like cells are prefixed with `'`. Audits `report_exported`. |
| 82 | `GET /saved-views` | Any user | — | 200 `list[SavedViewOut]` | `SavedViewService.list_views` | Built-in views first (computed for your role), then your own. |
| 83 | `POST /saved-views` | Any user | `{"name","query":{...}}` | **201** | `SavedViewService.create` | `query` is validated exactly like #49 (`fields["query.<key>"]` on error). 409 for a duplicate name or more than 50 views. |
| 84 | `PATCH /saved-views/{id}` | Owner | `{"name"?,"query"?}` | 200 | `SavedViewService.update` | 403 for a built-in id; 404 for someone else's view. |
| 85 | `DELETE /saved-views/{id}` | Owner | — | 204 | `SavedViewService.delete` | Soft delete; same 403 and 404 rules. |

## 8. End-to-End Flows

Each flow follows one real scenario through the layers: **HTTP → middleware → router → dependencies → service → policy → database → domain events → worker → email**. The numbers in brackets, like [#50], refer to the routes in section 7.

**What every API request passes through first** (4.3, 4.4):
1. `RequestContextMiddleware` gives the request an id (or keeps a valid incoming `X-Request-ID`) and records the IP and user agent.
2. `SecurityHeadersMiddleware` adds the security headers to the response.
3. CORS.
4. `BodySizeLimitMiddleware` rejects bodies that are too large; GZip compresses large responses.
5. FastAPI validates the path, query and body against the schemas (422 `validation_error` on failure).
6. The dependencies run: `get_db` opens a session; `get_actor` authenticates the caller.
7. The route calls the service. When the route returns, `get_db` commits, and only then is the response sent. The JSON access log line `app.access` is written at the end.

### 8.1 Self-signup, email verification, approval, first login

1. **Alice opens the signup page.** The frontend calls `GET /public/config` [#1] to fill the department list and show the password rules. No token is needed.
2. **She submits the form** to `POST /auth/signup` [#2]. In `SignupService.signup`:
   1. The checks run in order: email domain in `ALLOWED_EMAIL_DOMAINS`, `password_policy_error` (length and character rules from `app/core/security.py`), and the department exists and is active.
   2. `RateLimiter.hit` upserts `rate_limit_hits` for the IP and the email (each hashed).
   3. It inserts `users` (state `pending_verification`, password hashed with Argon2) and `signup_requests` (`pending`), and audits `signup_requested`.
   4. `_issue_verification` inserts an `email_tokens` row (SHA-256 of a random token, 24 h) and calls `enqueue_email(..., "verify_email", {name, token, expires_hours})`. That renders the Jinja2 templates now and inserts an `email_outbox` row with status `pending`.
   5. The router returns 202. `get_db` commits the user, request, token, outbox row and audit row together. **No email has been sent yet.**
3. **The worker sends the email.** On its next tick (every `WORKER_TICK_SECONDS`, default 15 s) the `send_outbox` job locks up to 20 due rows `FOR UPDATE SKIP LOCKED` and hands each to the `EmailSender` (SMTP; Mailpit in development). Each row becomes `sent`, or after a failure gets `attempts + 1` and a retry 1, 5, 30 or 120 minutes later; after 5 attempts it becomes `failed`. Then it commits.
4. **Alice clicks the link** `<FRONTEND_BASE_URL>/verify-email?token=...`. The frontend posts the token to `POST /auth/verify-email` [#3]. `SignupService.verify_email` hashes it, finds the `email_tokens` row, checks it is unused and unexpired, and marks it used. It sets `email_verified_at` and state `pending_approval`, audits `email_verified`, and **publishes `SignupVerified`**.
5. **Domain event, inside the same transaction.** `publish` calls the registered handlers synchronously. `notification_handlers` sends `signup_pending` to every Admin and Super Admin (for an employee request). `Notifier.send` inserts a `notifications` row for each, then queues an email or a digest item, depending on each approver's preference (R2-C2).
6. **An Admin approves.** The admin's portal shows the notification. The admin opens `GET /signup-requests` [#21] and calls `POST /signup-requests/{id}/approve` [#22]:
   1. `can_decide_signup` checks the role rank: an employee request needs Admin+, and the admin may not approve their own request.
   2. The request and user rows are checked to be still pending.
   3. The user becomes `active` with the approved role and department; the request becomes `approved`.
   4. The `signup_approved` email is queued; the audit row is security limited; `SignupDecided` is published.
7. **Alice logs in** with `POST /auth/login` [#6]:
   1. Rate limits are applied.
   2. The `users` row is loaded `FOR UPDATE` and the Argon2 hash verified.
   3. Failure counters are reset. `MfaService.challenge` returns `None` (MFA is off for employees by default).
   4. `_grant` sets `last_login_at`, audits `login_succeeded`, inserts a `refresh_tokens` row (hash only, new family) and creates a 15-minute access JWT.
   5. The router sets the `refresh_token` cookie (httpOnly, path `/api/v1/auth`) and returns `LoginSuccess` with `Me`.
8. The frontend keeps the access token **in memory**, and sends it as `Authorization: Bearer ...` on every later call.

### 8.2 Login with MFA, token refresh and logout

Assume `MFA_REQUIRED_ROLES=admin,super_admin` and Bob is an Admin who has not enrolled yet.

1. **`POST /auth/login` [#6]:** the password is correct, so `MfaService.challenge` sees that Bob's role requires MFA but `mfa_enabled` is false. It returns `MfaEnrolRequired` with a **5-minute MFA token**. This JWT has `aud="mfa"` and no `jti`, so it cannot be used as an access token. There is no cookie and no access token yet.
2. **`POST /auth/mfa/setup` [#7]** with the MFA token: a base32 secret is generated, stored **Fernet-encrypted** in `users.mfa_secret_encrypted`, and returned with an `otpauth://` URI. The frontend shows it as a QR code.
3. **`POST /auth/mfa/confirm` [#8]** with the 6-digit code from Bob's app:
   1. `pyotp` verifies the code, allowing ±1 step of 30 seconds.
   2. Eight recovery codes are generated and stored as SHA-256 hashes in `mfa_recovery_codes`; `mfa_enabled` becomes true and `mfa_enabled` is audited.
   3. `_grant` runs, as in 8.1 step 7.
   4. The response includes the plain recovery codes, the only time they are shown.
4. **Next day:** login returns `MfaRequired`, and `POST /auth/mfa/verify` [#9] accepts a TOTP code or one unused recovery code. Five wrong codes set `locked_until` for 15 minutes (429).
5. **The access token expires after 15 minutes.** The frontend calls `POST /auth/refresh` [#10]. The browser sends the cookie automatically because the path matches. `require_allowed_origin` checks `Origin`. `AuthService.refresh`:
   1. Finds the token by hash `FOR UPDATE`.
   2. Checks it is neither revoked nor expired and the user is still active.
   3. Inserts a **replacement in the same family** and marks the old one `revoked_at` with `replaced_by_id`.
   4. The router sets the new cookie and returns a new access token.
6. **Theft detection:** if anyone later presents the *old* cookie, `refresh` sees a revoked token that was replaced. It revokes **every** token in the family and audits `refresh_reuse_detected`. Both the thief and Bob must log in again.
7. **`POST /auth/logout` [#11]** revokes the family, audits `logout`, and clears the cookie (204).

### 8.3 Raising a ticket with an attachment

1. **Upload first:** `POST /attachments` [#56] (multipart). `AttachmentService.upload`:
   1. Reads at most `MAX_UPLOAD_BYTES + 1` bytes (413 if more).
   2. Checks that the declared type is allowed **and** the bytes match it; `SNIFFERS` checks the PDF, PNG, JPEG and ZIP signatures and UTF-8 text (415).
   3. Checks the user holds fewer than `MAX_FILES_PER_TICKET` unlinked uploads (422).
   4. Writes the file via `LocalStorage.save` to `ATTACHMENT_DIR/attachments/<random hex>`.
   5. Inserts `attachments` with `ticket_id = NULL`, the SHA-256 hash and scan status `clean` (`NoopScanner`).
   6. Returns 201 with the attachment id.
2. **Create:** `POST /tickets` [#50] with `attachment_ids: [<id>]`. In `TicketService.create`:
   1. `_accepting_department`: the department exists, is active and has an active Spoke.
   2. `_category`: valid for the department, or required when the department has categories.
   3. `_attachments` locks the uploads `FOR UPDATE` and checks each is Alice's own, unlinked and clean.
   4. `confidential` is set if Alice asked for it or the category is confidential.
   5. `TicketNumberService.next_number` upserts `ticket_counters` for (department, IST year), giving `IBX-IT-2026-000018`. This is atomic, so there are no duplicate numbers.
   6. It inserts `tickets` (status `new`, `sla_started_at = now`), links the attachments, inserts a public `ticket_events` row `created`, and audits `ticket_created`.
   7. **`publish(TicketCreated)`:**
      1. The **SLA handler** runs first. `Timers.start_initial_response` inserts an `sla_timers` row whose `warning_at`, `due_at` and `l3_at` come from the policy for this priority, multiplied by `SLA_TIME_SCALE`. In business mode they count working hours only (`add_working_time`). `reconcile` and `apply_levels` follow.
      2. The **notification handler** runs second. It plans `ticket_created` for the department's Spokes, excluding Alice (the actor). `visible_only` drops anyone who cannot see the ticket, which matters if it is confidential. `Notifier.send` inserts `notifications` rows and queues emails (or digest items).
   8. `TicketPresenter.present_one` builds the response for Alice: `sla` (label "Initial response due") and `allowed_actions` (for a requester on a `new` ticket: `comment`, `cancel`).
   9. 201. `get_db` commits everything at once: ticket, timer, events, audit, notifications and outbox rows.
3. **Critical priority only:** the next `sla_scan` run sees the pending `CREATION_CONTACT` step and alerts the department's escalation contact at once (8.5).

### 8.4 Working a ticket to closure

Actors: Sam is a Spoke of IT; Alice is the requester.

1. **Acknowledge** `POST /tickets/{no}/acknowledge` [#58] with `eta`:
   1. `Workflow.begin` runs `load_visible(for_update=True)` (404 if Sam cannot see it), builds the `ActorContext` (Sam is a department Spoke, so actor class `team`), and checks `is_action_allowed(acknowledge)` (the status is `new`).
   2. `ProgressService.acknowledge` checks the ETA is in the future, sets owner Sam, status `acknowledged`, `acknowledged_at` and `last_team_update_at`.
   3. `Workflow.record` inserts the public `acknowledged` event and the `ticket_acknowledged` audit row.
   4. It publishes `TicketAcknowledged` and `TeamUpdateRecorded`. The SLA handler marks `initial_response` met and starts the `progress_update` and `eta` timers. The notification handler tells Alice (P+E).
2. **Start work** `POST /status {"status":"in_progress"}` [#63]: the action checked is `start_work`. A `status_changed` event is recorded, and Alice is notified.
3. **Ask Alice something** `POST /status {"status":"awaiting_requester","message":"Which floor?"}`:
   1. The action checked is `ask_requester`. `awaiting_since` is set, and the message is stored as a public comment.
   2. The SLA handler **pauses** `progress_update` and `eta` and starts `requester_reminder`. The ticket's `sla.label` becomes "Timer paused".
4. **Alice replies** `POST /comments {"body":"3rd floor"}` [#53]:
   1. `CommentService.add` sees a requester's public comment on an `awaiting_requester` ticket, so it moves the status back to `in_progress` with a **system** `status_changed` event.
   2. It publishes `TicketStatusChanged` (timers resume, the reminder stops), then `CommentAdded`. Owner, assignee and Spokes are notified.
5. **Resolve** `POST /resolve {"summary":"Cable replaced"}` [#65]: status `resolved`. The SLA handler marks `eta` met, stops `progress_update`, and starts `auto_close`, due `auto_close_business_days` working days later (`add_business_days`, which skips weekends and calendar holidays). Alice receives `resolved` (P+E).
6. **Alice confirms** `POST /confirm-closure {"rating":5}` [#66]: `close_ticket` sets `closed`, `closed_at` and `close_reason = confirmed`, records the feedback, and publishes `TicketClosed`. The SLA handler stops all timers.
7. **If Alice never confirms,** the `auto_close` worker job finds due `auto_close` timers. It locks the ticket, then the timer, and calls `close_system`, which closes with actor `NULL` and reason `auto`, then commits.
8. **If the fix did not hold,** Alice calls `POST /reopen` [#67] within `reopen_window_days` (and under `max_reopens`). The status becomes `reopened`, `reopen_count + 1`, `sla_started_at = now`; a new `initial_response` cycle starts (`cycle + 1`). After the window or limit, the 409 `details` explain why.

### 8.5 SLA escalation by the worker

Nobody acknowledges a `high` ticket created at 10:00.

1. **The worker loop** (`python -m app.worker`, `Worker.tick` in `app/worker/main.py`) runs the jobs in order every tick: `sla_scan`, `reminders`, `auto_close`, `protected_action_expiry`, `housekeeping`, `digest`, `send_outbox`. Each job gets its own session and commits its own work; a failing job is logged and does not stop the others. Finally it upserts `worker_heartbeat`, which `/health/worker` reads.
2. **`sla_scan` → `SlaScanner.run`:**
   1. `pg_try_advisory_xact_lock(7420019)`: if another worker is scanning, it returns 0 at once.
   2. `candidate_timers` selects running SLA timers of open tickets whose current step is not yet recorded in `escalation_events`, up to 100, `FOR UPDATE SKIP LOCKED`.
   3. Per timer, in a savepoint, `_process` locks the ticket `SKIP LOCKED`. Then `due_steps` sees that `warning_at` has passed, so the step is `L1`.
   4. `resolve_recipients(level 1)` gives owner, assignee and department Spokes. `record_step` inserts `escalation_events` with `ON CONFLICT DO NOTHING`. If another process already recorded it, nothing more happens; this is the idempotency guarantee.
   5. `recompute_ticket` sets the timer level to 1 and `tickets.escalation_level = 1`. A non-public timeline event `escalation` ("L1 initial response warning") and audit `ticket_escalation` are written.
   6. It publishes `SlaWarningRaised`. The notification handler sends `sla_warning` with dedupe key `sla_warning:<ticket>:initial_response:<cycle>:L1`, so the same warning is never sent twice.

3. **Later ticks:**
   - at `due_at`, step `L2`: team plus escalation contact plus Admins, sent as a **critical** `escalation`, which ignores digest preferences;
   - at `l3_at`, step `L3`: all Admins and Super Admins;
   - then `L3_REPEAT_1`, `L3_REPEAT_2`, ... every `escalation_repeat_hours`.
4. **After a worker outage,** the scanner records every missed step (L1, L2, L3, the latest repeat) but `steps_to_emit` sends only one alert per level.
5. **Confidential tickets:** `resolve_recipients` removes recipients who cannot see the ticket, and every email uses the masked template `confidential_ticket_update` ("Update on IBX-...").
6. The `send_outbox` job at the end of the same tick sends the emails.

### 8.6 Exporting a ticket report

1. A Spoke of IT and HR calls `GET /reports/export?type=tickets&format=xlsx&status=open` [#81]. The router parses the same filters as `GET /tickets` through `TicketListParams`.
2. **`ExportService.export`:**
   1. `can_view_reports`: the caller is a Spoke, so access is allowed.
   2. `report_scope` limits the export to IT and HR, because the caller lacks `reports.view_org`.
   3. `TicketReadService.filters` builds the clauses; the visibility clause is always added.
   4. A `COUNT` runs first; more than 50,000 rows gives 422 `fields.format`. The export is refused, not cut short.
   5. Tickets, users, categories and timers are loaded in chunks of 1,000, and `ticket_table` builds the rows (names instead of ids, the SLA label).
   6. Audit `report_exported` with type, format, filters and row count. It is security limited if any exported ticket is confidential.
   7. `render` produces the bytes: openpyxl here; CSV is streamed as it is written. `safe_cell` prefixes `'` to cells starting with `=`, `+`, `-`, `@`, tab or carriage return.
3. The router returns a `StreamingResponse` with `Content-Disposition: attachment; filename="ibotix-tickets-<YYYYMMDD-HHMM>.xlsx"`. The audit row was already committed by `get_db` before streaming began.

### 8.7 Daily email digest

1. Carol sets `PUT /me/notification-preferences {"non_critical_email":"daily_digest","digest_hour":9}` [#75]. This upserts `notification_preferences`.
2. During the day, each non-critical notification for Carol still inserts a `notifications` row, so the portal shows it at once. `Notifier.send` adds a `digest_items` row **instead of** an email. Critical ones (escalations, protected actions, deactivations with open tickets) are still emailed immediately.
3. **The `digest` job** (each tick, just before `send_outbox`):
   1. `due_users` selects users whose preference is `daily_digest`, whose `digest_hour` is at or before the current IST hour, who have pending items, and who have no `notification_digests` row for today's IST date (up to 100). It then commits.
   2. Per user, `send_digest` locks the pending items `FOR UPDATE SKIP LOCKED` and reloads Carol's `Actor` (if she is no longer active, all items are dropped).
   3. It re-checks visibility **now** with `visible_ticket_clause`. Items about tickets Carol can no longer see are marked `dropped_at`. Confidential tickets are re-masked to "Update on IBX-...".
   4. It inserts `notification_digests (user, date)` with `ON CONFLICT DO NOTHING`; the unique key guarantees one digest per day, even with two workers.
   5. It marks the items sent and queues one `notification_digest` email listing up to 50 items plus "and N more". It commits per user.
4. `send_outbox` delivers it in the same tick.

### 8.8 Removing a Super Admin (protected action)

1. Super Admin Dana calls `POST /users/{erin}/deactivate` [#19] on fellow Super Admin Erin. `deactivation_is_protected` is true, so `ProtectedActionService.request`:
   1. Locks all active Super Admin rows ordered by id, so concurrent requests cannot both pass the count.
   2. Checks there is no duplicate pending request and that at least 2 Super Admins would remain (3 or more active now).
   3. Inserts `protected_action_requests` (expires in 72 h); audits `protected_action_requested` (security limited).
   4. Publishes `ProtectedActionRequested`, which notifies the other Super Admins (critical).

   The response is `{"result":"protected_request_created", ...}`.
2. Super Admin Frank, who is neither requester nor target, calls `POST /protected-actions/{id}/approve` [#29]. The service locks the request, locks the Super Admins again, and re-checks the minimum. `AccountEffects.deactivate` then:
   1. sets Erin `deactivated`;
   2. revokes her refresh tokens and Spoke mappings;
   3. audits `user_deactivated`;
   4. publishes `UserDeactivated`.

   The request becomes `approved`, and `ProtectedActionDecided` notifies Dana and the Super Admins.
3. Erin's next API call fails in `get_actor` (user not active), giving 401. Her next refresh fails because the tokens were revoked.
4. If nobody decides within 72 hours, the `protected_action_expiry` job marks the request `expired`, audits `protected_action_expired` and notifies the requester.
5. The database backs this up: a CHECK constraint stops the decider being the requester or the target (6.5).

## 9. Configuration, Authentication and Security

### 9.1 Configuration

- **Where settings come from:** `app/core/config.py` `Settings` (pydantic-settings). Values are read from environment variables, then from a `.env` file in the current folder; otherwise the defaults apply. The object is frozen and cached (`get_settings`). The full variable list with defaults is in 1.5; the example file is `.env.example` (4.1).
- **Environments:** `ENV` = `dev` (default), `test` or `prod`.

  | Behaviour | dev | test | prod |
  |---|---|---|---|
  | `/docs` (Swagger UI) | yes | yes | **no** (`app/main.py`) |
  | Email sender | SMTP (Mailpit) | `InMemorySender` | SMTP |
  | `seed`, `reset-db` CLI | allowed | allowed | **refused** |
  | Start-up checks (`_enforce_prod_rules`) | — | — | `JWT_SECRET` at least 32 characters, `COOKIE_SECURE=true`, `SLA_TIME_SCALE=1.0`, a valid `FIELD_ENCRYPTION_KEY` when MFA roles are set |
- **Secrets:** `JWT_SECRET`, `SMTP_PASSWORD` and `FIELD_ENCRYPTION_KEY` are `SecretStr`, so they never appear in logs or `repr`. In prod, start-up also requires a valid Fernet `FIELD_ENCRYPTION_KEY` whenever `MFA_REQUIRED_ROLES` is set (13.0 #35, fixed).
- **Business configuration lives in the database, not in settings:** the SLA policy (`policy_versions`, edited by `PUT /policy`), the business calendar and holidays, departments, categories and grants. Changing them needs no restart.
- **Testing knob:** `SLA_TIME_SCALE` (for example `0.01`) shrinks every SLA duration for manual testing. It is forbidden in prod.

### 9.2 Authentication (who are you?)

| Mechanism | Details | Source |
|---|---|---|
| Passwords | Argon2 (`argon2-cffi` `PasswordHasher`). Policy: 12 to 128 characters with lowercase, uppercase, digit and symbol (`password_policy_error`). Unknown emails still run `dummy_verify`, so timing does not reveal which emails exist. | `app/core/security.py` |
| Access token | HS256 JWT signed with `JWT_SECRET`, claims `sub`, `iat`, `exp`, `jti` only (**no roles**), lifetime `ACCESS_TOKEN_MINUTES` (15). Sent as `Authorization: Bearer`. On every request the user is **reloaded** from the database, so deactivation and role changes apply at once. | `create_access_token`, `get_actor` |
| Refresh token | Random string; only its SHA-256 is stored (`refresh_tokens`). httpOnly cookie on path `/api/v1/auth`, `REFRESH_TOKEN_DAYS` (7). **Rotated on every use**; reuse of an old token revokes the whole family. | `AuthService.refresh` |
| MFA (optional) | TOTP (`pyotp`, 6 digits, ±30 s) for the roles in `MFA_REQUIRED_ROLES`. Secrets are Fernet-encrypted with `FIELD_ENCRYPTION_KEY`; 8 single-use recovery codes are stored hashed. A 5-minute "MFA token" (`aud=mfa`, no `jti`) bridges password and code. | `app/services/mfa.py` |
| Lockout and rate limits | 5 wrong passwords or MFA codes lock the account for 15 min. Fixed-window limits: login 10 per minute per IP and per email; signup 5 per hour; resend and forgot 3 per hour. The subjects are stored hashed. | `auth.py`, `signup.py`, `rate_limit.py` |
| One-time links | Verification (24 h) and reset (1 h) tokens are stored hashed in `email_tokens`, single use. A reset revokes all refresh tokens. The raw token is in the queued email until it is sent; then `send_outbox` redacts it (13.0 #19). | `signup.py`, `auth.py`, `send_outbox.py` |

### 9.3 Authorization (what may you do?)

All rules live in `app/policy/` (4.6). Routes never check roles themselves.

1. **Roles:**
   - `employee` (everyone);
   - `spoke` (not a role column: an active `spoke_assignments` row for a department);
   - `admin`;
   - `super_admin`.
2. **Permission flags** (`compute_permissions`, 24 flags) are coarse switches, also sent to the frontend in `Me.permissions`. The policy key `admins_can_manage_departments` decides whether Admins get `departments.manage` and `users.manage_roles`.
3. **Visibility** (`is_visible` and `visible_ticket_clause`) decides whether a ticket exists for you. Invisible means **404, identical to missing**.
4. **Ticket actions** (`ACTION_RULES`): your actor class on that ticket (requester, collaborator, assignee, team) times its status.
5. **Account rules** (`permissions.py`): the signup approval chain; Admins manage only employees; nobody changes their own state; at least 2 active Super Admins; removing a Super Admin needs a second, independent Super Admin (protected actions).

### 9.4 Confidentiality guarantees

A confidential ticket (flag set by the requester or by a confidential category, never downgraded on transfer) is visible only to the requester, assignee, collaborators, Super Admins and holders of a grant on its category. **Spokes and Admins without a grant cannot see it.** It is kept out of:
- lists, counts, search, dashboards, KPIs and exports: every query applies `visible_ticket_clause`;
- notifications: `visible_only` per recipient, and masked text and email (`confidential_ticket_update`);
- digests: re-checked and re-masked at send time;
- the audit viewer: Admins do not see rows about tickets they cannot see;
- errors: the same 404.

`tests/security/test_confidentiality_leaks.py` checks all of these. The known exceptions are 13.0 #21 (deactivation count) and #27 (collaborators widen access by design).

### 9.5 Web and transport security

| Protection | Implementation |
|---|---|
| Security headers | `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY` on every response; `Cache-Control: no-store` on `/api/v1/auth/*` and attachment downloads (`SecurityHeadersMiddleware`) |
| CORS | only `CORS_ORIGINS` (a wildcard is rejected at start-up), credentials allowed, explicit method and header lists; exposes `X-Request-ID` and `Content-Disposition` (`app/main.py`) |
| CSRF | the cookie is used only by `/auth/refresh` and `/auth/logout`, which check `Origin` (`require_allowed_origin`); `SameSite` defaults to `lax`. All other routes need the bearer header, which a foreign site cannot send. |
| Body size | `BodySizeLimitMiddleware`: 413 for bodies over `MAX_UPLOAD_BYTES` + 64 KiB, counted while streaming, so chunked uploads are covered too |
| Uploads | type allow-list **and** content sniffing; sanitised file names; random storage keys; path-traversal guard in `LocalStorage._path`; downloads forced as attachments with `nosniff`. The virus scanner is a no-op (13.0 #8). |
| Injection | SQL only through SQLAlchemy (bound parameters); LIKE search terms escaped; Jinja autoescape for HTML email; spreadsheet formula neutralising (`safe_cell`) |
| Audit | immutable `audit_log` and `ticket_events` (database triggers); in Docker the app's database role `ibotix_app` has no UPDATE or DELETE on them (`docker-compose.full.yml`, 4.2) |
| Request tracing | `X-Request-ID` on every response and error; JSON access log `app.access` with route template, status, duration and user id (no bodies, no tokens) |

## 10. Third-Party Integrations and Dependencies

### 10.1 External systems

| System | Used for | Adapter | Configured by | If it is down |
|---|---|---|---|---|
| **PostgreSQL 16** | all data, advisory locks, `pg_trgm` search, SQL function `working_seconds` | SQLAlchemy + psycopg 3 (`app/core/db.py`) | `DATABASE_URL`, `TEST_DATABASE_URL` | API 500s; `/health/ready` fails; the worker logs job failures |
| **SMTP server** (Mailpit in development, port 1025; web UI 8025, or 8026 in the full compose) | sending email | `SmtpSender` (`app/integrations/email/smtp.py`) | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | nothing is lost: rows stay in `email_outbox` and retry with backoff (1, 5, 30, 120 min), then become `failed` after 5 attempts |
| **Local disk** | attachment files | `LocalStorage` | `ATTACHMENT_DIR` | upload and download fail (500); `StorageError` for a missing file |
| **Virus scanner** | placeholder only | `NoopScanner` | — | — |
| **Authenticator apps** (Google Authenticator and others) | TOTP codes | `pyotp` (standard RFC 6238, offline) | `MFA_REQUIRED_ROLES` | — |

There are no payment, chat, SSO or cloud-storage integrations. The adapters (`Storage`, `Scanner`, `EmailSender` protocols) are the places to add S3, ClamAV or an email API later: implement the protocol and change the `build_*` function.

### 10.2 Python dependencies (`pyproject.toml`, pinned exactly)

| Package | Version | Why |
|---|---|---|
| fastapi | 0.162.0 | web framework, validation, OpenAPI |
| uvicorn | 0.54.0 | ASGI server (`uvicorn app.main:app`) |
| pydantic, pydantic-settings | 2.14.1, 2.16.2 | schemas; settings from the environment |
| sqlalchemy | 2.0.55 | ORM and query builder (synchronous) |
| alembic | 1.20.1 | migrations |
| psycopg[binary] | 3.3.6 | PostgreSQL driver |
| argon2-cffi | 25.1.0 | password hashing |
| pyjwt | 2.15.1 | access and MFA tokens |
| pyotp | 2.10.0 | TOTP |
| cryptography | 50.0.2 | Fernet encryption of MFA secrets |
| python-multipart | 0.0.32 | file uploads (`UploadFile`) |
| email-validator | 2.3.0 | `EmailStr` validation |
| jinja2 | 3.1.6 | email templates |
| openpyxl | 3.1.5 | XLSX export (R2-B) |
| reportlab | 4.4.10 | PDF export (R2-B) |

**Development:** pytest 9.2.0, pytest-cov 7.1.0, httpx 0.28.1 (needed by `TestClient`), ruff 0.17.3 (lint and format), mypy 2.4.0 (strict typing), and type stubs for openpyxl and reportlab. The virtual environment has no pip; install with `uv pip install --python .venv/Scripts/python.exe ...` (`CLAUDE.md`). `CLAUDE.md` forbids adding packages outside this list (no Redis, no Celery).

## 11. Background Jobs, Scheduled Tasks, Signals, Hooks

### 11.1 Scheduled work: the worker process

There is **no cron, Celery or Redis**. One long-running process, `python -m app.worker` (the `worker` service in `docker-compose.full.yml`), runs every job in a fixed order every `WORKER_TICK_SECONDS` (default 15 s). The loop is in 4.4; each job is in 4.11.

| Order | Job | Finds | Does | Idempotency guard |
|---|---|---|---|---|
| 1 | `sla_scan` | running SLA timers whose next step has passed | records escalation steps, raises levels, timeline and audit, warning and escalation notifications | advisory lock (one scanner) + unique `escalation_events` key |
| 2 | `reminders` | due requester-reminder and hold-review timers | notifies the requester or owner | `escalation_events` key `REMINDER` or `HOLD_REVIEW` per cycle |
| 3 | `auto_close` | due auto-close timers on resolved tickets | closes with reason `auto` | ticket row lock + status re-check |
| 4 | `protected_action_expiry` | pending requests past 72 h | marks expired, audits, notifies the requester | row lock + status re-check |
| 5 | `housekeeping` | old unlinked uploads, tokens, rate-limit rows | deletes them (rows, then files) | — (deletion is naturally repeatable) |
| 6 | `digest` | daily-digest users past their hour | one digest email per IST day | unique `(user_id, digest_date)` |
| 7 | `send_outbox` | pending emails due now | sends via SMTP, with retries | `SKIP LOCKED`; at-least-once delivery |

**Running two workers is safe** (`tests/integration/test_scheduler_idempotency.py`, `tests/scenarios/test_18_concurrency.py`), though one is enough. **Monitoring:** `GET /health/worker` (503 after 3 missed ticks), the `worker_heartbeat.details` JSON (per-job counts and failed job names), and the `app.worker` log lines.

### 11.2 In-process domain events (the "signals")

`app/core/events.py` has a tiny synchronous **event bus**. Services call `publish(session, event)` (through `Workflow.publish` for ticket actions), and the bus calls every handler registered for that exact event class, **immediately, in the same database transaction**. If a handler fails, the whole request rolls back. There is no queue, retry or async dispatch.

- **Registration:** `register_all()` in `app/services/handlers/__init__.py`. It clears the bus, registers the SLA handlers, then the notification handlers. It is called by `create_app`, `seed` and tests.
- **Events:** ticket events (created, acknowledged, assigned, status changed, team update, ETA, priority, comment, collaborator, resolved, closed, reopened, cancelled, transferred), SLA events (`SlaWarningRaised`, `EscalationRaised`), and account events (`SignupVerified`, `SignupDecided`, `UserDeactivated`, `ProtectedActionRequested`, `ProtectedActionDecided`, `ConfidentialGrantChanged`).
- **What reacts:** see the handler tables in 4.9.6.
- **Registration happens in every process that publishes events:**
  - the API in `create_app` (`app/main.py`);
  - the worker in `main()` (`app/worker/main.py`);
  - the seed in `seed()` (`app/seed/run.py`).
- **History:** the worker call was missing until finding 13.0 #37 was fixed. Until then, SLA warnings, escalations and auto-close notifications were never sent by the real worker. `tests/integration/test_worker_loop.py::test_main_registers_event_handlers` now empties the global bus, runs the real `main()` with the loop stubbed out, and checks the handlers are back.

### 11.3 Database triggers and constraints as hooks

- Triggers `audit_log_immutable` and `ticket_events_immutable` reject UPDATE and DELETE (migrations `b05_audit_log` and `b04_tickets_sla_notifications`; 6.5).
- Many CHECK and partial UNIQUE constraints enforce invariants (6.5). The unique keys used for idempotency are on `escalation_events`, `notifications (user_id, dedupe_key)`, `notification_digests` and `ticket_counters`.

### 11.4 FastAPI hooks

- **Middleware** (outermost first): `RequestContextMiddleware`, `SecurityHeadersMiddleware`, CORS, `BodySizeLimitMiddleware`, GZip (`app/main.py`).
- **Exception handlers** (`install_error_handlers`): `ApiError`, request validation, Starlette HTTP errors (405 → 404) and any unexpected exception → 500 `server_error`, logged with the request id.
- **Dependency `get_db`:** commit after the route, rollback on error.

## 12. Testing

### 12.1 How to run

```bash
source .venv/Scripts/activate          # Git Bash on Windows
docker compose up -d db mailpit        # PostgreSQL on 5433, Mailpit
pytest -q -p no:warnings               # whole suite (several minutes; Argon2 and concurrency tests are slow)
pytest tests/api/test_ticket_create.py -q   # one file
pytest -k "visibility" -q              # by name
```

**The full gate** (`CLAUDE.md`):

```bash
ruff check . && ruff format --check . && mypy app && mypy tests scripts alembic/env.py alembic/versions \
  && pytest -q -p no:warnings && alembic upgrade head && alembic check && python scripts/check_contract.py --full
```

**The release gate** adds coverage:

```bash
pytest --cov=app -q -p no:warnings
coverage report --fail-under=85
coverage report --include="app/policy/*,app/services/sla/*" --fail-under=95
```

The test database (`ibotix_test` by default) is **dropped and re-migrated** at the start of every run (`migrated_engine`). Never point `TEST_DATABASE_URL` at real data.

### 12.2 Strategy

| Layer | Folder | Style | Database |
|---|---|---|---|
| Unit | `tests/unit` (24 files) | pure functions, policy matrices, model constraints | real, rolled back |
| API | `tests/api` (33 files) | HTTP through `TestClient`, one file per router area | real, rolled back (`db` fixture, savepoints) |
| Integration | `tests/integration` (15 files) | handlers, jobs, outbox, CLI, seed, concurrency | real; `committed_db` and threads where locking matters |
| Scenarios | `tests/scenarios` (20 stories) | end-to-end user stories with `Portal`, the frozen clock moved forward, jobs run in-process | real, rolled back |
| Security | `tests/security` | route × role matrix, leak tests, auth hardening | real, seeded once per module |
| Performance | `tests/perf` | p95 budgets (list 300 ms, KPI 500 ms) and query plans on large generated data | real, large data inserted per module |

**Principles you will see everywhere:**
- **Real PostgreSQL, no mocks** of the database or services. Only time and email are faked.
- **Time is frozen** at `FROZEN_NOW` and moved explicitly (`clock.advance`, `Portal.advance`), so SLA tests are exact.
- **Guard-rail tests that fail when you add something without finishing it:**
  - the authorization matrix (a new route needs an entry);
  - `test_email_masking` (a new notification template needs a case);
  - `test_events` (handler counts compared with a fresh registry);
  - `test_contract_shapes` and `check_contract.py --full` (response shapes and `routes.txt`);
  - `test_db_session.test_enums_match_contract`.

### 12.3 Coverage and the latest result

- At the release gate (recorded in `CLAUDE.md` and the session report): **2,197 tests passed**, coverage **98 % overall** and **98 % on `app/policy` + `app/services/sla`**, both above the thresholds (85 % and 95 %).
- **3 tests in `tests/perf` failed only under coverage.** They are now skipped under `--cov` and run in a plain `pytest` run (13.0 #34). On 2026-10-29 two KPI budgets (`admin_kpis_default` about 700 ms, `admin_dashboard` about 590 ms, budget 500 ms) also failed **without** coverage. The same happened on the unchanged code, so it is the machine's speed that day, not a regression. Re-measure on the target hardware.

### 12.4 Gaps and suggestions

- The real worker loop is not run end to end against SMTP. `main()` itself is tested only for handler registration (`test_main_registers_event_handlers`, added with the fix of 13.0 #37).
- No tests run against a real SMTP server or a real virus scanner (none exists).
- No migration downgrade tests (only `upgrade head` and `alembic check`).
- No load test of the API under concurrent HTTP traffic; perf tests measure single queries.
- Frontend integration is covered by contract tests only (`docs/FRONTEND-INTEGRATION.md`).

## 13. Code Quality Review

### 13.0 All findings

Every finding from reading the code, in the order found. Columns: number, issue, location, impact, suggestion. 13.1 groups them by priority.

| # | Finding | Where | Impact | Suggestion |
|---|---|---|---|---|
| 1 | `TIMEZONE` setting is never read. IST is hard-coded as a fixed +05:30 offset. | `app/core/config.py` `timezone`; `app/core/clock.py` `IST` | Changing `TIMEZONE` silently does nothing. | Remove the setting, or document it as fixed. (A fixed IST is an approved decision; see R.14 in the guide.) |
| 2 | **Fixed:** removed, with its test. `require_roles` is unused dead code. | `app/api/deps.py` lines 58-64 | None at runtime; it invites role checks outside `app/policy/`, against the project rule. | Delete it. |
| 3 | `app/core` imports `app/models` (`TimerKind`, `CloseReason`), so the core layer depends on the model layer. | `app/core/events.py` lines 9-10 | Risk of circular imports as the code grows. | Move these two enums to `app/core/enums.py`, or accept the dependency and document it. |
| 4 | `app/policy` imports `app/services/policy` (only `PolicyConfig`), so policy depends on a service. | `app/policy/allowed_actions.py` line 12 | Blurs the layering ("policy is pure"); a future import from `services/policy.py` back into policy would be circular. | Move `PolicyConfig` (a pure Pydantic model) to `app/schemas/policy.py` or `app/core`. |
| 5 | **Fixed:** constant moved to `app/models/notification.py`. The API imports the worker module only for the constant `HEARTBEAT_NAME`. | `app/api/routers/health.py` line 13 | Importing the API also loads `app/worker/jobs` and all job modules. | Move the constant to `app/models/notification.py` or `app/core`. |
| 6 | Only the last part of a validation-error location is kept, so errors inside list items are keyed by index (`"0"`) and nested fields can collide. | `app/core/errors.py` `_validation_fields` | The frontend sometimes cannot match an error to its field. | Join the location parts (for example `query.status`), keeping the contract's field names. |
| 7 | `fetch_page` runs two queries (count plus page) for every list. | `app/core/pagination.py` | Fine at the current scale (`docs/SECURITY.md` performance results). | Keep; revisit only if lists slow down. |
| 8 | The virus scanner is a no-op that marks everything clean. | `app/integrations/scanner/noop.py` | Uploaded files are not scanned. | Documented in `docs/SECURITY.md`; plug in a real scanner before handling untrusted files. |
| 9 | **Fixed:** rendered from the template via `enqueue_email`. The password-reset email is built inline in `AuthService` (lines 325-349), and the outbox row is added directly. `app/templates/email/password_reset.txt.j2` and `.html.j2` exist and are listed in `SUBJECTS`, but nothing renders them. | `app/services/auth.py`; `app/templates/email/password_reset.*` | Duplicated email logic. Template edits have no effect, and `FRONTEND_BASE_URL` handling differs from `enqueue_email`. | Use `enqueue_email(..., "password_reset", {...})` like every other email (`CLAUDE.md` B07 already notes this). |
| 10 | Timestamps have no database defaults; every insert relies on the service setting `created_at` and `updated_at`. | `app/models/base.py` `Timestamps` | A missed assignment fails with a NOT NULL error, so it is caught, not silent. This is deliberate (time only through the injected clock). | Keep, and note it for new contributors. |
| 11 | The visibility rule exists twice: `is_visible` (Python) and `visible_ticket_clause` (SQL). | `app/policy/visibility.py` | A change made in only one place would let lists and detail pages disagree, which could leak confidential tickets. | Keep them side by side (as now) and change both together; the leak tests are the safety net. A unit test that compares both forms on generated cases would make drift impossible to miss. |
| 12 | Duplicated small definitions: the LIKE-escape helper three times (`_escape_like` in two query modules, `UserService._escape`); `ACTIVE_STATUSES` in `app/queries/tickets.py` and `app/policy/allowed_actions.py` (same set; `OPEN_STATUSES` in `ticket_reads.py` and `CLOSED_TICKET_STATUSES` in `protected_actions.py` are the same idea); `_retry_after` in `auth.py`, `mfa.py` and `signup.py`; `_user_ref` in `signup.py` duplicating `spokes.user_ref`. | the files named | Several places to update when a rule changes. | Define each once (for example in `app/core/enums.py` and a small shared helper module). |
| 13 | `app/queries`, `app/schemas`, `app/services` and `app/integrations` have no `__init__.py` (implicit namespace packages); every other package has one. | folder listing | Works today. Some tools (coverage source discovery, older linters, packaging) treat namespace packages differently. | Add empty `__init__.py` files for consistency. |
| 14 | Layering is not strict: `app/queries/kpis.py` imports from `app/schemas/reports.py` and `app/services/sla/escalation.py`; `app/schemas/tickets.py` imports `SlaState` from `app/services/sla/sla_object.py`; `app/queries/tickets.py` imports `SlaStateFilter` from schemas. | the files named | Lower layers depend on higher ones, which makes circular imports more likely. | Move shared constants and plain data types (`CREATION_CONTACT`, `AgingBucket`, `SlaState`, `SlaStateFilter`) to a neutral module. |
| 15 | The name `Actor` means two different things: the authenticated caller (`app/policy/__init__.py`) and a response type alias `UserRef \| SystemActor` (`app/schemas/common.py` line 33). | the files named | Confusing when reading imports. | Rename the schema alias (for example `ActorOut`). |
| 16 | Business rules are split between schemas and services: password strength, cross-field policy rules, `work_end` after `work_start`, and "ETA or a reason" are checked in services, not in the request schemas. | `app/schemas/signup.py`, `policy.py`, `calendar.py`, `workflow.py` | Deliberate, so the 422 can name the right field and use the contract's message; but you must look in two places to see every rule. | Keep; this document lists where each rule lives. |
| 17 | Two ways to build the current user's `Actor`: `MeService.load_active_actor` and `app/policy/actors.load_actor` do the same thing (`UserService._to_item` builds a third, temporary one). | `app/services/me.py`, `app/policy/actors.py` | A change (for example a new `Actor` field) must be made twice. | Keep one loader in `app/policy/actors.py` and call it from `MeService`. |
| 18 | `_accepting_department` and `_category` are copied between ticket creation and transfer; the escalation recipient helpers (`_active_user`, `_department_spokes`, `_active_users_with_role`) duplicate `handlers/recipients.py`. | `app/services/tickets.py`, `workflow/transfer.py`, `sla/escalation.py` | The rules for "accepting department" and "valid category" could drift apart. | Move each helper to one module and import it. |
| 19 | **Fixed:** tokens redacted once an email is sent or finally fails. **Raw one-time tokens are stored in the database.** `email_outbox.context` holds the raw verification token (`signup.py` `_issue_verification`) and the full reset URL with its token (`auth.py` `_enqueue_reset_email`); `body_text` and `body_html` contain them too. Only the token *hash* is in `email_tokens`. | `app/services/signup.py` line 397, `app/services/auth.py` lines 324-348 | Anyone with read access to `email_outbox` (backups, read replicas, support staff) can use an unexpired link (24 h for verification, 1 h for reset). | Do not put the token into `context`, and clear the bodies of sent rows (a housekeeping step), or keep outbox rows only briefly. |
| 20 | **Fixed** for insert failures (the file is deleted); a failed final commit is still possible but rare. An uploaded file is written to disk before the database row is committed. If the request later fails, the file stays on disk with no row; housekeeping only deletes files of rows it removes. | `app/services/attachments.py` `upload` | Orphan files slowly fill the attachment volume. | Write to storage after the row is saved, or add a periodic sweep for keys that have no row. |
| 21 | **Needs a decision:** Appendix B09 defines `open_ticket_count` as all owned or assigned open tickets, which includes confidential ones. `AccountEffects.open_ticket_count` counts confidential tickets too, and returns the number to whoever deactivates the user (an Admin can deactivate employees). | `app/services/protected_actions.py` lines 60-65 | Reveals how many confidential tickets someone owns or is assigned. A count only, but the rule is "never leak confidential tickets through any count". | Count only tickets visible to the caller, or confirm this exception (open question in `CLAUDE.md` B09). |
| 22 | **Needs a decision:** no rule in the guide. Making a category confidential (or not) does not change the `confidential` flag of tickets already in it. | `app/services/categories.py` `update` | Existing tickets keep their old visibility. | Decide the rule (open question in `CLAUDE.md` B10) and implement or document it. |
| 23 | **Not a bug:** Appendix R.4 says "resume `eta` (add the paused time to `paused_seconds`; the ETA date does not move)". Pausing a timer records `paused_seconds` but does not move `warning_at`, `due_at` or `l3_at` on resume. | `app/services/sla/timers.py` `resume` | A ticket that waited long for the requester can breach right after resuming. **Unclear - needs confirmation** whether intended (Appendix R.4 in the guide is the place to check). | Confirm the rule; if pauses should extend deadlines, shift the times on resume. |
| 24 | The visibility check per recipient (`visible_only`, `_visible_only`) loads the user's actor and relationships with several queries **for each recipient**. | `app/services/handlers/recipients.py`, `app/services/sla/escalation.py` | N+1 queries for large departments or escalations to all admins; slower writes. | Batch-load actors, or filter recipients with `visible_ticket_clause` in one query. |
| 25 | Exports load up to 50,000 ticket objects and build XLSX and PDF files fully in memory. | `app/services/exports/__init__.py`, `writers.py` | High memory use per export request. | Acceptable at current limits; stream rows (`yield_per`) if limits grow. |
| 26 | **By design:** B09 specifies lookup and members for every user (returning only `UserRef`). `GET /users/lookup` lets any authenticated user search every active user by name or email (20 results). | `app/services/users.py` `lookup` | Exposes the staff directory to all employees. Likely intended (pickers for collaborators); confirm. | Document it, or restrict it to staff and Spokes. |
| 27 | A collaborator can see a ticket, including a confidential one, without a confidential grant. | `app/policy/visibility.py` `is_visible`; `app/services/collaborators.py` | By design, but it means team members can widen access to a confidential ticket. | Keep, but mention it in the confidentiality documentation. |
| 28 | **Fixed:** naive values are read as UTC (`assume_utc`). `created_from` and `created_to` on `GET /tickets` and `/reports/export`, and `from` and `to` on `GET /audit`, are plain `datetime`, so a value without a time zone is accepted and compared with a `timestamptz` column in the database session's time zone (not set by the app; UTC in the Docker image). `awaiting_before` and the KPI `from`/`to` require a time zone (`AwareDatetime`). | `app/api/routers/tickets.py` `ticket_list_query`, `app/api/routers/audit.py` | A frontend sending `2026-10-27T00:00` meaning IST gets results shifted by 5 h 30 min. | Use `AwareDatetime` everywhere (422 when the zone is missing), or treat naive values as IST explicitly. |
| 29 | **Fixed:** `app/api/params.py`. `exports.py` imports `TicketListParams` from another router (`tickets.py`). | `app/api/routers/exports.py` | Routers depend on each other; moving or renaming the tickets router breaks exports. | Move `ticket_list_query` and `TicketListParams` to a shared module (for example `app/api/params.py`). |
| 30 | **By design:** see #26. `GET /departments/{id}/members` returns the members of **any** department to any logged-in user; the route takes `_actor` and the service does no check. | `app/api/routers/users.py` `department_members`, `app/services/users.py` | Like #26, it exposes who works where. Probably intended for the assign picker; **Unclear - needs confirmation**. | Restrict it to the department's team and Admin+, or document it. |
| 31 | **Needs a decision:** B19 says housekeeping's deletes "are the only hard deletes in the system", so retention needs a rule. (The token part is fixed by #19.) Housekeeping never deletes `email_outbox` rows (sent or failed), `notifications`, `digest_items` or `escalation_events`. | `app/worker/jobs/housekeeping.py` | Unbounded table growth. Combined with #19, the rendered bodies containing one-time links are kept **forever**. | Add retention rules (for example sent outbox rows after 30 days, read notifications after 180 days); agree them with the business. |
| 32 | **Needs a decision:** R2-C2 does not say what happens to queued items when the preference changes. When a user switches from `daily_digest` to `immediate` or `off`, the already queued `digest_items` are never sent and never dropped (`due_users` only selects `daily_digest` users). If they switch back later, the old items show up in a digest. | `app/worker/jobs/digest.py` `due_users`; `app/services/preferences.py` `replace` | Lost or very late notifications by email (the portal still has them). | On a preference change, drop (or flush) pending items; or let `due_users` pick any user with pending items. |
| 33 | **Fixed.** `audit_log` is immutable but missing from `IMMUTABLE_TABLES` in `tests/conftest.py`, so `committed_db` cleanup cannot delete it. Three test files `TRUNCATE audit_log` by hand (`CLAUDE.md` B05 asked for it to be added). | `tests/conftest.py` | A new committed test that writes audit rows fails in cleanup or leaks rows into later tests. | Add `audit_log` to `IMMUTABLE_TABLES` and remove the manual truncates. |
| 34 | **Fixed:** skipped under coverage. The perf tests run inside the normal suite, and fail under `--cov` (the release gate) because instrumentation slows the queries past the budgets. | `tests/perf/` | The release gate is red for a reason unrelated to correctness; people learn to ignore failures. | Give perf tests a marker and run them in a separate, non-coverage step (or skip them when coverage is active). |
| 35 | **Fixed.** The prod start-up checks do not require `FIELD_ENCRYPTION_KEY` when `MFA_REQUIRED_ROLES` is set. The first MFA enrolment then raises `RuntimeError` (500) in `MfaService._fernet`. | `app/core/config.py` `_enforce_prod_rules`; `app/services/mfa.py` | Admins cannot log in once MFA is switched on with a missing key. | Validate at start-up: MFA roles set ⇒ a valid Fernet key. |
| 36 | **Fixed:** one row claimed and committed at a time. `send_outbox` sends the whole batch, then commits once. A crash or failed commit after some SMTP sends makes those emails go out again. | `app/worker/jobs/send_outbox.py` | Occasional duplicate emails (at-least-once delivery). | Acceptable; or commit after each email. |
| 37 | **Fixed.** **The worker never registered the domain-event handlers.** `register_all()` was called only by `create_app` and `seed`; `python -m app.worker` left the bus empty (verified: 0 handlers after importing `app.worker.main`), so events published by worker jobs reached nobody. | `app/worker/main.py` `main()` | **Before the fix:** in production no SLA warning or escalation notification or email was sent (steps, levels and timeline are still recorded), auto-closed tickets notify nobody, and their timers are not stopped. Tests miss it because they run jobs in a process where handlers were already registered. | **Done:** `register_all()` is now called in `main()`, and `test_main_registers_event_handlers` fails if it is removed (checked). |
| 38 | **Fixed.** A ticket export with `created_from` or `created_to` without a time zone crashed with a 500: `ticket_filter_values` calls `format_utc`, which rejects naive datetimes. | `app/services/exports/__init__.py` | Export failed for such dates. | Fixed with #28 (`assume_utc` in `app/api/params.py`); `test_dates_without_a_time_zone_are_read_as_utc`. |

### 13.1 Prioritised summary and status

A fix round on 2026-10-29 resolved every finding that did not need a business decision. The full test suite was run afterwards (12.3).

**Fixed:** #2, #5, #9, #19, #20, #28, #29, #33, #34, #35, #36, #37, #38.

**Not bugs (confirmed against the guide):** #23 (Appendix R.4), #26 and #30 (B09), #27 (visibility rule R.2).

**Waiting for a business decision** (`CLAUDE.md` forbids inventing rules):

| # | Question | Options |
|---|---|---|
| 21 | Should the deactivation response count confidential tickets the caller cannot see? | keep the guide's definition / count only tickets visible to the caller |
| 22 | When a category becomes confidential (or stops being), what happens to its existing tickets? | leave them / mark them confidential (never downgrade) |
| 31 | How long are sent emails, notifications and digest items kept? | keep forever (current) / add retention periods to housekeeping |
| 32 | When a user leaves `daily_digest`, what happens to queued items? | drop them / send them in one last digest / email them individually |

**Still open, not urgent** (maintainability and performance): #1, #3, #4, #6, #7, #8, #10 to #18, #24, #25.

### 13.2 What is done well

- **One place for every rule.** Permissions and visibility live only in `app/policy/`; routers are one-liners; services never commit. This makes the code easy to audit.
- **Confidentiality is built in, not bolted on.** It covers one SQL clause in every query, masking in notifications and digests, a shared 404, and dedicated leak tests.
- **Idempotent, concurrent-safe background work.** Advisory locks, `SKIP LOCKED`, unique step keys and a transactional outbox. Two workers can run, and the test suite proves it with real threads.
- **Deterministic time.** Everything uses the injected `Clock`, so SLA behaviour is tested to the minute.
- **Strong guard-rail tests:** the route × role matrix, contract-shape checks, email masking per template, a migrated real PostgreSQL every run, and 98 % coverage.
- **Defence in depth on the database:** immutable audit and timeline triggers, many CHECK and unique constraints, and an application role without UPDATE or DELETE on audit tables.

## 14. Glossary

| Term | Meaning in this project |
|---|---|
| **Actor** | (1) The logged-in caller, `app/policy/__init__.py` `Actor`. (2) In responses, the person or "System" who did something (`UserRef \| SystemActor`). |
| **Actor class** | How the actor relates to one ticket for action rules: `requester`, `collaborator`, `assignee`, `team` (`ActorClass`). |
| **Admin / Super Admin** | Global roles. Admins see all non-confidential tickets and approve employees; Super Admins can do everything, including policy, grants and managing Admins. |
| **Allowed actions** | The list in every ticket response of what the caller may do now (`compute_allowed_actions`); the frontend shows buttons from it. |
| **Appendix A / R / S** | Sections of `Backend_Build_Guide_v2.md`: A = API contract, R = business rules, S = seed data. |
| **Audit log** | Immutable record of significant actions (`audit_log`); viewed through `GET /audit`. "Security limited" rows are visible to Super Admins only. |
| **Business mode** | SLA times count only working hours on working days, skipping holidays (R2-C1). The opposite is **calendar mode** (wall-clock time). |
| **Checkpoint** | When a ticket has no ETA, the "next update by" time given on acknowledgement (`next_checkpoint_at`). |
| **Collaborator** | A person added to a ticket by the team; can see and comment on it, even if confidential. |
| **Confidential ticket / grant** | A ticket only specific people may see; a **grant** gives a user access to all confidential tickets of one category. |
| **Contract** | `contract/routes.txt` + Appendix A: the API the frontend relies on, checked by `scripts/check_contract.py`. |
| **Creation contact** | The immediate alert to the escalation contact when a **critical** ticket is created (`CREATION_CONTACT`). |
| **Cycle** | A timer's run number; it increases when a timer restarts (reopen, transfer, new waiting period). Dedupe keys include it. |
| **Dedupe key** | A unique key per user and notification (`notifications (user_id, dedupe_key)`) that prevents duplicates. |
| **Digest** | One daily email that collects non-critical notifications for users who chose `daily_digest`. |
| **Domain event** | A frozen dataclass such as `TicketCreated`, published to the in-process `EventBus`; handlers react in the same transaction. |
| **Escalation contact** | One person per department who receives level-2 and creation alerts and may view the department's non-confidential tickets. |
| **Escalation level** | 0 to 3 on a ticket: the highest level among its SLA timers. L1 = warning, L2 = breach, L3 = serious breach, then repeats. |
| **ETA** | The promised resolution time set by the team; changing it needs a reason. |
| **Frozen clock** | `FrozenClock`, a controllable clock used in tests and the seed. |
| **IST** | India Standard Time, UTC+05:30, used for ticket years, business days, digests and display text. |
| **MFA token** | A 5-minute JWT that proves the password step passed, exchanged for real tokens after the TOTP code. |
| **Outbox** | `email_outbox`: emails are written to the database in the request's transaction and sent later by the worker, so no email is lost or sent for a rolled-back change. |
| **Owner** | The Spoke who acknowledged the ticket and is accountable for it. |
| **Policy** | The versioned SLA and workflow settings (`policy_versions`); each change inserts a new version. |
| **Protected action** | Deactivating or demoting a Super Admin; needs approval by a second, independent Super Admin within 72 h. |
| **Public detail** | The shortened timeline text shown to non-staff (for example without the internal reason). |
| **Requester** | The person who raised the ticket. |
| **SLA** | Service-level agreement: time limits for first response, progress updates and the ETA. |
| **SLA time scale** | `SLA_TIME_SCALE`, a multiplier that shrinks all SLA durations for testing (must be 1.0 in prod). |
| **Spoke** | A department's support person (an active `spoke_assignments` row). Spokes see and work their department's tickets. |
| **Step** | One recorded escalation threshold (`L1`, `L2`, `L3`, `L3_REPEAT_n`, `CREATION_CONTACT`, `REMINDER`, `HOLD_REVIEW`) in `escalation_events`. |
| **Team** | For a ticket: its department's Spokes, its owner, Admins and Super Admins (if they can see it). |
| **Ticket number** | `IBX-<DEPT>-<IST year>-<6 digits>`, used in URLs instead of the UUID. |
| **Timeline** | The ticket's immutable history (`ticket_events`): comments, status changes, escalations. |
| **Timer** | A row in `sla_timers` (initial response, progress update, ETA, requester reminder, hold review, auto-close). |
| **Visibility clause** | `visible_ticket_clause(actor)`, the SQL condition added to every ticket query. |
| **Worker** | The background process `python -m app.worker` that runs the scheduled jobs. |

## 15. Quick-Reference Tables

### 15.1 Commands

| Task | Command |
|---|---|
| Start PostgreSQL and Mailpit | `docker compose up -d db mailpit` |
| Activate the virtual environment (Git Bash) | `source .venv/Scripts/activate` |
| Apply migrations | `alembic upgrade head` |
| New migration | `alembic revision --autogenerate --rev-id <id> -m "..."` (then hand-edit; `CLAUDE.md`) |
| Run the API | `uvicorn app.main:app --reload` → http://localhost:8000/docs |
| Run the worker | `python -m app.worker` |
| First Super Admin | `ADMIN_PASSWORD=... python -m app.cli create-super-admin --email you@ibotix.ai --name "Your Name"` |
| Demo data | `python -m app.cli seed` (password `Ibotix2026Demo`, emails `firstname.lastname@ibotix.ai`) |
| Wipe and recreate the database (dev/test) | `python -m app.cli reset-db` |
| Export OpenAPI | `python -m app.cli export-openapi openapi.json` |
| Clear a user's MFA | `python -m app.cli mfa-reset --email user@ibotix.ai` |
| Tests | `pytest -q -p no:warnings` |
| Lint, format, types | `ruff check . && ruff format --check . && mypy app` |
| Contract check | `python scripts/check_contract.py --full` |
| Perf data | `python -m scripts.perf_seed` |
| Full stack in Docker | `docker compose -f docker-compose.full.yml up -d` |

### 15.2 Ports and URLs (development)

| What | Where |
|---|---|
| API | http://localhost:8000/api/v1, docs at `/docs` |
| PostgreSQL | localhost:**5433** (5432 is taken by a local Windows PostgreSQL) |
| Mailpit SMTP / web UI | localhost:1025 / http://localhost:8025 (8026 in `docker-compose.full.yml`) |
| Frontend (expected) | http://localhost:5173 (`CORS_ORIGINS`, `FRONTEND_BASE_URL`) |

### 15.3 "Where do I change...?"

| I want to... | Change |
|---|---|
| add an endpoint | the contract first (Appendix A + `contract/routes.txt`), then the schema (`app/schemas`), the service (`app/services`), the router (`app/api/routers`), a matrix entry in `tests/security/test_authorization_matrix.py` |
| change who can see tickets | `app/policy/visibility.py`, **both** `is_visible` and `visible_ticket_clause` |
| change who can do a ticket action | `ACTION_RULES` in `app/policy/allowed_actions.py` |
| change a permission flag | `app/policy/flags.py` `compute_permissions` |
| change SLA hours | at runtime: `PUT /policy`; defaults: the policy seed in migration `b03_identity_org_policy` |
| change working hours or holidays | `PUT /calendar`, `POST /calendar/holidays` |
| change how timers react to events | `app/services/handlers/sla_handlers.py` and `Timers.reconcile` |
| change who is notified | `app/services/handlers/notification_handlers.py` (tickets), `app/services/sla/escalation.py` (escalations) |
| change an email's wording | `app/templates/email/<kind>.txt.j2` and `.html.j2`; subject in `app/services/email_templates.py` |
| add a background job | a module in `app/worker/jobs/` with `run(session, context) -> int`, registered in `registered_jobs()` before `send_outbox` |
| add a setting | `app/core/config.py` `Settings`, `.env.example`, section 1.5 |
| add a table or column | `app/models/*`, then an Alembic migration |

### 15.4 Status codes at a glance

| Status | Code(s) | Typical cause |
|---|---|---|
| 401 | `unauthenticated`, `invalid_credentials` | no or bad token; wrong email or password |
| 403 | `forbidden`, `account_state` | role cannot do this; account not active |
| 404 | `not_found` | missing **or hidden**; wrong method |
| 409 | `conflict`, `invalid_transition`, `protected_action_blocked` | duplicate or changed state; wrong ticket status; Super Admin minimum |
| 410 | `token_expired` | old verification or reset link |
| 413 / 415 | `file_too_large` / `unsupported_file_type` | upload limits |
| 422 | `validation_error` (+ `fields`) | bad input |
| 429 | `too_many_attempts`, `rate_limited` (+ `retry_after_seconds`) | lockout; rate limit |
| 500 | `server_error` | bug or infrastructure failure (look up `request_id` in the logs) |

### 15.5 Ticket statuses and timers

| Status | Meaning | Running timers |
|---|---|---|
| `new` | raised, not acknowledged | initial response |
| `acknowledged` | a Spoke owns it | progress update, ETA |
| `assigned` | given to a worker | progress update, ETA |
| `in_progress` | being worked on | progress update, ETA |
| `awaiting_requester` | waiting for the requester | progress and ETA paused; requester reminder |
| `on_hold` | parked until a review date | progress and ETA paused; hold review |
| `resolved` | fix proposed | auto-close |
| `closed` | finished (confirmed, by the team, or automatically) | none |
| `reopened` | the fix did not hold | initial response (new cycle) |
| `cancelled` | withdrawn | none |

### 15.6 Key files to read first

1. `CLAUDE.md`: the project rules and conventions.
2. `app/main.py`: how the app is assembled.
3. `app/api/deps.py`: authentication and the per-request session.
4. `app/policy/visibility.py` and `app/policy/allowed_actions.py`: who sees and does what.
5. `app/services/workflow/common.py`: the skeleton of every ticket action.
6. `app/services/sla/timers.py` and `scanner.py`: the SLA engine.
7. `app/services/handlers/notification_handlers.py` and `app/services/notifications.py`: notifications.
8. `tests/factories.py` and `tests/scenarios/helpers.py`: how to write tests.
