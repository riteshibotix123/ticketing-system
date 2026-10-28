import { forwardRef, type InputHTMLAttributes } from 'react';
import { cn } from '@/lib/cn';
import { Input } from '@/components/ui/input';
import { useField } from '@/components/common/FormField';

/**
 * Digits-only MFA code input (spec 9.1): accepts paste (codes like "123-456"
 * are stripped to digits), caps at 6 digits, and wires the FormField label and
 * error. No `autoFocus` attribute — jsx-a11y no-autofocus forbids it; callers
 * focus this input through its ref instead.
 */
export const CodeInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, onChange, ...props }, ref) => {
    const field = useField();

    return (
      <Input
        {...props}
        ref={ref}
        inputMode="numeric"
        autoComplete="one-time-code"
        id={props.id ?? field?.id}
        aria-invalid={props['aria-invalid'] ?? field?.invalid ?? undefined}
        aria-describedby={props['aria-describedby'] ?? field?.describedBy}
        className={cn('mono text-center text-base tracking-[0.35em]', className)}
        onChange={(event) => {
          // Strip non-digits in the DOM before React Hook Form reads the value,
          // so pasted codes with spaces or dashes just work.
          event.target.value = event.target.value.replace(/\D/g, '').slice(0, 6);
          onChange?.(event);
        }}
      />
    );
  },
);
CodeInput.displayName = 'CodeInput';
