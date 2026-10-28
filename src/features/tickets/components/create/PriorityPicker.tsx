import { useId } from 'react';
import { PRIORITY_LABEL, PRIORITY_MEANING, PRIORITY_ORDER } from '@/lib/constants';
import { cn } from '@/lib/cn';
import type { Priority } from '@/types/domain';

/**
 * Radio-style priority cards (spec 9.5): each option shows its exact meaning
 * text from spec 11.1; "The team confirms priority." is shown once below.
 */
export function PriorityPicker({
  value,
  onChange,
}: {
  value: Priority;
  onChange: (priority: Priority) => void;
}) {
  const name = useId();

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="sr-only">Priority</legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {PRIORITY_ORDER.map((priority) => (
          <label
            key={priority}
            className={cn(
              'flex cursor-pointer flex-wrap items-start gap-x-2.5 gap-y-1 rounded border p-3 transition-colors',
              value === priority
                ? 'border-accent bg-surface-2'
                : 'border-line bg-surface hover:bg-surface-2',
            )}
          >
            <input
              type="radio"
              name={name}
              value={priority}
              checked={value === priority}
              onChange={() => onChange(priority)}
              className="mt-0.5 h-4 w-4 shrink-0"
            />
            <span className="text-body font-medium text-fg">{PRIORITY_LABEL[priority]}</span>
            <span className="basis-full pl-6 text-small text-muted">
              {PRIORITY_MEANING[priority]}
            </span>
          </label>
        ))}
      </div>
      <p className="text-small text-muted">The team confirms priority.</p>
    </fieldset>
  );
}
