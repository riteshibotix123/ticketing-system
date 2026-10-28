import { api, apiFetch } from '../client';
import type { AccountState, Me, PublicConfig, Role } from '@/types/domain';

export interface LoginResponse {
  access_token?: string;
  token_type?: string;
  mfa_required?: boolean;
  mfa_token?: string;
}

export interface MeResponse extends Me {
  account_state?: AccountState;
}

export interface SignupPayload {
  name: string;
  email: string;
  password: string;
  requested_role: 'employee' | 'admin' | 'super_admin';
  requested_department: string;
}

export const authApi = {
  publicConfig: () => api.get<PublicConfig>('/public/config'),

  signup: (payload: SignupPayload) =>
    apiFetch<{ status: string; dev_token?: string }>('/auth/signup', {
      method: 'POST',
      body: payload,
      noRetry: true,
    }),

  verifyEmail: (token: string) =>
    apiFetch<{ status: string }>('/auth/verify-email', {
      method: 'POST',
      body: { token },
      noRetry: true,
    }),

  resendVerification: (email: string) =>
    apiFetch<{ status: string }>('/auth/resend-verification', {
      method: 'POST',
      body: { email },
      noRetry: true,
    }),

  login: (email: string, password: string) =>
    apiFetch<LoginResponse>('/auth/login', {
      method: 'POST',
      body: { email, password },
      noRetry: true,
    }),

  mfaVerify: (mfa_token: string, code: string) =>
    apiFetch<LoginResponse>('/auth/mfa/verify', {
      method: 'POST',
      body: { mfa_token, code },
      noRetry: true,
    }),

  logout: () => api.post<void>('/auth/logout'),

  forgotPassword: (email: string) =>
    apiFetch<{ status: string }>('/auth/forgot-password', {
      method: 'POST',
      body: { email },
      noRetry: true,
    }),

  resetPassword: (token: string, password: string) =>
    apiFetch<{ status: string }>('/auth/reset-password', {
      method: 'POST',
      body: { token, password },
      noRetry: true,
    }),

  /** Initial session probe: a 401 here just means "not signed in". */
  me: () => apiFetch<MeResponse>('/auth/me', { method: 'GET', noRetry: true }),

  setTheme: (theme: 'system' | 'light' | 'dark') =>
    api.patch<{ status: string }>('/auth/me', { theme }),
};

export type { Role };
