/**
 * Mock authentication: token issue/resolve, password check, MFA, signup and
 * verification. Tokens live only in the in-memory registry (spec 7/18 — never
 * localStorage/sessionStorage). Access tokens look like `mock-<userId>-<rand>`,
 * MFA tokens like `mfa-<userId>` (requirement 11).
 */
import { db, findUser, findUserByEmail, uid, type DbUser } from './db';
import { meFor } from './access';
import type { AccountState, Role } from '@/types/domain';

export const DEMO_PASSWORD = 'IbotixDemo@2026';
export const MFA_DEMO_CODE = '123456';
export const VERIFY_TOKEN = 'mock-verify-token';
export const RESET_TOKEN = 'mock-reset-token';
const ALLOWED_DOMAINS = ['ibotix.ai'];
const MAX_ATTEMPTS = 6;
const ATTEMPT_WINDOW_MS = 15 * 60_000;

/* ------------------------------------------------------------------ tokens */

export function issueToken(userId: string, kind: 'access' | 'refresh'): string {
  const prefix = kind === 'access' ? 'mock' : 'refresh';
  const token = `${prefix}-${userId}-${Math.random().toString(36).slice(2, 10)}`;
  db.tokens[token] = { user_id: userId, kind };
  if (kind === 'refresh') db.lastRefreshToken = token;
  return token;
}

/** Resolve an Authorization bearer to an active user (mfa tokens don't count). */
export function resolveToken(raw: string | null): DbUser | null {
  if (!raw) return null;
  const record = db.tokens[raw];
  if (!record || record.kind === 'mfa') return null;
  const user = findUser(record.user_id);
  if (!user || user.state === 'deactivated') return null;
  return user;
}

export function invalidateUserTokens(userId: string): void {
  for (const [token, record] of Object.entries(db.tokens)) {
    if (record.user_id === userId) delete db.tokens[token];
  }
  if (db.lastRefreshToken && !db.tokens[db.lastRefreshToken]) db.lastRefreshToken = null;
}

export function logout(token: string | null): void {
  if (!token) return;
  const record = db.tokens[token];
  if (record) invalidateUserTokens(record.user_id);
}

/** Re-issue an access token from a refresh token (body, header or fallback). */
export function refreshAccess(fromBody: string | null): string | null {
  const candidates = [fromBody, db.lastRefreshToken];
  for (const candidate of candidates) {
    if (!candidate) continue;
    const record = db.tokens[candidate];
    if (record?.kind === 'refresh') return issueToken(record.user_id, 'access');
  }
  return null;
}

/* ------------------------------------------------------------------- login */

export type LoginOutcome =
  | { kind: 'ok'; access_token: string; refresh_token: string }
  | { kind: 'mfa'; mfa_token: string }
  | { kind: 'invalid_credentials' }
  | { kind: 'rate_limited'; minutes: number };

export function login(email: string, password: string): LoginOutcome {
  const user = findUserByEmail(email);
  if (!user || user.password !== password) return recordFailedAttempt(email);
  delete db.loginAttempts[email.trim().toLowerCase()];
  // MFA is mandatory for Super Admin, Admin and Spoke (spec 7).
  if (user.roles.some((r) => r === 'super_admin' || r === 'admin' || r === 'spoke')) {
    const mfaToken = `mfa-${user.id}`;
    db.tokens[mfaToken] = { user_id: user.id, kind: 'mfa' };
    return { kind: 'mfa', mfa_token: mfaToken };
  }
  user.last_login_at = new Date().toISOString();
  return {
    kind: 'ok',
    access_token: issueToken(user.id, 'access'),
    refresh_token: issueToken(user.id, 'refresh'),
  };
}

function recordFailedAttempt(email: string): LoginOutcome {
  const key = email.trim().toLowerCase();
  const now = Date.now();
  const attempt = db.loginAttempts[key] ?? { count: 0, window_start: now };
  if (now - attempt.window_start > ATTEMPT_WINDOW_MS) {
    attempt.count = 0;
    attempt.window_start = now;
  }
  attempt.count += 1;
  db.loginAttempts[key] = attempt;
  if (attempt.count >= MAX_ATTEMPTS) {
    const remaining = Math.max(
      1,
      Math.ceil((attempt.window_start + ATTEMPT_WINDOW_MS - now) / 60_000),
    );
    return { kind: 'rate_limited', minutes: remaining };
  }
  return { kind: 'invalid_credentials' };
}

export type MfaOutcome =
  | { kind: 'ok'; access_token: string; refresh_token: string }
  | { kind: 'invalid_token' }
  | { kind: 'invalid_code' };

export function verifyMfa(mfaToken: string, code: string): MfaOutcome {
  const record = db.tokens[mfaToken];
  if (!record || record.kind !== 'mfa') return { kind: 'invalid_token' };
  if (code.trim() !== MFA_DEMO_CODE) return { kind: 'invalid_code' };
  delete db.tokens[mfaToken];
  const user = findUser(record.user_id);
  if (!user) return { kind: 'invalid_token' };
  user.last_login_at = new Date().toISOString();
  return {
    kind: 'ok',
    access_token: issueToken(user.id, 'access'),
    refresh_token: issueToken(user.id, 'refresh'),
  };
}

/* ----------------------------------------------------------------- signup */

export function allowedEmailDomain(email: string): boolean {
  const at = email.lastIndexOf('@');
  if (at <= 0) return false;
  const domain = email.slice(at + 1).toLowerCase();
  return ALLOWED_DOMAINS.some((d) => domain === d || domain.endsWith(`.${d}`));
}

export type SignupOutcome =
  | { kind: 'created'; user: DbUser; request_id: string }
  | { kind: 'invalid'; fields: Record<string, string> };

export function createSignup(input: {
  name: string;
  email: string;
  password: string;
  requested_role: string;
  requested_department: string;
}): SignupOutcome {
  const fields: Record<string, string> = {};
  const name = input.name.trim();
  const email = input.email.trim();
  if (name.length < 2) fields.name = 'Enter your full name.';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) fields.email = 'Enter a valid email address.';
  else if (!allowedEmailDomain(email))
    fields.email = 'Use your company email address (@ibotix.ai).';
  if (input.password.length < 12) fields.password = 'Use at least 12 characters.';
  const role = input.requested_role;
  if (role !== 'employee' && role !== 'admin' && role !== 'super_admin')
    fields.requested_role = 'Choose a role.';
  if (!db.departments.some((d) => d.id === input.requested_department)) {
    fields.requested_department = 'Pick a department.';
  }
  if (findUserByEmail(email)) fields.email = 'An account with this email already exists.';
  if (Object.keys(fields).length > 0) return { kind: 'invalid', fields };

  const user: DbUser = {
    id: uid('u'),
    name,
    email,
    title: undefined,
    roles: [],
    department_id: input.requested_department,
    state: 'pending_verification',
    spoke_departments: [],
    mfa_enabled: false,
    created_at: new Date().toISOString(),
    last_login_at: null,
    password: input.password,
  };
  db.users.push(user);
  const requestId = uid('sr');
  db.signupRequests.push({
    id: requestId,
    name,
    email,
    email_verified: false,
    requested_role: role as 'employee' | 'admin' | 'super_admin',
    requested_department: input.requested_department,
    status: 'pending',
    can_approve: false,
    created_at: new Date().toISOString(),
  });
  db.verifyTokens[`verify-${user.id}-${Math.random().toString(36).slice(2, 8)}`] = user.id;
  db.lastSignupUserId = user.id;
  return { kind: 'created', user, request_id: requestId };
}

/** Accept a stored token or the shared dev token from the signup response. */
export function verifyEmail(token: string): DbUser | null {
  const userId =
    db.verifyTokens[token] ?? (token === VERIFY_TOKEN ? db.lastSignupUserId : null) ?? null;
  const user = userId ? findUser(userId) : null;
  if (!user) return null;
  delete db.verifyTokens[token];
  user.state = 'pending_approval';
  const request = db.signupRequests.find(
    (r) => r.email.toLowerCase() === user.email.toLowerCase() && r.status === 'pending',
  );
  if (request) request.email_verified = true;
  return user;
}

/** Forgot/reset: remember who asked so the dev token can resolve a user. */
export function requestPasswordReset(email: string): void {
  const user = findUserByEmail(email);
  if (!user) return;
  db.resetTokens[`rst-${user.id}-${Math.random().toString(36).slice(2, 8)}`] = user.id;
  db.lastForgotUserId = user.id;
}

export function resetPassword(token: string, password: string): DbUser | null {
  const userId = db.resetTokens[token] ?? (token === RESET_TOKEN ? db.lastForgotUserId : null);
  const user = userId ? findUser(userId) : null;
  if (!user || password.length < 12) return null;
  delete db.resetTokens[token];
  user.password = password;
  return user;
}

/* ------------------------------------------------------------- dev persona */

export interface Persona {
  id: string;
  name: string;
  email: string;
  title?: string;
  roles: Role[];
  state: AccountState;
}

export function personas(): Persona[] {
  return db.users.map((u) => ({
    id: u.id,
    name: u.name,
    email: u.email,
    ...(u.title ? { title: u.title } : {}),
    roles: u.roles,
    state: u.state,
  }));
}

/** Dev-only instant login: fresh tokens, no password, no MFA. */
export function personaLogin(
  email: string,
): { access_token: string; me: ReturnType<typeof meFor> } | null {
  const user = findUserByEmail(email);
  if (!user) return null;
  user.last_login_at = new Date().toISOString();
  return { access_token: issueToken(user.id, 'access'), me: meFor(user) };
}
