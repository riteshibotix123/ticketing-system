import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { AuthShell } from '@/features/auth/components/AuthShell';
import { FormAlert } from '@/features/auth/components/FormAlert';
import { ManualVerifyForm } from '@/features/auth/components/ManualVerifyForm';
import { ResendVerificationForm } from '@/features/auth/components/ResendVerificationForm';
import { Skeleton } from '@/components/ui/skeleton';
import { authApi } from '@/api/endpoints/auth';
import { errorMessage } from '@/api/client';

type Phase = 'verifying' | 'success' | 'manual';

/**
 * Email verification (spec 9.1): reads ?token= and verifies once on mount.
 * With no token — or after a failure — it shows the manual token field and
 * the resend form (cooldown inside ResendVerificationForm).
 */
export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const urlToken = searchParams.get('token') ?? '';
  const [phase, setPhase] = useState<Phase>(urlToken ? 'verifying' : 'manual');
  const [failureMessage, setFailureMessage] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (!urlToken || started.current) return;
    started.current = true; // verify exactly once per mount (spec task rule)
    let active = true;
    authApi
      .verifyEmail(urlToken)
      .then(() => {
        if (active) setPhase('success');
      })
      .catch((err: unknown) => {
        if (!active) return;
        setFailureMessage(errorMessage(err));
        setPhase('manual');
      });
    return () => {
      active = false;
    };
  }, [urlToken]);

  if (phase === 'verifying') {
    return (
      <AuthShell title="Verifying email">
        <div role="status" className="flex flex-col gap-3">
          <p className="text-small text-muted">Checking your verification link…</p>
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      </AuthShell>
    );
  }

  if (phase === 'success') {
    return (
      <AuthShell title="Email verified">
        <div className="flex flex-col gap-4">
          <p role="status" className="text-small text-muted">
            Email verified. Your request is waiting for approval.
          </p>
          <Button asChild variant="primary" className="w-full">
            <Link to="/login">Go to sign in</Link>
          </Button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Verify your email"
      subtitle="Paste the token from your verification email, or ask for a new link."
    >
      <div className="flex flex-col gap-5">
        <FormAlert message={failureMessage} />
        <ManualVerifyForm
          onSuccess={() => {
            setFailureMessage(null);
            setPhase('success');
          }}
          onFailure={(message) => setFailureMessage(message)}
        />
        <ResendVerificationForm />
      </div>
    </AuthShell>
  );
}
