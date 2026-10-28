import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FormField } from '@/components/common/FormField';
import { authApi } from '@/api/endpoints/auth';
import { errorMessage } from '@/api/client';
import { useToast } from '@/hooks/useToast';
import { forgotPasswordSchema, type ForgotPasswordInput } from '@/lib/zod-schemas';
import { FormAlert } from './FormAlert';

const COOLDOWN_SECONDS = 60;

/**
 * Resend-verification form for users without a fresh email link (verify-email
 * failure or no token in the URL). Shows a confirmation and the 60s cooldown
 * after each send.
 */
export function ResendVerificationForm() {
  const { success } = useToast();
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<ForgotPasswordInput>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: '' },
  });

  useEffect(() => {
    if (secondsLeft <= 0) return undefined;
    const timer = window.setTimeout(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [secondsLeft]);

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await authApi.resendVerification(values.email);
      setSentTo(values.email);
      setSecondsLeft(COOLDOWN_SECONDS);
      success('Verification email sent.');
    } catch (err) {
      setFormError(errorMessage(err));
    }
  });

  const cooling = secondsLeft > 0;
  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex flex-col gap-3"
      aria-busy={formState.isSubmitting}
    >
      <h2 className="text-section-title text-fg">Resend the link</h2>
      {sentTo && cooling ? (
        <p role="status" className="text-small text-ok">
          A new verification link is on its way to {sentTo}.
        </p>
      ) : null}
      <FormAlert message={formError} />
      <FormField label="Company email" required error={formState.errors.email?.message}>
        <Input
          type="email"
          autoComplete="email"
          placeholder="you@ibotix.ai"
          {...register('email')}
        />
      </FormField>
      <Button
        type="submit"
        variant="secondary"
        className="w-full"
        loading={formState.isSubmitting}
        loadingLabel="Sending"
        disabled={cooling}
      >
        {cooling ? `Resend in ${secondsLeft}s` : 'Resend verification email'}
      </Button>
    </form>
  );
}
