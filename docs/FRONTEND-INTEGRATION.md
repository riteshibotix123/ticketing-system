# Running the frontend against the live backend

This guide connects `ticketing_frontend` to the real FastAPI backend with the MSW mock switched off. The API contract is Appendix A of `Backend_Build_Guide_v2.md`, mirrored in `Frontend_Change_Request_CR1.md`. If something differs, fix it in the backend, or change both documents together (section 4.2 of the guide). Never change one side only.

## 1. Start the backend

From `backend/`, in Git Bash:

```bash
source .venv/Scripts/activate
cp .env.example .env                    # first time only
docker compose up -d db mailpit         # Postgres on host port 5433, Mailpit UI on 8025
alembic upgrade head
python -m app.cli seed                  # Appendix S demo data; safe to run again
uvicorn app.main:app --reload --port 8000
```

In a second terminal, start the worker. It runs SLA escalations, reminders, auto-close and outgoing email:

```bash
source .venv/Scripts/activate
python -m app.worker
```

To demonstrate timers quickly, set `SLA_TIME_SCALE=0.0166667` in `.env` so one SLA hour lasts one minute. Prod refuses any value other than 1.0.

To start again from an empty database (dev and test only), run `python -m app.cli reset-db` and then `python -m app.cli seed`.

### Seeded accounts

Every seeded account uses the password `Ibotix2026Demo`. Emails follow the pattern `firstname.lastname@ibotix.ai`.

| Use | Account |
|---|---|
| Super Admin | `karan.shah@ibotix.ai`, `mira.kulkarni@ibotix.ai` |
| Admin | `priya.nair@ibotix.ai` |
| Spoke | `rohan.mehta@` (IT and ENG), `isha.gupta@` (IT), `neha.kapoor@` (HR, HR confidential grant), `sanjay.rao@` (FIN), `vikram.singh@` (SEC, Security confidential grant), `aarav.khanna@` (LEG, no grant), `rahul.chopra@` (SAL), `sneha.bhatt@` (OPS) |
| Employee | `asha.verma@` (ENG), `meera.iyer@` (FIN), `dev.patel@` (IT, assignee), `tara.joshi@` (ADM) |
| Status pages | `kabir.sethi@`, `ritu.bansal@`, `farhan.qureshi@` (pending approval), `nitin.saxena@` (rejected), `gaurav.thakur@` (deactivated), `leena.das@` (unverified) |

The department codes are `IT ENG HR ADM FIN SEC SAL OPS LEG`. `ADM` has no active Spoke, so it does not accept tickets. `SAL` has no escalation contact.

The frontend mock data uses different values: the password `IbotixDemo@2026`, the codes `FAC` and `LGL`, and Engineering without a Spoke. When you run against the live backend, use the values above. E2E specs that hard-code the mock values must be updated to match the seed.

## 2. Generate the API types

FastAPI serves the schema at `http://localhost:8000/openapi.json`, at the root and not under `/api/v1`. The `gen:api` script builds its URL as `%VITE_API_BASE_URL%/openapi.json`. That points to `/api/v1/openapi.json`, which does not exist, and the `%VAR%` syntax only expands in Windows `cmd`. Run the generator directly instead:

```bash
cd ticketing_frontend
npx openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts
npm run typecheck
```

Fix every type error in the frontend so that it matches the generated schema. Changing the generator script itself is a frontend change. You can also get a copy of the schema without a running server: `python -m app.cli export-openapi ../ticketing_frontend/openapi.json`.

Points to know when reading the generated types:

- Optional contract fields (`title?`, `theme?`, `action?`, `detail?`, `body?`, `old_value?`, `approved_role?`, `decided_by?`, `ticket_id?`, ...) are left out of the JSON when they have no value. The backend never sends them as `null`. The generated type may still say `string | null`.
- Fields that the contract declares nullable (`owner`, `assignee`, `eta`, `hold`, `feedback`, `escalation_contact`, `object_id`, ...) are always present and may be `null`.
- `POST /auth/login` returns one of `LoginSuccess`, `{mfa_required, mfa_token}` or `{mfa_enrol_required, mfa_token}`. MFA is off unless `MFA_REQUIRED_ROLES` is set, and then `FIELD_ENCRYPTION_KEY` must hold a Fernet key.
- Timestamps are UTC ISO 8601 strings ending in `Z`, sometimes with microseconds.

## 3. Point the frontend at the backend

In `ticketing_frontend/.env`:

```
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_USE_MOCKS=false
```

Then run `npm run dev` (http://localhost:5173) and sign in with a seeded account.

## 4. CORS and cookies

- `CORS_ORIGINS` must list every origin the browser loads the frontend from, exactly as written and comma-separated. It does not accept a wildcard. Example: `CORS_ORIGINS=http://localhost:5173,http://localhost:4173`. Port 4173 is the `vite preview` server that the E2E suite uses.
- The refresh token is the httpOnly cookie `refresh_token` on the path `/api/v1/auth`. The frontend already sends `credentials: "include"`. `/auth/refresh` and `/auth/logout` also check the `Origin` header against `CORS_ORIGINS`.
- Local development over http: `COOKIE_SECURE=false` and `COOKIE_SAMESITE=lax`. `localhost:5173` and `localhost:8000` count as the same site, so the cookie is sent.
- Frontend and API on different sites over https: `COOKIE_SECURE=true` and `COOKIE_SAMESITE=none`. Prod requires `COOKIE_SECURE=true`.
- The client refreshes only after a 401 `unauthenticated`, and never for `/auth/*` except `/auth/me`. A 401 `invalid_credentials` from login is final.

## 5. Run the E2E suite against the live backend

`playwright.config.ts` currently forces `VITE_USE_MOCKS: 'true'` in its `webServer.env`. To run against the backend, that value must come from the environment instead, which is a frontend change, for example `VITE_USE_MOCKS: process.env.VITE_USE_MOCKS ?? 'true'`. After that change:

```bash
# backend: API and worker running, freshly seeded
python -m app.cli reset-db && python -m app.cli seed

# frontend
cd ticketing_frontend
VITE_USE_MOCKS=false VITE_API_BASE_URL=http://localhost:8000/api/v1 npm run test:e2e
```

Run `reset-db` and `seed` again before each full run so that ticket states and counters start from the same point.

## 6. Checking conformance

Run these from `backend/`:

- `python scripts/check_contract.py --full`: the routes the app exposes must equal `contract/routes.txt` exactly, and the file must have no malformed or duplicate lines.
- `pytest tests/api/test_contract_shapes.py`: seeds the database and checks the exact key sets and value types of every Appendix A type, the three dashboards, the error envelope, and the status and `error.code` of every row in Appendix A.1.
- Mailpit (http://localhost:8025) shows every email the worker sends: verification, reset, approvals and ticket notifications.

## 7. Release 2 dashboards and KPIs (R2-A)

- `GET /api/v1/reports/kpis` returns `KpiReport` (Appendix A.3). Query: `from`, `to` (ISO 8601 with an offset; default the last 30 days ending now; at most 366 days), `department_id`, and `priority[]` (or repeated `priority`). Bind the dashboard's date range, department and priority controls to these parameters.
- Admins and Super Admins (`reports.view_org`) get the whole organisation. A Spoke gets their own departments; asking for another department gives 403 `forbidden`. Employees get 403, so hide the page unless `reports.view_org` or `tickets.view_department` is in `Me.permissions`.
- Confidential tickets the caller cannot see are left out of every number. An Admin's totals can therefore be lower than a Super Admin's.
- `filters` in the response echoes the window and scope that were actually applied; show it next to the charts.
- The definition of each KPI (R.12) goes in its tooltip. Percentages are 0 to 100 with one decimal; durations are whole seconds; a `null` percentage or average means there was no data in the window (show "No data", not 0).
- `initial_response_trend` has one entry per IST day in the window, zeros included. `aging` always lists the five buckets in order. `workload` rows with `user: null` are unassigned or unowned tickets.
- `AdminDashboard` now fills `sla_met_pct`, `avg_initial_response_seconds`, `reopen_rate_pct` (last 30 days) and `by_department` (always a list). `SpokeDashboard` gains the same four fields for the caller's departments; `EmployeeDashboard` gains `assigned_warning` and `assigned_breached`. Regenerate the API types (section 2) to pick these up.

## 8. Exports and saved views (R2-B)

- `GET /api/v1/reports/export?type=tickets|kpis&format=csv|xlsx|pdf` returns a file. `type=tickets` takes the same query parameters as `GET /tickets` (pass the current list filters straight through); `type=kpis` takes `from`, `to`, `department_id` and `priority[]` like `/reports/kpis`. Download it with the bearer token as a blob, the same way as attachment downloads, and use the filename from `Content-Disposition` (`ibotix-<type>-<YYYYMMDD-HHMM>.<format>`, IST).
- Access matches the KPI page: `reports.view_org` exports the organisation, a Spoke exports their own departments (another department gives 403), employees get 403. Confidential tickets the caller cannot see are never in a file.
- Every file starts with Report, Generated by, Generated at (IST), Filters and Rows; the export dialog only needs to say so. Cells that look like spreadsheet formulas are prefixed with `'`.
- Limits: CSV and XLSX up to 50,000 tickets, PDF up to 2,000. Over the limit the API returns 422 with `fields.format`; show the message and ask the user to narrow the filters.
- `GET /api/v1/saved-views` returns the built-in views first (`built_in: true`, ids `builtin.<key>`, `created_at`/`updated_at` null), then the caller's own views by name. Apply a view by calling `GET /tickets` with its `query` as the query string. Built-in queries with dates (`Unassigned Today`, `Awaiting Requester > 48h`) are computed when the list is fetched, so refetch rather than caching them for long.
- `POST /saved-views` `{name, query}` (201), `PATCH /saved-views/{id}` `{name?, query?}`, `DELETE /saved-views/{id}` (204). Names are 2 to 80 characters and unique per user ignoring case (409 `conflict`); at most 50 views per user (409). `query` accepts only the `TicketListQuery` keys; a bad value gives 422 with `fields["query.<key>"]`. Built-in views give 403 on change or delete; another user's view gives 404.
- `GET /tickets` has two new filters: `unassigned=true` and `awaiting_before=<ISO timestamp>`.

## 9. Business calendar and business-hours SLA (R2-C1)

- `GET /api/v1/calendar` returns `BusinessCalendar` (Admin and Super Admin; others 403). `timezone` is always `Asia/Kolkata`; show it read-only. Defaults: Monday to Friday (`working_days` `[1,2,3,4,5]`, ISO weekdays), `09:00` to `18:00`, no holidays, `updated_at: null`.
- `PUT /api/v1/calendar` `{working_days, work_start, work_end}` needs `policy.manage` (Super Admin). Times are `HH:MM`, 24-hour; `work_end` must be after `work_start` (422 `fields.work_end`). Days must be distinct integers 1 to 7 (422 `fields.working_days`).
- `POST /api/v1/calendar/holidays` `{date: 'YYYY-MM-DD', name}` (201, returns the whole calendar); a holiday already on that date gives 409 `conflict`. `DELETE /api/v1/calendar/holidays/{date}` (204) removes it; an unknown date gives 404.
- `PolicyConfig.sla_mode` now accepts `business`: enable the Business hours option on the policy screen. `Department.sla_mode` and `Category.sla_mode` (`calendar`, `business` or `null` = inherit) are set with `PATCH /departments/{id}` and `PATCH /categories/{id}`; send `"sla_mode": null` to go back to inheriting. The ticket uses the category value, else the department value, else the policy.
- In business mode every SLA threshold counts only working time (weekends, nights and holidays are skipped); auto-close business days always skip holidays. Calendar, holiday and basis changes apply to timers that start after the change; existing due times do not move, so tell the user that in the confirmation dialog.

## 10. Notification preferences and digests (R2-C2)

- `GET /api/v1/me/notification-preferences` returns `NotificationPreferences` for the signed-in user (defaults `immediate`, `digest_hour` 9, `critical_email` `'always'`). `PUT` takes `{non_critical_email, digest_hour}`; `digest_hour` is an integer 0 to 23 (IST). Sending `critical_email` gives 422 `fields.critical_email`: show it as a locked "Always" row.
- The setting only affects emails. Portal notifications and the bell count never change. Critical notifications (`critical: true`) are always emailed immediately; verification, password reset and signup emails ignore the setting.
- `daily_digest` sends one email per IST day, after the chosen hour, only when something is queued: up to 50 items (oldest first, then "and N more"), each with its portal text and a ticket link. Items about tickets the user can no longer see are left out; confidential tickets show only `Update on <ticket number>`. `off` sends no non-critical email.
