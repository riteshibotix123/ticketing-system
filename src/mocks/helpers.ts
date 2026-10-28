/**
 * Shared plumbing for the mock handlers: response envelopes (spec 6 error
 * shape), CORS headers for the cross-origin dev API, request parsing, and the
 * audit / notification / timeline emitters used after every mutation.
 */
import { HttpResponse } from 'msw';
import type { AuditEntry, Notification, TimelineEvent, UserRef } from '@/types/domain';
import { db, findUser, ref, uid, type DbNotification, type DbTicket, type DbUser } from './db';

/* ------------------------------------------------------------------ errors */

/** Throw-from-handler error mapped to the documented error envelope. */
export class ApiFailure extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields?: Record<string, string>;
  constructor(status: number, code: string, message: string, fields?: Record<string, string>) {
    super(message);
    this.name = 'ApiFailure';
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

export function bad(
  status: number,
  code: string,
  message: string,
  fields?: Record<string, string>,
): ApiFailure {
  return new ApiFailure(status, code, message, fields);
}

/**
 * Throwing constructors for the documented error envelope. These THROW (they
 * are caught by `respond` and mapped to the envelope), and are typed `never`
 * so TypeScript narrows guards like `if (!user) throw401();`.
 */
export function throw401(message = 'Sign in to continue.'): never {
  throw bad(401, 'unauthorized', message);
}
export function throw403(message = 'You do not have access to this action.'): never {
  throw bad(403, 'forbidden', message);
}
export function throw404(): never {
  throw bad(404, 'not_found', 'Access denied or not found.');
}
export function throw409(code: string, message: string): never {
  throw bad(409, code, message);
}
export function throw422(
  fields: Record<string, string>,
  message = 'Please correct the highlighted fields.',
): never {
  throw bad(422, 'validation_error', message, fields);
}

/* --------------------------------------------------------------- responses */

function corsHeaders(request?: Request): Record<string, string> {
  // The dev API runs on another port (localhost:8000 vs the Vite origin) and the
  // client sends credentials, so ACAO must echo the exact origin — not '*'.
  const origin = request?.headers.get('origin');
  return {
    'Access-Control-Allow-Origin': origin ?? '*',
    'Access-Control-Allow-Credentials': 'true',
    Vary: 'Origin',
  };
}

/**
 * Handler responses: the DOM `Response` MSW's HttpResponse extends, which is
 * what its handler return union accepts for any body type.
 */
type AnyResponse = Response;

export function ok(data: unknown, request?: Request, status = 200): AnyResponse {
  return HttpResponse.json(data as Record<string, unknown>, {
    status,
    headers: corsHeaders(request),
  });
}

export function fail(
  status: number,
  code: string,
  message: string,
  fields?: Record<string, string>,
  request?: Request,
): AnyResponse {
  const error: Record<string, unknown> = { code, message };
  if (fields) error.fields = fields;
  // request_id only on 5xx (requirement: error envelopes carry it for 5xx only).
  if (status >= 500) error.request_id = `req_${Math.random().toString(36).slice(2, 10)}`;
  return HttpResponse.json({ error }, { status, headers: corsHeaders(request) });
}

export function noContent(request?: Request): AnyResponse {
  return new HttpResponse(null, { status: 204, headers: corsHeaders(request) });
}

/**
 * Wraps a handler body so thrown ApiFailures become proper envelopes and any
 * unexpected throw becomes a 500 with a request_id (never a network error).
 */
export function respond(
  request: Request,
  fn: () => AnyResponse | Promise<AnyResponse>,
): Promise<AnyResponse> {
  return Promise.resolve()
    .then(fn)
    .catch((err: unknown) => {
      if (err instanceof ApiFailure)
        return fail(err.status, err.code, err.message, err.fields, request);
      const message = err instanceof Error ? err.message : 'Unexpected mock server error.';
      return fail(500, 'server_error', message, undefined, request);
    });
}

/* ----------------------------------------------------------------- parsing */

/** JSON body or `{}` when the body is missing/invalid (callers validate). */
export async function readJson<T extends object>(request: Request): Promise<T> {
  try {
    const body: unknown = await request.json();
    if (body && typeof body === 'object' && !Array.isArray(body)) return body as T;
  } catch {
    /* empty or non-JSON body: fall through */
  }
  return {} as T;
}

export function qs(request: Request): URLSearchParams {
  return new URL(request.url).searchParams;
}

/** Trimmed string field from a body, '' when absent. */
export function str(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

/** Authorization bearer token from a request, or null. */
export function bearer(request: Request): string | null {
  const header = request.headers.get('authorization');
  if (!header || !header.toLowerCase().startsWith('bearer ')) return null;
  return header.slice(7).trim();
}

/* ------------------------------------------------------------------- time */

export function nowIso(): string {
  return new Date().toISOString();
}

const whenFormatter = new Intl.DateTimeFormat('en-IN', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Asia/Kolkata',
});

/** Timeline-friendly timestamp, e.g. "26 Oct 2026, 4:30 pm IST". */
export function fmtWhen(iso: string | null | undefined): string {
  if (!iso) return '—';
  return whenFormatter.format(new Date(iso));
}

/* --------------------------------------------------------------- emitters */

export function pushEvent(
  rec: DbTicket,
  ev: Omit<TimelineEvent, 'id' | 'at'> & { at?: string },
): TimelineEvent {
  const event: TimelineEvent = { id: uid('ev'), at: ev.at ?? nowIso(), ...ev };
  rec.events.push(event);
  return event;
}

export function addAudit(entry: Omit<AuditEntry, 'id' | 'at' | 'seq'> & { at?: string }): void {
  db.audit.push({ id: uid('aud'), at: entry.at ?? nowIso(), ...entry, seq: db.audit.length + 1 });
}

let notifSeq = 0;
export function notifyUsers(
  userIds: string[],
  n: {
    text: string;
    kind: string;
    critical?: boolean;
    ticket_id?: string;
    at?: string;
    read?: boolean;
  },
): void {
  const at = n.at ?? nowIso();
  for (const id of new Set(userIds)) {
    const user = findUser(id);
    if (!user || user.state !== 'active') continue;
    notifSeq += 1;
    const row: DbNotification = {
      id: uid('ntf'),
      user_id: id,
      created_at: at,
      read: n.read ?? false,
      critical: n.critical ?? false,
      text: n.text,
      kind: n.kind,
      ...(n.ticket_id ? { ticket_id: n.ticket_id } : {}),
      seq: notifSeq,
    };
    db.notifications.push(row);
  }
}

/** Strip internal fields before returning a notification over the API. */
export function publicNotification(n: DbNotification): Notification {
  const { user_id: _user_id, seq: _seq, ...rest } = n;
  void _user_id;
  void _seq;
  return rest;
}

export function actorRef(user: DbUser): UserRef {
  return ref(user);
}
