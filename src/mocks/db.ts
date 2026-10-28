/**
 * In-memory database for the mock API (spec section 14).
 *
 * The mock acts as the backend: it owns tickets, deadlines and SLA levels.
 * The browser never computes SLA — it only renders `ticket.sla`.
 *
 * Time model ("demo clock"):
 * - Event timestamps (created_at, acknowledged_at, timeline `at`, …) are stored
 *   in the REAL frame so the UI always shows sensible dates.
 * - Deadlines (resp_due, update_due, ticket.eta) are stored in the display frame
 *   and are shifted BACK by `advanceMockClock` so a real-clock countdown reads
 *   "overdue" immediately. `*_shift` remembers how much has been subtracted so
 *   `resetMockClock` can undo it deterministically.
 */
import type {
  Attachment,
  AuditEntry,
  Department,
  Notification,
  Paged,
  PolicyConfig,
  SignupRequest,
  Ticket,
  TimelineEvent,
  User,
  UserRef,
} from '@/types/domain';

export const HOUR_MS = 3_600_000;

/** Full user row; password is plaintext because this is a mock (never do this for real). */
export interface DbUser extends User {
  password: string;
  theme?: 'system' | 'light' | 'dark';
}

export interface DbTicket {
  /** Canonical ticket (sla is refreshed server-side on every read/mutation). */
  ticket: Ticket;
  events: TimelineEvent[];
  /** Initial-response deadline (ms, display frame). Null once acknowledged. */
  resp_due: number | null;
  resp_shift: number;
  /** Progress-update deadline (ms, display frame). Set at ack/update events. */
  update_due: number | null;
  update_shift: number;
  /** Demo-clock shift applied to ticket.eta so far. */
  eta_shift: number;
  /** Pause point (real ms + clock offset) to extend deadlines when resuming. */
  pause: { at: number; off: number } | null;
  /** Last escalation emission (real ms + clock offset + level) for the 24h repeat rule. */
  last_escalation: { at: number; off: number; level: 0 | 1 | 2 | 3 } | null;
}

/** Notification row with its internal recipient (stripped from API responses). */
export interface DbNotification extends Notification {
  user_id: string;
  /** Monotonic tiebreaker so "newest first" is stable. */
  seq: number;
}

export interface TokenRecord {
  user_id: string;
  kind: 'access' | 'refresh' | 'mfa';
}

export interface MockDb {
  users: DbUser[];
  departments: Department[];
  tickets: DbTicket[];
  notifications: DbNotification[];
  /** Same shape as AuditEntry plus a monotonic seq for stable newest-first order. */
  audit: (AuditEntry & { seq: number })[];
  signupRequests: SignupRequest[];
  policy: PolicyConfig;
  tokens: Record<string, TokenRecord>;
  /** Fallback identity for POST /auth/refresh when the client sends no body. */
  lastRefreshToken: string | null;
  loginAttempts: Record<string, { count: number; window_start: number }>;
  attachments: Record<string, Attachment>;
  /** Verification token -> user id. */
  verifyTokens: Record<string, string>;
  /** Password-reset token -> user id. */
  resetTokens: Record<string, string>;
  /** Most recent signup (lets the dev token 'mock-verify-token' resolve a user). */
  lastSignupUserId: string | null;
  /** Most recent forgot-password user (same trick for 'mock-reset-token'). */
  lastForgotUserId: string | null;
  /** Ticket id sequence, format IBX-XXX-2026-NNNNNN (continued by new tickets). */
  ticketSeq: number;
  /** Demo-clock offset in ms, starts at 0. */
  clockOffsetMs: number;
}

function emptyDb(): MockDb {
  return {
    users: [],
    departments: [],
    tickets: [],
    notifications: [],
    audit: [],
    signupRequests: [],
    policy: freshPolicy(),
    tokens: {},
    lastRefreshToken: null,
    loginAttempts: {},
    attachments: {},
    verifyTokens: {},
    resetTokens: {},
    lastSignupUserId: null,
    lastForgotUserId: null,
    ticketSeq: 0,
    clockOffsetMs: 0,
  };
}

/** Spec 11.2 defaults (the single source for the initial policy). */
export function freshPolicy(): PolicyConfig {
  return {
    initial_response_hours: 24,
    warning_hours: { low: 18, medium: 18, high: 18, critical: 12 },
    l3_hours: { low: 48, medium: 48, high: 36, critical: 30 },
    update_cadence_hours: 24,
    sla_mode: 'calendar',
    admins_can_manage_departments: true,
    requester_reminder_hours: 48,
    auto_close_business_days: 3,
  };
}

/** Singleton store. Cleared/reseeded in place so module references stay valid. */
export const db: MockDb = emptyDb();

export function clearDatabase(): void {
  db.users.length = 0;
  db.departments.length = 0;
  db.tickets.length = 0;
  db.notifications.length = 0;
  db.audit.length = 0;
  db.signupRequests.length = 0;
  db.policy = freshPolicy();
  db.tokens = {};
  db.lastRefreshToken = null;
  db.loginAttempts = {};
  db.attachments = {};
  db.verifyTokens = {};
  db.resetTokens = {};
  db.lastSignupUserId = null;
  db.lastForgotUserId = null;
  db.ticketSeq = 0;
  db.clockOffsetMs = 0;
}

/* ------------------------------------------------------------------ lookups */

let uidCounter = 0;
export function uid(prefix: string): string {
  uidCounter += 1;
  return `${prefix}_${uidCounter.toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

export function findUser(id: string): DbUser | null {
  return db.users.find((u) => u.id === id) ?? null;
}

export function findUserByEmail(email: string): DbUser | null {
  const needle = email.trim().toLowerCase();
  return db.users.find((u) => u.email.toLowerCase() === needle) ?? null;
}

export function ref(user: DbUser): UserRef {
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    ...(user.title ? { title: user.title } : {}),
  };
}

export function findTicket(id: string): DbTicket | null {
  return db.tickets.find((r) => r.ticket.id === id) ?? null;
}

export function findDepartment(id: string): Department | null {
  return db.departments.find((d) => d.id === id) ?? null;
}

/** Users who are Spokes of a department (active accounts only). */
export function spokesOf(departmentId: string): DbUser[] {
  return db.users.filter((u) => u.state === 'active' && u.spoke_departments.includes(departmentId));
}

export function usersWithRole(role: string): DbUser[] {
  return db.users.filter(
    (u) => u.state === 'active' && u.roles.includes(role as User['roles'][number]),
  );
}

/**
 * Ticket id: `IBX-XXX-2026-NNNNNN` where XXX is the department id uppercased and
 * padded right with 'X' to 3 chars ('IT' -> 'ITX', 'HR' -> 'HRX', 'FIN' -> 'FIN').
 * The 6-digit suffix increments globally across departments.
 */
export function nextTicketId(departmentId: string): string {
  db.ticketSeq += 1;
  const code = (departmentId.toUpperCase() + 'XXX').slice(0, 3);
  return `IBX-${code}-2026-${String(db.ticketSeq).padStart(6, '0')}`;
}

/** Server-side pagination shared by every list endpoint. */
export function paginate<T>(
  items: T[],
  page: unknown,
  pageSize: unknown,
  defaultSize = 25,
): Paged<T> {
  const size = clampInt(pageSize, 1, 100, defaultSize);
  const current = clampInt(page, 1, 100_000, 1);
  const start = (current - 1) * size;
  return {
    items: items.slice(start, start + size),
    total: items.length,
    page: current,
    page_size: size,
  };
}

function clampInt(value: unknown, min: number, max: number, fallback: number): number {
  const n =
    typeof value === 'string'
      ? Number.parseInt(value, 10)
      : typeof value === 'number'
        ? value
        : NaN;
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(n)));
}

/** Keep each department's `spokes` array in step with user.spoke_departments. */
export function syncSpokes(): void {
  for (const dept of db.departments) {
    dept.spokes = db.users
      .filter((u) => u.state === 'active' && u.spoke_departments.includes(dept.id))
      .map((u) => ref(u));
  }
}
