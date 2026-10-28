import { useId, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { FieldContext, type FieldContextValue } from './field-context';

export { useField } from './field-context';

interface FormFieldProps {
  label: string;
  /** Validation error from React Hook Form. */
  error?: string;
  hint?: ReactNode;
  required?: boolean;
  /** Hide the visible <label> but keep it for screen readers. */
  labelHidden?: boolean;
  /** Override the generated id (for controls that own their id). */
  id?: string;
  children: ReactNode;
  className?: string;
}

/**
 * Label + control + error + hint wired to React Hook Form with generated ids.
 * Errors use role="alert" (spec 3.6).
 */
export function FormField({
  label,
  error,
  hint,
  required,
  labelHidden,
  id: providedId,
  children,
  className,
}: FormFieldProps) {
  const generatedId = useId();
  const id = providedId ?? generatedId;
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const invalid = Boolean(error);

  const ctx: FieldContextValue = {
    id,
    invalid,
    describedBy:
      [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ') || undefined,
  };

  return (
    <FieldContext.Provider value={ctx}>
      <div className={cn('flex flex-col gap-1.5', className)}>
        <label
          htmlFor={id}
          className={cn(
            labelHidden ? 'sr-only' : 'text-small font-medium text-fg',
            'data-[required=true]:after:ml-1 data-[required=true]:after:text-crit',
          )}
          data-required={required || undefined}
        >
          {label}
          {required ? (
            <span aria-hidden="true" className="ml-1 text-crit">
              *
            </span>
          ) : null}
        </label>
        {children}
        {hint ? (
          <p id={hintId} className="text-small text-muted">
            {hint}
          </p>
        ) : null}
        {error ? (
          <p id={errorId} role="alert" className="text-small text-crit">
            {error}
          </p>
        ) : null}
      </div>
    </FieldContext.Provider>
  );
}
