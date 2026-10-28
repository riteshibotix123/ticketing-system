import { useEffect, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from '@/components/ui/button';
import { FormField } from '@/components/common/FormField';
import { useAuth } from '@/hooks/useAuth';
import { errorMessage } from '@/api/client';
import { mfaSchema, type MfaInput } from '@/lib/zod-schemas';
import { CodeInput } from './CodeInput';

interface MfaFormProps {
  email: string;
  mfaToken: string;
  onBack: () => void;
}

/**
 * MFA step of the login flow (spec 7/9.1): 6-digit code, paste support, shows
 * which email the code was sent to, and offers "Use a different account".
 * Success does not navigate — the PublicOnly guard redirects once `me`
 * appears (or to /status/:state for non-active accounts).
 */
export function MfaForm({ email, mfaToken, onBack }: MfaFormProps) {
  const { verifyMfa } = useAuth();
  const codeRef = useRef<HTMLInputElement | null>(null);
  const { register, handleSubmit, setError, formState } = useForm<MfaInput>({
    resolver: zodResolver(mfaSchema),
    defaultValues: { code: '' },
  });
  const { ref: registerRef, ...codeRegister } = register('code');

  // Merge React Hook Form's ref with ours (register options cannot override
  // the ref in this RHF version).
  const setCodeRef = (node: HTMLInputElement | null) => {
    registerRef(node);
    codeRef.current = node;
  };

  // jsx-a11y no-autofocus makes the autoFocus attribute an error — focus the
  // code input with a ref + effect instead (spec 9.1).
  useEffect(() => {
    codeRef.current?.focus();
  }, []);

  const onSubmit = handleSubmit(async (values) => {
    try {
      await verifyMfa(mfaToken, values.code);
      // No manual navigation: PublicOnly redirects when `me` appears.
    } catch (err) {
      // Invalid code (or server trouble) maps to an inline field error.
      setError('code', { type: 'server', message: errorMessage(err) });
    }
  });

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex flex-col gap-4"
      aria-busy={formState.isSubmitting}
    >
      <p className="text-small text-muted">
        We sent a 6-digit code to <span className="font-medium text-fg">{email}</span>.
      </p>
      <FormField
        label="Verification code"
        required
        error={formState.errors.code?.message}
        hint={import.meta.env.DEV ? 'Mock code: 123456' : undefined}
      >
        {/* Keep React Hook Form's ref while also holding ours for the focus effect. */}
        <CodeInput placeholder="123456" ref={setCodeRef} {...codeRegister} />
      </FormField>
      <Button
        type="submit"
        variant="primary"
        className="w-full"
        loading={formState.isSubmitting}
        loadingLabel="Verifying"
      >
        Verify code
      </Button>
      <Button
        type="button"
        variant="ghost"
        className="w-full"
        onClick={onBack}
        disabled={formState.isSubmitting}
      >
        Use a different account
      </Button>
    </form>
  );
}
