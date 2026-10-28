import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FormField } from '@/components/common/FormField';
import { AuthShell } from '@/features/auth/components/AuthShell';
import { FormAlert } from '@/features/auth/components/FormAlert';
import { PasswordInput } from '@/features/auth/components/PasswordInput';
import { PasswordStrengthMeter } from '@/features/auth/components/PasswordStrengthMeter';
import { authApi } from '@/api/endpoints/auth';
import { errorMessage } from '@/api/client';
import { useToast } from '@/hooks/useToast';
import { MIN_PASSWORD_LENGTH } from '@/lib/constants';
import { resetPasswordSchema, type ResetPasswordInput } from '@/lib/zod-schemas';

/**
 * Reset password (spec 6.1/9.1): token comes from ?token=; when it is missing
 * the token field is shown. Success toasts, then offers the way to /login.
 */
export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const urlToken = searchParams.get('token') ?? '';
  const { success } = useToast();
  const [formError, setFormError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const { register, handleSubmit, watch, formState } = useForm<ResetPasswordInput>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { token: urlToken, password: '', confirm: '' },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await authApi.resetPassword(values.token, values.password);
      success('Password updated.', 'Sign in with your new password.');
      setDone(true);
    } catch (err) {
      setFormError(errorMessage(err));
    }
  });

  if (done) {
    return (
      <AuthShell title="Password updated">
        <div className="flex flex-col gap-4">
          <p role="status" className="text-small text-muted">
            Your password was reset. Sign in with the new password.
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
      title="Reset password"
      subtitle={
        urlToken
          ? 'Choose a new password for your account.'
          : 'Paste the token from your reset email and choose a new password.'
      }
    >
      <form
        onSubmit={onSubmit}
        noValidate
        className="flex flex-col gap-4"
        aria-busy={formState.isSubmitting}
      >
        <FormAlert message={formError} />
        {urlToken ? null : (
          <FormField label="Reset token" required error={formState.errors.token?.message}>
            <Input
              className="mono"
              autoComplete="off"
              placeholder="mock-reset-token"
              {...register('token')}
            />
          </FormField>
        )}
        <FormField
          label="New password"
          required
          error={formState.errors.password?.message}
          hint={`Use at least ${MIN_PASSWORD_LENGTH} characters.`}
        >
          <PasswordInput autoComplete="new-password" {...register('password')} />
          <PasswordStrengthMeter value={watch('password') ?? ''} />
        </FormField>
        <FormField label="Confirm password" required error={formState.errors.confirm?.message}>
          <PasswordInput autoComplete="new-password" {...register('confirm')} />
        </FormField>
        <Button
          type="submit"
          variant="primary"
          className="w-full"
          loading={formState.isSubmitting}
          loadingLabel="Saving"
        >
          Reset password
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
