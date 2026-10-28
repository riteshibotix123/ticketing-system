import { AlertTriangle, Inbox, Lock, SearchX } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

interface StateProps {
  title?: string;
  description?: string;
  action?: React.ReactNode;
}

function StateShell({
  icon,
  tone,
  title,
  description,
  action,
}: StateProps & { icon: React.ReactNode; tone: string }) {
  return (
    <div className="card flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <span className={tone} aria-hidden="true">
        {icon}
      </span>
      <h2 className="text-section-title text-fg">{title ?? 'Nothing here yet.'}</h2>
      {description ? <p className="max-w-[46ch] text-small text-muted">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

/** Empty: short explanation and the next step (spec 13). */
export function EmptyState({
  title = 'Nothing here yet.',
  description,
  action,
  variant = 'default',
}: StateProps & { variant?: 'default' | 'filtered' }) {
  return (
    <StateShell
      icon={
        variant === 'filtered' ? <SearchX className="h-6 w-6" /> : <Inbox className="h-6 w-6" />
      }
      tone="text-muted"
      title={title}
      description={description}
      action={action}
    />
  );
}

/** Error: message, request ID if given, and Retry (spec 13). */
export function ErrorState({
  message = 'Something went wrong.',
  requestId,
  onRetry,
}: {
  message?: string;
  requestId?: string;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="card flex flex-col items-center gap-2 px-6 py-10 text-center">
      <AlertTriangle className="h-6 w-6 text-crit" aria-hidden="true" />
      <h2 className="text-section-title text-fg">Could not load this page</h2>
      <p className="max-w-[46ch] text-small text-muted">{message}</p>
      {requestId ? <p className="mono text-small text-muted">Request ID: {requestId}</p> : null}
      {onRetry ? (
        <Button variant="secondary" size="sm" className="mt-2" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}

/** Forbidden: "You do not have access to this page." with a link home (spec 4.3/13). */
export function ForbiddenState({
  message = 'You do not have access to this page.',
}: {
  message?: string;
}) {
  return (
    <div role="alert" className="card flex flex-col items-center gap-2 px-6 py-10 text-center">
      <Lock className="h-6 w-6 text-warn" aria-hidden="true" />
      <h2 className="text-section-title text-fg">Access denied</h2>
      <p className="max-w-[46ch] text-small text-muted">{message}</p>
      <Link
        to="/dashboard"
        className="mt-2 text-small font-medium text-accent underline-offset-4 hover:underline"
      >
        Back to dashboard
      </Link>
    </div>
  );
}

/**
 * 404 / no access on a ticket: reveals nothing about the ticket (spec 9.6/18).
 */
export function NotFoundState({ message = 'Access denied or not found.' }: { message?: string }) {
  return (
    <div role="alert" className="card flex flex-col items-center gap-2 px-6 py-10 text-center">
      <Inbox className="h-6 w-6 text-muted" aria-hidden="true" />
      <h2 className="text-section-title text-fg">{message}</h2>
      <p className="max-w-[46ch] text-small text-muted">
        If you expected access, ask an administrator to share the ticket with you.
      </p>
      <Link
        to="/tickets"
        className="mt-2 text-small font-medium text-accent underline-offset-4 hover:underline"
      >
        Back to tickets
      </Link>
    </div>
  );
}

/** Offline banner (spec 13). */
export function OfflineBanner({ online }: { online: boolean }) {
  if (online) return null;
  return (
    <div role="status" className="bg-warn-soft px-4 py-2 text-center text-small text-warn">
      You are offline. Changes will not be saved.
    </div>
  );
}
