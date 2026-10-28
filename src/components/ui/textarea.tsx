import * as React from 'react';
import { cn } from '@/lib/cn';
import { useField } from '@/components/common/field-context';

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(
  (
    { className, id, 'aria-invalid': ariaInvalid, 'aria-describedby': ariaDescribedBy, ...props },
    ref,
  ) => {
    const field = useField();
    return (
      <textarea
        {...props}
        ref={ref}
        id={id ?? field?.id}
        aria-invalid={ariaInvalid ?? (field ? field.invalid : undefined)}
        aria-describedby={ariaDescribedBy ?? field?.describedBy}
        className={cn(
          'placeholder:text-muted/70 flex min-h-[80px] w-full rounded border border-line bg-surface px-3 py-2 text-body text-fg',
          'disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted',
          'aria-[invalid=true]:border-crit',
          className,
        )}
      />
    );
  },
);
Textarea.displayName = 'Textarea';
