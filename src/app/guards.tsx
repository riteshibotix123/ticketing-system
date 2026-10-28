import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { usePermissions } from '@/hooks/usePermissions';
import { FullPageSkeleton } from '@/components/ui/skeleton';
import { ForbiddenState } from '@/components/common/States';

function nextParam(pathname: string, search: string): string {
  return encodeURIComponent(`${pathname}${search}`);
}

/** Unauthenticated users go to /login?next=... (spec 4.3). */
export function RequireAuth() {
  const { me, status } = useAuth();
  const location = useLocation();

  if (status === 'loading') return <FullPageSkeleton />;
  if (!me)
    return <Navigate to={`/login?next=${nextParam(location.pathname, location.search)}`} replace />;

  if (me.account_state && me.account_state !== 'active') {
    // Pending / rejected / deactivated never reach the app shell (spec 4.3).
    return <Navigate to={`/status/${me.account_state}`} replace />;
  }

  return <Outlet />;
}

/** Only for anonymous visitors; signed-in users bounce to their destination. */
export function PublicOnly() {
  const { me, status } = useAuth();
  const location = useLocation();

  if (status === 'loading') return <FullPageSkeleton />;

  // account_state is only present for non-active users (spec 6.1); presence-check
  // first so an active session is never bounced to /status/undefined.
  if (me && me.account_state != null && me.account_state !== 'active') {
    return <Navigate to={`/status/${me.account_state}`} replace />;
  }

  if (me) {
    const next = new URLSearchParams(location.search).get('next');
    return <Navigate to={next && next.startsWith('/') ? next : '/dashboard'} replace />;
  }

  return <Outlet />;
}

/**
 * Shows `ForbiddenState` (not a redirect) when the permission flag is missing
 * (spec 4.3). Pass `anyOf` when several flags grant access (config screens are
 * viewable with any config permission, editable only with the specific one).
 * The backend still enforces everything.
 */
export function RequirePermission({ flag, anyOf }: { flag?: string; anyOf?: string[] }) {
  const { can, loading } = usePermissions();

  if (loading) return <FullPageSkeleton />;
  const allowed = anyOf ? anyOf.some((f) => can(f)) : flag ? can(flag) : false;
  if (!allowed) return <ForbiddenState />;
  return <Outlet />;
}
