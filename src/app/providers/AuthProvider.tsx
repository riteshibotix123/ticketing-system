import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { authApi, type MeResponse } from '@/api/endpoints/auth';
import { setAccessToken, setSessionExpiredHandler } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';

export interface AuthResult {
  mfaRequired: boolean;
  mfaToken?: string;
}

interface AuthContextValue {
  me: MeResponse | null;
  status: 'loading' | 'ready';
  /** True while the "Session expired" dialog is showing. */
  sessionExpired: boolean;
  login: (email: string, password: string) => Promise<AuthResult>;
  verifyMfa: (mfaToken: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
  dismissSessionExpired: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Install the access token, load /auth/me, and clear the token if that fails. */
async function adoptSession(access_token: string | undefined): Promise<MeResponse> {
  setAccessToken(access_token ?? null);
  try {
    return await authApi.me();
  } catch (err) {
    setAccessToken(null);
    throw err;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready'>('loading');
  const [sessionExpired, setSessionExpired] = useState(false);
  const queryClient = useQueryClient();

  const loadMe = useCallback(async () => {
    try {
      const next = await authApi.me();
      setMe(next);
    } catch {
      // 401 (not signed in) or a network failure: treat as anonymous.
      setMe(null);
      setAccessToken(null);
    } finally {
      setStatus('ready');
    }
  }, []);

  // App start: call /auth/me (spec 7).
  useEffect(() => {
    void loadMe();
  }, [loadMe]);

  // Refresh failure anywhere in the app → "Session expired" modal → /login.
  useEffect(() => {
    setSessionExpiredHandler(() => {
      setSessionExpired(true);
      setMe(null);
    });
    return () => setSessionExpiredHandler(null);
  }, []);

  const login = useCallback<AuthContextValue['login']>(async (email, password) => {
    const res = await authApi.login(email, password);
    if (res.mfa_required && res.mfa_token) {
      return { mfaRequired: true, mfaToken: res.mfa_token };
    }
    // The token must be installed BEFORE /auth/me (spec 7), or the probe 401s.
    const next = await adoptSession(res.access_token);
    setMe(next);
    return { mfaRequired: false };
  }, []);

  const verifyMfa = useCallback<AuthContextValue['verifyMfa']>(async (mfaToken, code) => {
    const res = await authApi.mfaVerify(mfaToken, code);
    const next = await adoptSession(res.access_token);
    setMe(next);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Logging out locally matters more than the server call.
    }
    setAccessToken(null);
    setMe(null);
    queryClient.clear(); // spec 7: logout clears the Query cache
  }, [queryClient]);

  const refreshMe = useCallback(async () => {
    await loadMe();
    queryClient.invalidateQueries({ queryKey: queryKeys.me });
  }, [loadMe, queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      me,
      status,
      sessionExpired,
      login,
      verifyMfa,
      logout,
      refreshMe,
      dismissSessionExpired: () => setSessionExpired(false),
    }),
    [me, status, sessionExpired, login, verifyMfa, logout, refreshMe],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
