# Security and performance notes

This document describes the controls the backend enforces, the tests that prove each one, and the limits that operators need to know about. Business rules come from Appendix R of `Backend_Build_Guide_v2.md`.

## Authentication

| Control | Behaviour | Proof |
|---|---|---|
| Passwords | Argon2id (`argon2-cffi`). Passwords must be 12 to 128 characters with a lowercase letter, an uppercase letter and a digit. Unknown emails still run a dummy hash, so response timing does not reveal accounts. | `tests/security/test_auth_hardening.py::test_password_policy` |
| Access token | HS256 JWT, 15 minutes, with the claims `sub`, `iat`, `exp` and `jti`. The user is reloaded on every request, so roles never come from the token, and a deactivated account stops working at once. | `test_tampered_tokens_are_rejected`, `test_role_is_never_taken_from_the_token`, `test_deactivated_user_token_stops_working` |
| Refresh token | Opaque and stored only as a SHA-256 hash. It travels in the httpOnly cookie `refresh_token` on the path `/api/v1/auth` and rotates on every refresh. Reusing a rotated token revokes the whole family and is audited (`refresh_reuse_detected`). | `test_refresh_token_reuse_revokes_the_family` |
| Origin check | `/auth/refresh` and `/auth/logout` refuse any `Origin` that is not in `CORS_ORIGINS` (403). | `test_refresh_rejects_foreign_origin` |
| Lockout | 5 consecutive wrong passwords lock the account for 15 minutes (429 `too_many_attempts`). Reapply shares the same counter. MFA verification has its own counter with the same limits. | `test_login_lockout_after_five_failures`, `test_reapply_wrong_password_is_403_and_locks`, `tests/api/test_mfa.py` |
| MFA | TOTP (±1 step), secrets encrypted with Fernet (`FIELD_ENCRYPTION_KEY`), 8 single-use recovery codes stored hashed. MFA tokens are 5-minute JWTs with `aud`/`purpose` `mfa` and are never accepted as access tokens. Off unless `MFA_REQUIRED_ROLES` is set. | `tests/api/test_mfa.py`, `tests/unit/test_mfa_service.py` |
| No enumeration | Login gives the same 401 for an unknown email and for a wrong password. Signup, forgot-password and resend-verification always return the same 202. Reapply gives the same 403 for an unknown email and for a wrong password. | `test_no_account_enumeration` |
| Public endpoints | `/public/config`, signup, verify-email, resend, reapply, forgot and reset never return 401, even with a bad bearer token. | `test_public_endpoints_never_return_401` |

### Rate limits (stored in PostgreSQL, so they hold across processes)

| Rule | Limit |
|---|---|
| Login per email / per IP | 10 per minute each |
| Signup per email / per IP | 5 per hour each |
| Resend verification per email | 3 per hour |
| Forgot password per email | 3 per hour |
| Reapply | no separate limit; covered by the per-account lockout above |

Per-IP rules use the client address that Uvicorn reports. Behind a reverse proxy, start Uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy address>`. Without those flags every client shares the proxy's address and the per-IP limits apply to everyone at once.

## Authorization

- Every permission and visibility decision lives in `app/policy/`. Routers only parse input and call one service.
- `tests/security/test_authorization_matrix.py` takes every route in `contract/routes.txt` and checks it against six actor classes: anonymous, employee, Spoke, Admin, Super Admin, and Admin with `admins_can_manage_departments` off. Each pair is expected to give 401, 403, 404 or an allowed outcome. A route that is in the contract or exposed by the app but has no matrix entry fails the test.
- A ticket the caller may not see returns the same 404 body as a ticket that does not exist. This holds for reads, writes and attachment downloads.
- R.2 rule 6: a department's escalation contact can read that department's non-confidential tickets, so L2 and critical-creation alerts reach them. The rule gives read access only, never actions, and never confidential tickets.

## Confidential tickets

`tests/security/test_confidentiality_leaks.py` creates a confidential HR ticket with a comment, an internal note and an attachment. It then signs in as each of five users who have no access: the Legal Spoke, the Admin, an IT Spoke, an employee, and the HR escalation contact. For each of them it checks:

- Lists in every scope, text search on number and title, notifications and their count, audit search and filters, the three dashboards, departments, members and user lookup: no response body or header contains the ticket number, title, comment text, attachment name or attachment id.
- The ticket detail, the timeline, write actions and the attachment download all return 404 bodies identical to those for a missing ticket.
- Admin dashboard counts and list totals go up by exactly one when the ticket stops being confidential. This proves the counts exclude it beforehand.
- None of the outsiders has a notification or an email about the ticket. Email to the requester never carries the title or comment text (it uses the `confidential_ticket_update` template).
- Positive control: the granted Spoke, the Super Admin and the requester can see the ticket.

## HTTP hardening (`app/core/security_headers.py`)

- Every response carries `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and `X-Frame-Options: DENY`.
- Every `/api/v1/auth/*` response and every attachment download also carries `Cache-Control: no-store`.
- Request body limit: `MAX_UPLOAD_BYTES` plus 64 KiB for multipart overhead. Requests whose declared `Content-Length` is larger are rejected with 413 `file_too_large` before any parsing. Chunked bodies are counted as they arrive and stopped at the same limit, so an oversized upload never fills the temporary directory. The 413 response still carries the CORS and security headers.
- CORS: exact origins from `CORS_ORIGINS`. The settings refuse a wildcard, credentials are allowed only for listed origins, and the allowed methods and headers are fixed lists.

## Uploads

- Size, count and type limits come from settings and are published in `PublicConfig.attachment_limits`.
- The first bytes of each file are checked against the declared type, and a mismatch gives 415 `unsupported_file_type`. File names are sanitised. Files are stored under random keys (`attachments/<hex>`) and never under the user's file name.
- Downloads require visibility of the linked ticket. Unlinked uploads can only be downloaded by their uploader. Infected or pending files are never served. Each download of a confidential ticket's attachment is audited.
- The scanner is pluggable (`app/integrations/scanner`). Release 1 ships `NoopScanner`, which marks files clean. Plug in a real scanner before handling untrusted files at scale.

## Data protection

- All SQL goes through the ORM or bound parameters. The few raw statements (advisory locks, seed SQL) use bound values only.
- `audit_log` and `ticket_events` are immutable through database triggers. B25 adds a non-owner application role with no `UPDATE` or `DELETE` on these tables.
- Logs never contain passwords, tokens, hashes, MFA secrets or email addresses.

## Performance

- `python -m scripts.perf_seed` inserts 50,000 tickets and 200,000 events across the nine departments, generated on the server with `generate_series`. It refuses to run when `ENV=prod`.
- `tests/perf/test_list_performance.py` builds the same data inside a rolled-back transaction. It requires `GET /tickets` to answer within a 300 ms p95, measured over 20 runs, for these cases: the default order for an employee, a Spoke queue and an Admin; department plus status filters; and text search. For every case except the Admin's unfiltered "all tickets" view, it also requires that the plan of every SQL statement the request runs avoids a sequential scan on `tickets`. That one view reads about 95% of the table, where a sequential scan with a top-N sort is the right plan.
- Fixes found with `EXPLAIN`:
  - The planner's cost estimate for the visibility clause, an OR with hashed subplans, exceeds `jit_above_cost`. JIT compilation then added 400 to 600 ms to every list request. The app's connections now set `jit=off` (`app/core/db.py`), which suits a workload of short OLTP queries.
  - The `mine` scope is now `id IN (own UNION collaborating)`. The old form was an OR with an EXISTS subquery, which forced a sequential scan. The new form uses the `requester_id` and `ticket_collaborators.user_id` indexes.
- No new index was needed. The existing department and status B-tree index and the trigram GIN indexes on `title` and `ticket_no` (B04) serve the filtered and search cases.
