# Ibotix Tickets — internal ticketing portal (frontend)

React 18 + TypeScript (strict) + Vite 5 frontend for the Ibotix internal helpdesk, built to
`IBOTIX_FRONTEND_SPEC.md`. It runs against a **mock API (MSW)** out of the box and switches to the
real FastAPI backend with one environment variable — no screen code changes.

## Quick start

```bash
npm install
npm run dev          # http://localhost:5173, mocks on by default
```

Demo sign-ins (mock API):

| Who                      | Email                   | Notes             |
| ------------------------ | ----------------------- | ----------------- |
| Super Admin              | `karan.shah@ibotix.ai`  | MFA code `123456` |
| Admin                    | `priya.nair@ibotix.ai`  | MFA code `123456` |
| Spoke (IT)               | `rohan.mehta@ibotix.ai` | MFA code `123456` |
| Spoke (HR, confidential) | `neha.kapoor@ibotix.ai` | MFA code `123456` |
| Resolver (IT)            | `dev.patel@ibotix.ai`   | MFA code `123456` |
| Employee (Engineering)   | `asha.verma@ibotix.ai`  | no MFA            |
| Employee (Finance)       | `meera.iyer@ibotix.ai`  | no MFA            |

Password for everyone: **`IbotixDemo@2026`** (12+ characters). Company domain: `ibotix.ai`.

The floating **dev panel** (bottom-left, development builds only) switches persona instantly and
moves the **demo clock** forward by 6h / 12h / 24h to see L1 → L2 → L3 escalation states.

## Scripts

| Script              | What it does                                                     |
| ------------------- | ---------------------------------------------------------------- |
| `npm run dev`       | Vite dev server (MSW on unless `VITE_USE_MOCKS=false`)           |
| `npm run build`     | Production build                                                 |
| `npm run preview`   | Serve `dist/` locally                                            |
| `npm run lint`      | ESLint, zero warnings allowed                                    |
| `npm run typecheck` | `tsc --noEmit`                                                   |
| `npm test`          | Vitest + Testing Library                                         |
| `npm run test:e2e`  | Playwright against the built app with mocks                      |
| `npm run gen:api`   | Regenerate `src/api/schema.d.ts` from the FastAPI OpenAPI schema |

## Environment (`.env`, prefix `VITE_`)

```
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_USE_MOCKS=true            # default: on in dev, off in builds; true once more to ship mocks
VITE_APP_NAME=Ibotix Tickets
VITE_DISPLAY_TZ=Asia/Kolkata
VITE_SENTRY_DSN=               # optional
```

Every value is optional: with no `.env` at all the dev server still runs on the mock API (a
production build talks to `VITE_API_BASE_URL`). Copy `.env.example` and set `VITE_USE_MOCKS=false`
to point the UI at the FastAPI backend.

## Switching to the real backend

1. `VITE_USE_MOCKS=false`
2. `npm run gen:api` against the FastAPI OpenAPI schema; fix any type errors surfaced in
   `src/api/schema.d.ts`.
3. Re-run `npm run test:e2e`.

Only `src/api/endpoints/*` adapters should need attention — screens keep their code.

## Structure

```
src/
  main.tsx            boots MSW (when enabled) then React
  app/                providers, router (lazy routes + guards)
  api/                fetch wrapper (in-memory tokens, refresh-retry), endpoints, query keys
  mocks/              MSW browser/node servers, in-memory db, seed, demo clock, dev panel
  features/           auth, approvals, dashboard, tickets, departments, users, audit, notifications
  components/ui/      shadcn-style primitives
  components/common/  badges, SLA indicator, DataTable, FilterBar, states, form field…
  components/layout/  AppShell, Sidebar, Topbar, PageHeader
  hooks/              useAuth, usePermissions, useCountdown, useDebounce, useUrlFilters, useToast, useTheme
  lib/                permissions, SLA display, formatting, Zod schemas, constants
  types/domain.ts     domain types
```

## Rules encoded in the UI (and enforced by the server)

- The browser **never computes SLA levels** — it renders `ticket.sla` and counts down to `due_at`.
- Access is gated by **permission flags** from `/auth/me`, never by role names alone; ticket
  buttons come from `allowed_actions`.
- Internal notes, escalation events and priority changes are **never shown to requesters**.
- Reasons are required for: ETA changes, transfers, priority changes, holds, reopen, cancel.
- Tokens live **in memory only**; no `localStorage`/`sessionStorage` tokens, no `window.confirm`.
- Every colour comes from the CSS tokens in `src/styles/tokens.css`; state is always text + icon.

## Quality gates

`npm run lint`, `npm run typecheck`, `npm test` must pass (CI runs all three plus a build and
Playwright). Deployment: multi-stage `Dockerfile` (node build → nginx with SPA fallback and
security headers). See `.github/workflows/ci.yml`.

## Testing

| Layer            | Command            | Covers                                                                                                                                                                                                                                            |
| ---------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unit / component | `npm test`         | 85 Vitest + Testing Library tests across 10 files (components, hooks, formatters, provider regression).                                                                                                                                           |
| Integration      | `npm test`         | MSW-backed suites: login + refresh, signup → approval per role, full ticket control loop, reopen, transfer, hold, internal-note and confidential visibility, admin-approval rules, notification read flow.                                        |
| E2E              | `npm run test:e2e` | Playwright against `npm run build` + `preview` with mocks: BRD §20 control loop, demo-clock escalation, keyboard-only create + acknowledge, axe (WCAG 2.1 A/AA) on every page in light and dark, and 400px phone width with no horizontal scroll. |

E2E needs the browser once per machine: `npx playwright install chromium`. The suite runs two
projects — `desktop` (Chrome) and `phone` (Pixel 7 at 400×850); desktop-only flows skip themselves
on the phone project and the responsive checks skip on desktop.
