import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useOnlineStatus } from '@/hooks/useDebounce';
import { Sidebar } from '@/components/layout/Sidebar';
import { Topbar } from '@/components/layout/Topbar';
import { OfflineBanner } from '@/components/common/States';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { SESSION_EXPIRED_MESSAGE } from '@/lib/constants';

/**
 * "Session expired" modal (spec 7): shown when the access token expires and
 * refresh fails. Continuing goes to /login?next=<current path>.
 */
export function SessionExpiredDialog() {
  const { sessionExpired, dismissSessionExpired } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  if (!sessionExpired) return null;

  function continueToLogin() {
    dismissSessionExpired();
    const next = `${location.pathname}${location.search}`;
    navigate(`/login?next=${encodeURIComponent(next)}`, { replace: true });
  }

  return (
    <Dialog open onOpenChange={(open) => !open && continueToLogin()}>
      <DialogContent hideClose>
        <DialogHeader>
          <DialogTitle>Session expired</DialogTitle>
          <DialogDescription>{SESSION_EXPIRED_MESSAGE}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="primary" onClick={continueToLogin}>
            Sign in again
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Authenticated app shell: sidebar + sticky top bar + content (max 1240px). */
export function AppShell() {
  const online = useOnlineStatus();

  return (
    <div className="flex min-h-dvh flex-col nav:flex-row">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <OfflineBanner online={online} />
        <main className="safe-pb w-full max-w-[1240px] flex-1 px-4 py-5 nav:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
