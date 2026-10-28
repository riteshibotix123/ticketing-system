import { forwardRef, useState, type InputHTMLAttributes } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { cn } from '@/lib/cn';
import { Input } from '@/components/ui/input';
import { useField } from '@/components/common/FormField';

/**
 * Password field with a show/hide toggle (spec 9.1). The toggle always has an
 * aria-label; the visible <label> and error wiring come from the surrounding
 * FormField through its context (useField).
 */
export const PasswordInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => {
    const [visible, setVisible] = useState(false);
    const field = useField();

    return (
      <div className="relative">
        <Input
          {...props}
          ref={ref}
          type={visible ? 'text' : 'password'}
          id={props.id ?? field?.id}
          aria-invalid={props['aria-invalid'] ?? field?.invalid ?? undefined}
          aria-describedby={props['aria-describedby'] ?? field?.describedBy}
          className={cn('pr-10', className)}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? 'Hide password' : 'Show password'}
          className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1.5 text-muted hover:bg-surface-2 hover:text-fg"
        >
          {visible ? (
            <EyeOff className="h-4 w-4" aria-hidden="true" />
          ) : (
            <Eye className="h-4 w-4" aria-hidden="true" />
          )}
        </button>
      </div>
    );
  },
);
PasswordInput.displayName = 'PasswordInput';
