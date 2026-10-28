/**
 * Regression test: AuthProvider must install the access token BEFORE probing
 * /auth/me (spec 7). A provider that probes first logs the user out
 * immediately after a successful login.
 */
import { describe, expect, it, afterAll, beforeAll, afterEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor, act } from '@testing-library/react';
import type { ReactNode } from 'react';
import { server } from '@/mocks/server';
import { setAccessToken } from '@/api/client';
import { AuthProvider, useAuth } from '@/app/providers/AuthProvider';
import { ASHA, PASSWORD, ROHAN, MFA_CODE } from './msw-session';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  setAccessToken(null);
  cleanupWrapper();
});
afterAll(() => server.close());

let unmount: (() => void) | undefined;
function cleanupWrapper() {
  unmount?.();
  unmount = undefined;
}

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    );
  };
}

describe('AuthProvider (spec 7)', () => {
  it('keeps the session after a non-MFA login', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.status).toBe('ready'));

    await act(async () => {
      const res = await result.current.login(ASHA, PASSWORD);
      expect(res.mfaRequired).toBe(false);
    });

    expect(result.current.me?.email).toBe(ASHA);
    expect(result.current.me?.permissions).toContain('tickets.create');
  });

  it('keeps the session after the MFA step', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.status).toBe('ready'));

    let mfaToken = '';
    await act(async () => {
      const res = await result.current.login(ROHAN, PASSWORD);
      expect(res.mfaRequired).toBe(true);
      mfaToken = res.mfaToken ?? '';
    });
    expect(result.current.me).toBeNull();

    await act(async () => {
      await result.current.verifyMfa(mfaToken, MFA_CODE);
    });
    expect(result.current.me?.email).toBe(ROHAN);
    expect(result.current.me?.roles).toContain('spoke');
  });
});
