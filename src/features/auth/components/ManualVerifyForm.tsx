import { useForm } from 'react-hook-form';
import { useMutation } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FormField } from '@/components/common/FormField';
import { authApi } from '@/api/endpoints/auth';
import { errorMessage } from '@/api/client';
import { verifyEmailSchema } from '@/lib/zod-schemas';

type TokenInput = { token: string };

interface ManualVerifyFormProps {
  onSuccess: () => void;
  onFailure: (message: string) => void;
}

/** Manual verification-token entry used when the email link is missing (spec 9.1). */
export function ManualVerifyForm({ onSuccess, onFailure }: ManualVerifyFormProps) {
  const verify = useMutation({ mutationFn: (token: string) => authApi.verifyEmail(token) });
  const { register, handleSubmit, formState } = useForm<TokenInput>({
    resolver: zodResolver(verifyEmailSchema),
    defaultValues: { token: '' },
  });

  const onSubmit = handleSubmit((values) => {
    verify.mutate(values.token, { onSuccess, onError: (err) => onFailure(errorMessage(err)) });
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3">
      <FormField
        label="Verification token"
        required
        error={formState.errors.token?.message}
        hint="Paste the token from the verification email."
      >
        <Input
          className="mono"
          autoComplete="off"
          placeholder="mock-verify-token"
          {...register('token')}
        />
      </FormField>
      <Button
        type="submit"
        variant="primary"
        className="w-full"
        loading={verify.isPending}
        loadingLabel="Verifying"
      >
        Verify token
      </Button>
    </form>
  );
}
