import { useMemo, useState } from 'react';
import { Check, ChevronDown, Search } from 'lucide-react';
import { useField } from '@/components/common/FormField';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/cn';
import type { Department } from '@/types/domain';

/** Spec 9.5/10.3: a department needs an active Spoke before tickets can go to it. */
function disabledReason(dept: Department): string | null {
  if (!dept.active) return 'Inactive department';
  if (dept.spokes.length === 0) return 'No active Spoke yet';
  return null;
}

/**
 * Searchable department combobox: a trigger button plus a filterable listbox
 * inside a popover (Radix Select cannot host a text filter).
 */
export function DepartmentSelect({
  value,
  onChange,
  departments,
}: {
  value: string;
  onChange: (departmentId: string) => void;
  departments: Department[];
}) {
  const field = useField();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');

  const selected = departments.find((dept) => dept.id === value) ?? null;
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle
      ? departments.filter((dept) => dept.name.toLowerCase().includes(needle))
      : departments;
  }, [departments, query]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          id={field?.id}
          aria-haspopup="listbox"
          data-invalid={field?.invalid ? '' : undefined}
          aria-describedby={field?.describedBy}
          className={cn(
            'flex h-9 w-full items-center justify-between gap-2 rounded border border-line bg-surface px-3 text-left text-body',
            'data-[invalid]:border-crit data-[state=open]:bg-surface-2',
          )}
        >
          <span className={cn('truncate', selected ? 'text-fg' : 'text-muted/70')}>
            {selected?.name ?? 'Select a department'}
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
        </button>
      </PopoverTrigger>

      <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-2" align="start">
        <div className="relative">
          <label htmlFor="dept-filter" className="sr-only">
            Filter departments
          </label>
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
            aria-hidden="true"
          />
          <Input
            id="dept-filter"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type to filter…"
            className="pl-8"
          />
        </div>
        <ul
          role="listbox"
          aria-label="Departments"
          className="scroll-thin mt-2 max-h-[240px] overflow-auto"
        >
          {filtered.map((dept) => {
            const reason = disabledReason(dept);
            return (
              <li key={dept.id} role="presentation">
                <button
                  type="button"
                  role="option"
                  aria-selected={dept.id === value}
                  disabled={reason !== null}
                  onClick={() => {
                    onChange(dept.id);
                    setOpen(false);
                    setQuery('');
                  }}
                  className={cn(
                    'flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-left text-body text-fg',
                    'hover:bg-surface-2 disabled:pointer-events-none disabled:opacity-60 data-[selected=true]:bg-surface-2',
                  )}
                  data-selected={dept.id === value}
                >
                  <span className="inline-flex min-w-0 items-center gap-1.5">
                    {dept.id === value ? (
                      <Check className="h-3.5 w-3.5 shrink-0 text-accent" aria-hidden="true" />
                    ) : null}
                    <span className="truncate">{dept.name}</span>
                  </span>
                  {reason ? <span className="shrink-0 text-small text-muted">{reason}</span> : null}
                </button>
              </li>
            );
          })}
          {filtered.length === 0 ? (
            <li role="presentation" className="px-2 py-1.5 text-small text-muted">
              No departments match.
            </li>
          ) : null}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
