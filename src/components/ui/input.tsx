import * as React from 'react';
import { cn } from '@/lib/cn';
import { useField } from '@/components/common/field-context';

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(
  (
    {
      className,
      type,
      id,
      'aria-invalid': ariaInvalid,
      'aria-describedby': ariaDescribedBy,
      ...props
    },
    ref,
  ) => {
    const field = useField();
    return (
      <input
        {...props}
        ref={ref}
        type={type}
        id={id ?? field?.id}
        aria-invalid={ariaInvalid ?? (field ? field.invalid : undefined)}
        aria-describedby={ariaDescribedBy ?? field?.describedBy}
        className={cn(
          'placeholder:text-muted/70 flex h-9 w-full rounded border border-line bg-surface px-3 text-body text-fg',
          'disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted',
          'aria-[invalid=true]:border-crit',
          className,
        )}
      />
    );
  },
);
Input.displayName = 'Input';
