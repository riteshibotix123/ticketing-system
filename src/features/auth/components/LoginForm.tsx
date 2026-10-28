import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FormField } from '@/components/common/FormField';
import { useAuth } from '@/hooks/useAuth';
import { errorMessage, isApiError } from '@/api/client';
import { loginSchema, type LoginInput } from '@/lib/zod-schemas';
import { FormAlert } from './FormAlert';
import { PasswordInput } from './PasswordInput';

interface LoginFormProps {
  /** Prefill from the last attempt so "Use a different account" keeps it handy. */
  email?: string;
  onMfaRequired: (mfaToken: string, email: string) => void;
}

/**
 * Email + password step of the login flow (spec 7/9.1). Success does NOT
 * navigate: the PublicOnly guard redirects to ?next= (or /dashboard) once
 * `me` appears, and to /status/:state for non-active accounts. Leaving the
 * URL untouched keeps `next` intact.
 */
export function LoginForm({ email, onMfaRequired }: LoginFormProps) {
  const { login } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const { register, handleSubmit, setError, formState } = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: email ?? '', password: '' },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      const result = await login(values.email, values.password);
      if (result.mfaRequired && result.mfaToken) {
        onMfaRequired(result.mfaToken, values.email);
      }
      // Non-MFA success: `me` is set; the guard handles all navigation.
    } catch (err) {
      if (isApiError(err) && err.fields && Object.keys(err.fields).length > 0) {
        // 422 field errors (spec 6) surface inline…
        if (err.fields.email) setError('email', { type: 'server', message: err.fields.email });
        if (err.fields.password)
          setError('password', { type: 'server', message: err.fields.password });
        const mapped = new Set(['email', 'password']);
        if (Object.keys(err.fields).some((f) => !mapped.has(f))) setFormError(err.message);
      } else {
        // …everything else shows the server message: the generic
        // "Email or password is incorrect." for 401, "Too many attempts…"
        // for 429 (spec 7). Never invent copy.
        setFormError(errorMessage(err));
      }
    }
  });

  return (
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
      <FormField label="Password" required error={formState.errors.password?.message}>
        <PasswordInput autoComplete="current-password" {...register('password')} />
      </FormField>
      <div className="flex justify-end">
        <Link
          to="/forgot-password"
          className="text-small font-medium text-accent underline-offset-4 hover:underline"
        >
          Forgot password?
        </Link>
      </div>
      <Button
        type="submit"
        variant="primary"
        className="w-full"
        loading={formState.isSubmitting}
        loadingLabel="Signing in"
      >
        Sign in
      </Button>
    </form>
  );
}
