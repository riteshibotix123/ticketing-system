import { useId } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/cn';

interface NumberFieldProps {
  label: string;
  /** Result of react-hook-form `register(...)`. */
  field: UseFormRegisterReturn;
  min?: number;
  max?: number;
  hint?: string;
  error?: string;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

/** Numeric policy field: label + number input + optional hint/error (spec 9.13). */
export function NumberField({
  label,
  field,
  min = 1,
  max = 720,
  hint,
  error,
  placeholder,
  disabled,
  className,
}: NumberFieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <label htmlFor={id} className="label-caps text-muted">
        {label}
      </label>
      <Input
        {...field}
        id={id}
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        step={1}
        placeholder={placeholder}
        disabled={disabled}
        className="tabular"
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : hint ? hintId : undefined}
      />
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
