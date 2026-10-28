import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Controller, useForm } from 'react-hook-form';
import { useMutation, useQuery } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SelectItem } from '@/components/ui/select';
import { FormField } from '@/components/common/FormField';
import { authApi, type SignupPayload } from '@/api/endpoints/auth';
import { departmentsApi } from '@/api/endpoints/departments';
import { queryKeys } from '@/api/queryKeys';
import { errorMessage, isApiError } from '@/api/client';
import { MIN_PASSWORD_LENGTH } from '@/lib/constants';
import { signupSchema, type SignupInput } from '@/lib/zod-schemas';
import { FormAlert } from './FormAlert';
import { PasswordInput } from './PasswordInput';
import { PasswordStrengthMeter } from './PasswordStrengthMeter';
import { SelectField } from './SelectField';

const SIGNUP_FIELDS = [
  'name',
  'email',
  'password',
  'requested_role',
  'requested_department',
] as const;

/** Self-signup form (spec 9.1 + 1.3). On success the parent shows the notice. */
export function SignupForm({ onSuccess }: { onSuccess: (email: string) => void }) {
  const [formError, setFormError] = useState<string | null>(null);
  const departments = useQuery({
    queryKey: queryKeys.departments,
    queryFn: () => departmentsApi.list(),
  });
  const signup = useMutation({ mutationFn: (payload: SignupPayload) => authApi.signup(payload) });
  const { register, control, handleSubmit, setError, watch, formState } = useForm<SignupInput>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      name: '',
      email: '',
      password: '',
      requested_role: 'employee',
      requested_department: '',
    },
  });

  // Only active departments are pickable at signup (spec 1.3/9.1).
  const activeDepartments = useMemo(
    () => (departments.data ?? []).filter((d) => d.active),
    [departments.data],
  );

  const onSubmit = handleSubmit((values) => {
    setFormError(null);
    signup.mutate(values, {
      onSuccess: () => onSuccess(values.email),
      onError: (err) => {
        // Server rejections (e.g. "domain not allowed") come back in
        // error.fields — map them inline; anything else is a form banner.
        const fields = isApiError(err) ? (err.fields ?? {}) : {};
        let mapped = 0;
        for (const name of SIGNUP_FIELDS) {
          const message = fields[name];
          if (message) {
            setError(name, { type: 'server', message });
            mapped += 1;
          }
        }
        if (mapped === 0) setFormError(errorMessage(err));
      },
    });
  });

  const departmentField = departments.isError ? (
    <FormField label="Department" required error={formState.errors.requested_department?.message}>
      <div className="flex items-center justify-between gap-3 rounded border border-line bg-surface-2 px-3 py-2">
        <p role="alert" className="text-small text-crit">
          Could not load departments.
        </p>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => void departments.refetch()}
          loading={departments.isFetching}
        >
          Retry
        </Button>
      </div>
    </FormField>
  ) : (
    <Controller
      control={control}
      name="requested_department"
      render={({ field, fieldState }) => (
        <SelectField
          label="Department"
          required
          placeholder={departments.isLoading ? 'Loading departments…' : 'Pick a department'}
          value={field.value}
          onValueChange={field.onChange}
          error={fieldState.error?.message}
          disabled={departments.isLoading || activeDepartments.length === 0}
          hint={
            !departments.isLoading && activeDepartments.length === 0
              ? 'No active departments are available yet.'
              : undefined
          }
        >
          {activeDepartments.map((d) => (
            <SelectItem key={d.id} value={d.id}>
              {d.name}
            </SelectItem>
          ))}
        </SelectField>
      )}
    />
  );

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex flex-col gap-4"
      aria-busy={formState.isSubmitting}
    >
      <FormAlert message={formError} />
      <FormField label="Full name" required error={formState.errors.name?.message}>
        <Input autoComplete="name" placeholder="Asha Verma" {...register('name')} />
      </FormField>
      <FormField
        label="Company email"
        required
        error={formState.errors.email?.message}
        hint="Must end with your company domain."
      >
        <Input
          type="email"
          autoComplete="email"
          placeholder="you@ibotix.ai"
          {...register('email')}
        />
      </FormField>
      <FormField
        label="Password"
        required
        error={formState.errors.password?.message}
        hint={`Use at least ${MIN_PASSWORD_LENGTH} characters.`}
      >
        <PasswordInput autoComplete="new-password" {...register('password')} />
        <PasswordStrengthMeter value={watch('password') ?? ''} />
      </FormField>
      {departmentField}
      <Controller
        control={control}
        name="requested_role"
        render={({ field, fieldState }) => (
          <SelectField
            label="Requested role"
            required
            value={field.value}
            onValueChange={field.onChange}
            error={fieldState.error?.message}
            hint={field.value === 'employee' ? undefined : 'Needs approval from a Super Admin'}
          >
            <SelectItem value="employee">Employee</SelectItem>
            <SelectItem value="admin" hint="Needs approval">
              Admin
            </SelectItem>
            <SelectItem value="super_admin" hint="Needs approval">
              Super Admin
            </SelectItem>
          </SelectField>
        )}
      />
      <Button
        type="submit"
        variant="primary"
        className="w-full"
        loading={signup.isPending}
        loadingLabel="Creating account"
      >
        Create account
      </Button>
      <p className="text-center text-small text-muted">
        Already have an account?{' '}
        <Link to="/login" className="font-medium text-accent underline-offset-4 hover:underline">
          Sign in
        </Link>
      </p>
    </form>
  );
}
