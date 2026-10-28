import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { MailCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FormField } from '@/components/common/FormField';
import { AuthShell } from '@/features/auth/components/AuthShell';
import { FormAlert } from '@/features/auth/components/FormAlert';
import { authApi } from '@/api/endpoints/auth';
import { errorMessage } from '@/api/client';
import { USE_MOCKS } from '@/lib/constants';
import { forgotPasswordSchema, type ForgotPasswordInput } from '@/lib/zod-schemas';

/**
 * Forgot password (spec 6.1/9.1): email in, neutral success panel out —
 * the copy never reveals whether the address exists.
 */
export default function ForgotPasswordPage() {
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<ForgotPasswordInput>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: '' },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await authApi.forgotPassword(values.email);
      setSentTo(values.email);
    } catch (err) {
      setFormError(errorMessage(err));
    }
  });

  if (sentTo) {
    return (
      <AuthShell title="Check your email">
        <div className="flex flex-col gap-4">
          <div className="border-accent/40 flex items-start gap-2 rounded border bg-accent-soft px-3 py-2.5">
            <MailCheck className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
            <div>
              <p className="text-body font-medium text-fg">
                If that address exists, a reset link is on its way.
              </p>
              <p className="mt-0.5 text-small text-muted">Check the inbox for {sentTo}.</p>
            </div>
          </div>
          {USE_MOCKS ? (
            <p className="text-small text-muted">
              Mock shortcut:{' '}
              <Link
                to="/reset-password?token=mock-reset-token"
                className="font-medium text-accent underline-offset-4 hover:underline"
              >
                open the mock reset link
              </Link>
            </p>
          ) : null}
          <p className="text-small text-muted">
            Wrong address?{' '}
            <Link
              to="/login"
              className="font-medium text-accent underline-offset-4 hover:underline"
            >
              Back to sign in
            </Link>
          </p>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Forgot password"
      subtitle="Enter your company email and we will send you a link to set a new password."
    >
      <form
        onSubmit={onSubmit}
        noValidate
        className="flex flex-col gap-4"
        aria-busy={formState.isSubmitting}
      >
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
          variant="primary"
          className="w-full"
          loading={formState.isSubmitting}
          loadingLabel="Sending"
        >
          Send reset link
        </Button>
        <p className="text-center text-small text-muted">
          <Link to="/login" className="font-medium text-accent underline-offset-4 hover:underline">
            Back to sign in
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}
