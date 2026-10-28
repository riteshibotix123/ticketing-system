import * as React from 'react';
import * as CheckboxPrimitive from '@radix-ui/react-checkbox';
import { Check } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useField } from '@/components/common/field-context';

export const Checkbox = React.forwardRef<
  React.ElementRef<typeof CheckboxPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>
>(
  (
    { className, id, 'aria-invalid': ariaInvalid, 'aria-describedby': ariaDescribedBy, ...props },
    ref,
  ) => {
    const field = useField();
    return (
      <CheckboxPrimitive.Root
        {...props}
        ref={ref}
        id={id ?? field?.id}
        aria-invalid={ariaInvalid ?? (field ? field.invalid : undefined)}
        aria-describedby={ariaDescribedBy ?? field?.describedBy}
        className={cn(
          'peer h-4 w-4 shrink-0 rounded-[3px] border border-line bg-surface data-[state=checked]:border-accent data-[state=checked]:bg-accent data-[state=checked]:text-accent-fg',
          'disabled:cursor-not-allowed disabled:opacity-60',
          className,
        )}
      >
        <CheckboxPrimitive.Indicator className="flex items-center justify-center text-current">
          <Check className="h-3 w-3" strokeWidth={3} aria-hidden="true" />
        </CheckboxPrimitive.Indicator>
      </CheckboxPrimitive.Root>
    );
  },
);
Checkbox.displayName = 'Checkbox';
