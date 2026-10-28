import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Search } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/cn';
import type { UserRef } from '@/types/domain';

/** Merge current selections into an option list without duplicates. */
export function mergeUserOptions(
  base: UserRef[],
  extras: (UserRef | null | undefined)[],
): UserRef[] {
  const byId = new Map<string, UserRef>();
  for (const user of [...base, ...extras]) {
    if (user && !byId.has(user.id)) byId.set(user.id, user);
  }
  return [...byId.values()];
}

interface UserSelectProps {
  value: string | null;
  onChange: (userId: string | null) => void;
  options: UserRef[];
  /** aria-label for the trigger button. */
  label: string;
  placeholder?: string;
  disabled?: boolean;
  /** Offer a "Clear selection" action (→ onChange(null)). */
  allowClear?: boolean;
  className?: string;
}

/**
 * Select over a searchable, filtered list of users (spec 9.13: searchable
 * selects for Spokes and escalation contacts). Trigger matches SelectTrigger
 * styling; the popover contains a text filter.
 */
export function UserSelect({
  value,
  onChange,
  options,
  label,
  placeholder = 'Anyone',
  disabled,
  allowClear,
  className,
}: UserSelectProps) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus the filter when the popover opens (no autoFocus — jsx-a11y).
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const selected = options.find((o) => o.id === value) ?? null;

  const filtered = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return options;
    return options.filter(
      (o) => o.name.toLowerCase().includes(needle) || o.email.toLowerCase().includes(needle),
    );
  }, [options, filter]);

  const pick = (userId: string | null) => {
    onChange(userId);
    setOpen(false);
    setFilter('');
  };

  return (
    <Popover
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) setFilter('');
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className={cn(
            'flex h-9 w-full items-center justify-between gap-2 rounded border border-line bg-surface px-3 text-body text-fg',
            'hover:bg-surface-2 disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted',
            className,
          )}
        >
          <span className="sr-only">{label}</span>
          <span className={cn('truncate text-left', !selected && 'text-muted/70')}>
            {selected ? selected.name : placeholder}
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-2" align="start">
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted"
            aria-hidden="true"
          />
          <Input
            ref={inputRef}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter people…"
            aria-label={`Filter people for ${label}`}
            className="h-8 pl-7"
          />
        </div>
        <ul className="scroll-thin mt-2 max-h-56 overflow-y-auto">
          {filtered.length === 0 ? (
            <li className="px-2 py-3 text-small text-muted">No people match.</li>
          ) : null}
          {filtered.map((option) => (
            <li key={option.id}>
              <button
                type="button"
                onClick={() => pick(option.id)}
                className="flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-left hover:bg-surface-2"
              >
                <span className="min-w-0">
                  <span className="block truncate text-body text-fg">{option.name}</span>
                  <span className="block truncate text-small text-muted">{option.email}</span>
                </span>
                {option.id === value ? (
                  <Check className="h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
                ) : null}
              </button>
            </li>
          ))}
        </ul>
        {allowClear && selected ? (
          <button
            type="button"
            onClick={() => pick(null)}
            className="mt-1 w-full rounded-sm px-2 py-1.5 text-left text-small text-muted hover:bg-surface-2 hover:text-fg"
          >
            Clear selection
          </button>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
