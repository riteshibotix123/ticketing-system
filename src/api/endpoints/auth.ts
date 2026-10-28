import { api, apiFetch } from '../client';
import type { Me, PublicConfig } from '@/types/domain';

export interface LoginSuccess {
  access_token: string;
  expires_in: number;
  user: Me;
}

export type LoginResult =
  | LoginSuccess
  | { mfa_required: true; mfa_token: string }
  | { mfa_enrol_required: true; mfa_token: string };

export interface MfaSetupResult {
  secret: string;
  otpauth_uri: string;
}

export type MfaConfirmResult = LoginSuccess & { recovery_codes: string[] };

export interface SignupPayload {
  name: string;
  email: string;
  password: string;
  requested_role: 'employee' | 'admin' | 'super_admin';
  requested_department: string;
}

export interface ReapplyPayload {
  email: string;
  password: string;
  requested_role: 'employee' | 'admin' | 'super_admin';
  requested_department: string;
}

export const authApi = {
  publicConfig: () => api.get<PublicConfig>('/public/config'),

  signup: (payload: SignupPayload) =>
    apiFetch<{ message: string }>('/auth/signup', {
      method: 'POST',
      body: payload,
      noRetry: true,
    }),

  verifyEmail: (token: string) =>
    apiFetch<{ state: 'pending_approval' }>('/auth/verify-email', {
      method: 'POST',
      body: { token },
      noRetry: true,
    }),

  resendVerification: (email: string) =>
    apiFetch<void>('/auth/resend-verification', {
      method: 'POST',
      body: { email },
      noRetry: true,
    }),

  reapply: (payload: ReapplyPayload) =>
    apiFetch<void>('/auth/reapply', {
      method: 'POST',
      body: payload,
      noRetry: true,
    }),

  login: (email: string, password: string) =>
    apiFetch<LoginResult>('/auth/login', {
      method: 'POST',
      body: { email, password },
      noRetry: true,
    }),

  mfaSetup: (mfa_token: string) =>
    apiFetch<MfaSetupResult>('/auth/mfa/setup', {
      method: 'POST',
      body: { mfa_token },
      noRetry: true,
    }),

  mfaConfirm: (mfa_token: string, code: string) =>
    apiFetch<MfaConfirmResult>('/auth/mfa/confirm', {
      method: 'POST',
      body: { mfa_token, code },
      noRetry: true,
    }),

  mfaVerify: (mfa_token: string, code: string) =>
    apiFetch<LoginSuccess>('/auth/mfa/verify', {
      method: 'POST',
      body: { mfa_token, code },
      noRetry: true,
    }),

  refresh: () =>
    apiFetch<{ access_token: string; expires_in: number }>('/auth/refresh', {
      method: 'POST',
      noRetry: true,
    }),

  logout: () => api.post<void>('/auth/logout'),

  forgotPassword: (email: string) =>
    apiFetch<void>('/auth/forgot-password', {
      method: 'POST',
      body: { email },
      noRetry: true,
    }),

  resetPassword: (token: string, password: string) =>
    apiFetch<void>('/auth/reset-password', {
      method: 'POST',
      body: { token, password },
      noRetry: true,
    }),

  me: () => apiFetch<Me>('/auth/me', { method: 'GET', noRetry: true }),

  setTheme: (theme: 'system' | 'light' | 'dark') => api.patch<Me>('/auth/me', { theme }),
};
