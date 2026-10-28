/**
 * fetch wrapper: auth header, refresh-and-retry once, error mapping.
 * Tokens live in memory only — never in localStorage/sessionStorage (spec 18).
 */
import { API_BASE_URL } from '@/lib/constants';

export interface ApiErrorShape {
  code: string;
  message: string;
  fields?: Record<string, string>;
  request_id?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields?: Record<string, string>;
  readonly requestId?: string;

  constructor(status: number, shape: ApiErrorShape) {
    super(shape.message);
    this.name = 'ApiError';
    this.status = status;
    this.code = shape.code;
    this.fields = shape.fields;
    this.requestId = shape.request_id;
  }
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError;
}

/* ------------------------------------------------------------------ tokens */

let accessToken: string | null = null;
/** Called when the session is truly gone (refresh failed). */
let onSessionExpired: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function setSessionExpiredHandler(handler: (() => void) | null): void {
  onSessionExpired = handler;
}

/* ------------------------------------------------------------------ refresh */

let refreshPromise: Promise<string | null> | null = null;

async function doRefresh(): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) return null;
    const body = (await res.json()) as { access_token?: string; token?: string };
    const token = body.access_token ?? body.token ?? null;
    accessToken = token;
    return token;
  } catch {
    return null;
  }
}

function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

/* ------------------------------------------------------------------ errors */

function parseErrorBody(status: number, body: unknown): ApiError {
  const fallback: Record<string, string> = {
    400: 'The request was rejected.',
    401: 'Your session has expired. Please sign in again.',
    403: 'You do not have access to this action.',
    404: 'Not found.',
    409: 'This changed by someone else. Refresh to see the latest version.',
    422: 'Please correct the highlighted fields.',
    429: 'Too many attempts. Try again in a few minutes.',
  };
  if (body && typeof body === 'object' && 'error' in body) {
    const e = (body as { error: ApiErrorShape }).error;
    if (e && typeof e.message === 'string') {
      return new ApiError(status, {
        code: e.code || 'error',
        message: e.message,
        fields: e.fields,
        request_id: e.request_id,
      });
    }
  }
  if (status >= 500) {
    return new ApiError(status, {
      code: 'server_error',
      message: 'Something went wrong on our side. Try again.',
    });
  }
  return new ApiError(status, {
    code: `http_${status}`,
    message: fallback[status] ?? `Request failed (${status}).`,
  });
}

/* ------------------------------------------------------------------ fetch */

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | boolean | string[] | null | undefined>;
  signal?: AbortSignal;
  /** Skip the automatic refresh-retry (used by the refresh call itself). */
  noRetry?: boolean;
  /** Multipart upload. */
  formData?: FormData;
}

export function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === '') continue;
      if (Array.isArray(value)) {
        value
          .filter((v) => v !== '' && v !== null)
          .forEach((v) => url.searchParams.append(key, String(v)));
      } else {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, signal, noRetry, formData } = options;
  const url = buildUrl(path, query);

  const headers: Record<string, string> = {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (body !== undefined && !formData) headers['Content-Type'] = 'application/json';

  const res = await fetch(url, {
    method,
    headers,
    credentials: 'include',
    signal,
    body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
  });

  if (res.status === 401 && !noRetry) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return apiFetch<T>(path, { ...options, noRetry: true });
    }
    accessToken = null;
    onSessionExpired?.();
    throw new ApiError(401, {
      code: 'session_expired',
      message: 'Session expired. Please sign in again.',
    });
  }

  if (res.status === 204) return undefined as T;

  let payload: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!res.ok) {
    const error = parseErrorBody(res.status, payload);
    if (res.status === 409) {
      // Callers show the spec-13 toast: "This ticket changed. Refreshed..."
      throw error;
    }
    throw error;
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, query?: RequestOptions['query'], signal?: AbortSignal) =>
    apiFetch<T>(path, { method: 'GET', query, signal }),
  post: <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: 'POST', body }),
  patch: <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: 'PATCH', body }),
  put: <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: 'PUT', body }),
  del: <T>(path: string) => apiFetch<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, formData: FormData) => apiFetch<T>(path, { method: 'POST', formData }),
};

/** Human message for any thrown value. */
export function errorMessage(err: unknown): string {
  if (isApiError(err)) return err.message;
  if (err instanceof Error) return err.message;
  return 'Something went wrong.';
}
