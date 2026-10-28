/**
 * Auth endpoints (spec 6.1) plus the dev-only persona switcher and demo clock
 * routes used by `ui/DevPanel.tsx`.
 */
import { http } from 'msw';
import { type DbUser } from '../db';
import { bearer, fail, ok, readJson, respond, str, throw401, throw403, throw422 } from '../helpers';
import { meFor } from '../access';
import {
  createSignup,
  login,
  logout,
  personaLogin,
  refreshAccess,
  requestPasswordReset,
  resetPassword,
  resolveToken,
  verifyEmail,
  verifyMfa,
  VERIFY_TOKEN,
} from '../auth';
import { advanceMockClock, resetMockClock } from '../scheduler';
import { USE_MOCKS } from '@/lib/constants';
import { p } from './paths';

function requireUser(request: Request): DbUser {
  const user = resolveToken(bearer(request));
  if (!user) throw401();
  return user;
}

/** Login / MFA / signup responses issue refresh tokens for POST /auth/refresh. */
function tokenResponse(request: Request, access: string, refresh?: string, status = 200) {
  return ok(
    refresh
      ? { access_token: access, refresh_token: refresh, token_type: 'bearer' }
      : { access_token: access },
    request,
    status,
  );
}

export const authHandlers = [
  /* ------------------------------------------------------------- session */
  http.get(p('/auth/me'), ({ request }) =>
    respond(request, () => {
      const user = requireUser(request);
      return ok(meFor(user), request);
    }),
  ),

  http.patch(p('/auth/me'), ({ request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      const body = await readJson<{ theme?: string }>(request);
      if (body.theme === 'system' || body.theme === 'light' || body.theme === 'dark')
        user.theme = body.theme;
      return ok({ status: 'saved' }, request);
    }),
  ),

  http.post(p('/auth/login'), ({ request }) =>
    respond(request, async () => {
      const body = await readJson<{ email?: string; password?: string }>(request);
      const email = str(body.email);
      const password = str(body.password);
      if (!email || !password)
        throw422({
          ...(email ? {} : { email: 'Required.' }),
          ...(password ? {} : { password: 'Required.' }),
        });
      const outcome = login(email, password);
      if (outcome.kind === 'invalid_credentials') {
        return fail(
          401,
          'invalid_credentials',
          'Email or password is incorrect.',
          undefined,
          request,
        );
      }
      if (outcome.kind === 'rate_limited') {
        return fail(
          429,
          'too_many_attempts',
          `Too many attempts, try again in ${outcome.minutes} minutes.`,
          undefined,
          request,
        );
      }
      if (outcome.kind === 'mfa')
        return ok({ mfa_required: true, mfa_token: outcome.mfa_token }, request);
      return tokenResponse(request, outcome.access_token, outcome.refresh_token);
    }),
  ),

  http.post(p('/auth/mfa/verify'), ({ request }) =>
    respond(request, async () => {
      const body = await readJson<{ mfa_token?: string; code?: string }>(request);
      const mfaToken = str(body.mfa_token);
      const code = str(body.code);
      if (!mfaToken || !code)
        throw422({
          ...(mfaToken ? {} : { mfa_token: 'Required.' }),
          ...(code ? {} : { code: 'Required.' }),
        });
      const outcome = verifyMfa(mfaToken, code);
      if (outcome.kind === 'invalid_token')
        return fail(
          401,
          'invalid_mfa_token',
          'Your verification step expired. Sign in again.',
          undefined,
          request,
        );
      if (outcome.kind === 'invalid_code') {
        return fail(
          422,
          'invalid_code',
          'The verification code is incorrect or expired.',
          { code: 'Enter the 6-digit code from your authenticator.' },
          request,
        );
      }
      return tokenResponse(request, outcome.access_token, outcome.refresh_token);
    }),
  ),

  http.post(p('/auth/refresh'), ({ request }) =>
    respond(request, async () => {
      // client.ts sends no body (credentials-only refresh): fall back to the
      // last issued refresh token kept in the mock registry.
      const body = await readJson<{ refresh_token?: string }>(request);
      const header = bearer(request);
      const access = refreshAccess(str(body.refresh_token) || header);
      if (!access)
        return fail(
          401,
          'session_expired',
          'Session expired. Please sign in again.',
          undefined,
          request,
        );
      return ok({ access_token: access, token_type: 'bearer' }, request);
    }),
  ),

  http.post(p('/auth/logout'), ({ request }) =>
    respond(request, () => {
      logout(bearer(request));
      return ok({ status: 'logged_out' }, request);
    }),
  ),

  /* -------------------------------------------------------------- signup */
  http.post(p('/auth/signup'), ({ request }) =>
    respond(request, async () => {
      const body = await readJson<{
        name?: string;
        email?: string;
        password?: string;
        requested_role?: string;
        requested_department?: string;
      }>(request);
      const outcome = createSignup({
        name: str(body.name),
        email: str(body.email),
        password: str(body.password),
        requested_role: str(body.requested_role),
        requested_department: str(body.requested_department),
      });
      if (outcome.kind === 'invalid') throw422(outcome.fields);
      return ok({ status: 'verification_sent', dev_token: VERIFY_TOKEN }, request, 201);
    }),
  ),

  http.post(p('/auth/verify-email'), ({ request }) =>
    respond(request, async () => {
      const body = await readJson<{ token?: string }>(request);
      const token = str(body.token);
      if (!token) throw422({ token: 'Required.' });
      if (!verifyEmail(token)) {
        return fail(
          422,
          'invalid_token',
          'This verification link is invalid or has expired.',
          { token: 'Request a new email.' },
          request,
        );
      }
      return ok({ status: 'verified' }, request);
    }),
  ),

  http.post(p('/auth/resend-verification'), ({ request }) =>
    respond(request, async () => {
      await readJson(request);
      // Always "sent" — never reveal whether the address exists.
      return ok({ status: 'sent' }, request);
    }),
  ),

  http.post(p('/auth/forgot-password'), ({ request }) =>
    respond(request, async () => {
      const body = await readJson<{ email?: string }>(request);
      if (str(body.email)) requestPasswordReset(str(body.email));
      return ok({ status: 'sent' }, request);
    }),
  ),

  http.post(p('/auth/reset-password'), ({ request }) =>
    respond(request, async () => {
      const body = await readJson<{ token?: string; password?: string }>(request);
      const token = str(body.token);
      const password = str(body.password);
      if (!token) throw422({ token: 'Required.' });
      if (password.length < 12) throw422({ password: 'Use at least 12 characters.' });
      if (!resetPassword(token, password)) {
        return fail(
          422,
          'invalid_token',
          'This reset link is invalid or has expired.',
          { token: 'Request a new email.' },
          request,
        );
      }
      return ok({ status: 'reset' }, request);
    }),
  ),

  /* ------------------------------------------------------- demo-only routes
   * Available whenever the mock API is served (VITE_USE_MOCKS=true) so the
   * Playwright suite can drive the demo clock against the production build.
   * With mocks off the whole src/mocks bundle is absent — these never ship. */
  http.post(p('/auth/dev/persona'), ({ request }) =>
    respond(request, async () => {
      if (!USE_MOCKS) throw403('Dev personas are disabled.');
      const body = await readJson<{ email?: string }>(request);
      const email = str(body.email);
      if (!email) throw422({ email: 'Required.' });
      const session = personaLogin(email);
      if (!session)
        return fail(404, 'not_found', 'No seeded persona with that email.', undefined, request);
      return ok(session, request);
    }),
  ),

  http.post(p('/dev/clock'), ({ request }) =>
    respond(request, async () => {
      if (!USE_MOCKS) throw403('The demo clock is disabled.');
      const body = await readJson<{ hours?: number; reset?: boolean }>(request);
      const offset =
        body.reset === true ? resetMockClock() : advanceMockClock(Number(body.hours ?? 0));
      return ok({ clock_offset_ms: offset }, request);
    }),
  ),
];
