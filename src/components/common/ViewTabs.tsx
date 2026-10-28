import { useRef, type KeyboardEvent, type ReactNode } from 'react';
import { cn } from '@/lib/cn';

export interface ViewTabItem {
  id: string;
  label: ReactNode;
}

/**
 * View switcher used where a tab strip filters one page region instead of
 * owning a tab panel (dashboard views, ticket scopes, notification filters).
 *
 * Deliberately a hand-rolled `tablist` rather than Radix Tabs: Radix always
 * points `aria-controls` at a `tabpanel` id, and these strips render no panel,
 * which axe flags (aria-valid-attr-value). `aria-controls` is optional for
 * tabs, so omitting it keeps the roles, keyboard model and styling while the
 * region below stays a normal landmark.
 */
export function ViewTabs({
  items,
  value,
  onChange,
  label,
  className,
}: {
  items: ViewTabItem[];
  value: string;
  onChange: (id: string) => void;
  label: string;
  className?: string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % items.length;
    else if (event.key === 'ArrowLeft') next = (index - 1 + items.length) % items.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = items.length - 1;
    else return;

    event.preventDefault();
    const item = items[next];
    onChange(item.id);
    refs.current[item.id]?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label={label}
      className={cn('flex flex-wrap items-center gap-1 border-b border-line', className)}
    >
      {items.map((item, index) => {
        const active = item.id === value;
        return (
          <button
            key={item.id}
            ref={(node) => {
              refs.current[item.id] = node;
            }}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(item.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={cn(
              'relative -mb-px inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-body transition-colors',
              active
                ? 'border-accent font-medium text-fg'
                : 'border-transparent text-muted hover:text-fg',
            )}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
