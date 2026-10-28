import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { authApi } from '@/api/endpoints/auth';
import { errorMessage } from '@/api/client';
import { useToast } from '@/hooks/useToast';

const COOLDOWN_SECONDS = 60;

/**
 * Resend-verification button for a known address with the 60s cooldown from
 * spec 7. The cooldown starts on mount (an email was just sent) and restarts
 * after every resend.
 */
export function ResendButton({
  email,
  label = 'Resend verification email',
}: {
  email: string;
  label?: string;
}) {
  const { success, error: showError } = useToast();
  const [secondsLeft, setSecondsLeft] = useState(COOLDOWN_SECONDS);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (secondsLeft <= 0) return undefined;
    const timer = window.setTimeout(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [secondsLeft]);

  const resend = async () => {
    setPending(true);
    try {
      await authApi.resendVerification(email);
      success('Verification email sent.');
      setSecondsLeft(COOLDOWN_SECONDS);
    } catch (err) {
      showError(errorMessage(err));
    } finally {
      setPending(false);
    }
  };

  const cooling = secondsLeft > 0;
  return (
    <Button
      type="button"
      variant="secondary"
      className="w-full"
      onClick={resend}
      disabled={cooling}
      loading={pending}
      loadingLabel="Sending"
    >
      {cooling ? `Resend in ${secondsLeft}s` : label}
    </Button>
  );
}
