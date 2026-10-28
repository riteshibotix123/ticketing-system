import { Link, useParams, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { FullPageSkeleton } from '@/components/ui/skeleton';
import { AuthShell } from '@/features/auth/components/AuthShell';
import { ResendButton } from '@/features/auth/components/ResendButton';
import { useAuth } from '@/hooks/useAuth';
import type { MeResponse } from '@/api/endpoints/auth';
import { ROLE_LABEL } from '@/lib/constants';
import type { Role } from '@/types/domain';

const FALLBACK_REASON = 'Contact an administrator.';
const linkCls = 'font-medium text-accent underline-offset-4 hover:underline';

/**
 * The mock `/auth/me` includes requested_role/requested_department for pending
 * accounts as extra fields the `Me` domain type does not declare — the real
 * backend may omit them. Read them defensively through an optional cast so
 * either payload shape renders safely.
 */
interface PendingRequestFields {
  requested_role?: string;
  requested_department?: string;
}

function readPendingRequest(me: MeResponse | null): PendingRequestFields {
  return (me ?? {}) as unknown as PendingRequestFields;
}

function requestedRoleLabel(role: string | undefined): string {
  if (!role) return 'not specified';
  return role in ROLE_LABEL ? ROLE_LABEL[role as Role] : role;
}

function statusLink(to: string, label: string) {
  return (
    <p className="text-small text-muted">
      <Link to={to} className={linkCls}>
        {label}
      </Link>
    </p>
  );
}

/**
 * Account-state pages (spec 7): rendered outside the app shell (see
 * router.tsx) for pending / rejected / deactivated accounts.
 */
export default function StatusPage() {
  const { state } = useParams<{ state: string }>();
  const { me, status } = useAuth();
  const [searchParams] = useSearchParams();

  if (status === 'loading') return <FullPageSkeleton />;

  const pending = readPendingRequest(me);

  switch (state) {
    case 'pending_verification':
      return (
        <AuthShell title="Verify your email" subtitle="One last step before your request is sent.">
          <div className="flex flex-col gap-4">
            <p className="text-small text-muted">Check your email to verify your address.</p>
            {me ? (
              <ResendButton email={me.email} />
            ) : (
              <p className="text-small text-muted">
                Sign in again to resend the verification email.
              </p>
            )}
            {statusLink('/login', 'Back to sign in')}
          </div>
        </AuthShell>
      );

    case 'pending_approval':
      return (
        <AuthShell
          title="Waiting for approval"
          subtitle="Your request is waiting for approval. We will email you."
        >
          <dl className="flex flex-col gap-3">
            <div>
              <dt className="label-caps">Requested role</dt>
              <dd className="text-body text-fg">{requestedRoleLabel(pending.requested_role)}</dd>
            </div>
            <div>
              <dt className="label-caps">Requested department</dt>
              <dd className="text-body text-fg">
                {pending.requested_department ?? 'not specified'}
              </dd>
            </div>
          </dl>
          <div className="mt-4">{statusLink('/login', 'Back to sign in')}</div>
        </AuthShell>
      );

    case 'rejected': {
      const reason = (searchParams.get('reason') ?? '').trim() || FALLBACK_REASON;
      return (
        <AuthShell title="Request not approved">
          <div className="flex flex-col gap-4">
            <p
              role="alert"
              className="border-crit/40 rounded border bg-crit-soft px-3 py-2 text-small text-crit"
            >
              Your request was not approved. Reason: {reason}.
            </p>
            <p className="text-small text-muted">
              You can submit a new request with different details.
            </p>
            <Button asChild variant="primary" className="w-full">
              <Link to="/signup">Request access again</Link>
            </Button>
            {statusLink('/login', 'Back to sign in')}
          </div>
        </AuthShell>
      );
    }

    case 'deactivated':
      return (
        <AuthShell title="Account deactivated">
          <div className="flex flex-col gap-4">
            <p
              role="alert"
              className="border-crit/40 rounded border bg-crit-soft px-3 py-2 text-small text-crit"
            >
              Your account is deactivated. Contact an administrator.
            </p>
            {statusLink('/login', 'Back to sign in')}
          </div>
        </AuthShell>
      );

    default:
      return (
        <AuthShell title="Unknown account status">
          <div className="flex flex-col gap-4">
            <p className="text-small text-muted">
              This link does not match any account status. Go home or sign in.
            </p>
            {statusLink('/', 'Go home')}
            {statusLink('/login', 'Back to sign in')}
          </div>
        </AuthShell>
      );
  }
}
