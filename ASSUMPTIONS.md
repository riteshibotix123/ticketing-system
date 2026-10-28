# Assumptions

Anything the spec did not decide, marked `// ASSUMPTION:` in code and listed here (spec section 0.2).

1. **`date-fns-tz` not installed.** The spec asks for date-fns (+ date-fns-tz). Timezone-safe
   formatting of UTC ISO strings into `Asia/Kolkata` is done with the platform
   `Intl.DateTimeFormat` (`src/lib/format.ts`), which is equivalent and removes a dependency.
   `date-fns` itself is used for relative time.
2. **Auth session state uses React context** (not Zustand). Spec 2 allows either; context keeps a
   single state library (`AuthProvider`), with tokens held in memory in `src/api/client.ts`.
3. **Mock credentials.** Every seeded user signs in with `firstname.lastname@ibotix.ai` and the
   password `IbotixDemo@2026`; the MFA code in the mock API is `123456`. Dev-only hints show this
   in the UI (`import.meta.env.DEV`), never in production builds.
4. **Mock email verification / password reset tokens.** The mock API accepts `mock-verify-token`
   and `mock-reset-token` because no mailer exists in development. The dev shortcut links render
   only when `VITE_USE_MOCKS === 'true'`.
5. **Demo clock mechanics.** There is no virtual clock in the browser (the client must keep
   counting down from real `sla.due_at` values). The mock server's demo clock shifts deadline
   timestamps back by the advanced amount, recomputes levels and appends escalation events, so a
   real countdown immediately reads e.g. "Response overdue 6h".
6. **Route guards for configuration screens.** `/config/departments` and `/config/policy` allow any
   config permission (`departments.manage`, `policy.manage` or `admins.manage`) and render
   read-only for viewers without the specific edit permission, per spec 9.13 ("view only
   otherwise"). `/config/admins` requires `admins.manage` (Super Admin) exactly.
7. **MFA step focus** uses a `ref` + `useEffect` instead of the `autoFocus` attribute because
   `jsx-a11y/no-autofocus` is enforced as an error; behaviour is identical.
8. **`GET /departments` during signup** is called without a session (the signup page needs the
   org department list before authentication). If the real backend requires auth there, only the
   signup adapter changes (`src/api/endpoints/departments.ts`), not the screen.
9. **Reports/exports, saved views, business-hours UI, SSO and directory sync** (spec 9.15, phase 5)
   are out of the first release scope; `/reports` renders a "coming in a later release" notice.
10. **Single `tsconfig.json`** (no project references) so `npm run typecheck` stays one command.
11. **Recharts is pinned to v2** — the API used for the department bars is stable and compatible
    with React 18; v3's migration guide is not needed for a single stacked bar chart.
12. **`GET /users` is readable by Spokes.** Spec 9.7 makes a Spoke pick an eligible resolver when
    delegating, but the endpoint table (section 6) does not name a permission for the directory
    read. The mock allows callers with `tickets.assign` (Spokes/Admins) to list users; role changes
    stay behind `users.manage_roles`. The real backend should mirror this read permission or expose
    a narrower "assignable people" endpoint — only `src/api/endpoints/users.ts` and the mock change.
13. **Configuration sub-navigation.** The sidebar links only `/config/departments`, so a shared
    `ConfigTabs` strip (Departments / Policy / Admin accounts, the last gated by `admins.manage`)
    sits on all three screens; without it Policy and Admin accounts were unreachable by navigation.
14. **Demo endpoints are gated on `VITE_USE_MOCKS`, not `DEV`.** The demo clock and persona login
    must exist in the production build that Playwright drives (spec 15/17 escalation scenario);
    they live inside the mock bundle, which is tree-shaken out when mocks are off, so nothing ships
    to the real deployment. The floating dev panel itself remains `DEV`-only.
15. **View tabs are a hand-rolled `tablist`.** Dashboard views, ticket scopes and notification
    filters switch one region instead of owning a tab panel; Radix tabs would emit `aria-controls`
    pointing at a panel that does not exist (axe `aria-valid-attr-value`). Radix Tabs is still used
    where real panels exist (Approvals).
16. **Accessible names match visible text.** The account-menu trigger's name is "<name> — account
    menu" and the decorative initials were dropped from it; select triggers expose their label via
    screen-reader-only text instead of `aria-label`. Both fix axe `label-content-name-mismatch`.
17. **E2E targets the production build with the mock API** (`npm run build` + `preview`, mocks on).
    Vitest excludes `e2e/` (Playwright owns those files) and the production bundle is verified
    separately with `VITE_USE_MOCKS=false`.
