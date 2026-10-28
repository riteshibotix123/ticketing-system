import { useId, type ReactNode } from 'react';
import { Select, SelectContent, SelectTrigger, SelectValue } from '@/components/ui/select';

interface SelectFieldProps {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  error?: string;
  hint?: ReactNode;
  required?: boolean;
  disabled?: boolean;
  children: ReactNode;
}

/**
 * Visible <label> bound to the Radix SelectTrigger + error (role="alert") +
 * hint. Mirrors FormField's markup: FormField generates its own internal id
 * which cannot be pointed at a SelectTrigger, so the label binding is done
 * here instead. React Hook Form wiring happens in the parent via Controller.
 */
export function SelectField({
  label,
  value,
  onValueChange,
  placeholder,
  error,
  hint,
  required,
  disabled,
  children,
}: SelectFieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy =
    [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-small font-medium text-fg">
        {label}
        {required ? (
          <span aria-hidden="true" className="ml-1 text-crit">
            *
          </span>
        ) : null}
      </label>
      <Select value={value} onValueChange={onValueChange} disabled={disabled}>
        <SelectTrigger
          id={id}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={describedBy}
        >
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>{children}</SelectContent>
      </Select>
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
  );
}
