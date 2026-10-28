import { Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/cn';

/**
 * Search + selects, state synced to the URL query string (the parent owns
 * `useUrlFilters`). Renders a responsive, wrapping bar with a clear action.
 */
export function FilterBar({
  searchValue,
  onSearchChange,
  searchPlaceholder = 'Search…',
  searchLabel = 'Search',
  activeCount,
  onClear,
  children,
  right,
}: {
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  searchLabel?: string;
  activeCount: number;
  onClear: () => void;
  children?: React.ReactNode;
  right?: React.ReactNode;
}) {
  return (
    <div
      className="flex flex-wrap items-end gap-2"
      role="search"
      aria-label="Filters"
      data-testid="filter-bar"
    >
      <div className="relative min-w-[220px] flex-1">
        <label htmlFor="filter-search" className="sr-only">
          {searchLabel}
        </label>
        <Search
          className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
          aria-hidden="true"
        />
        <Input
          id="filter-search"
          type="search"
          value={searchValue}
          placeholder={searchPlaceholder}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-8"
        />
      </div>

      {children}

      {activeCount > 0 ? (
        <Button
          variant="ghost"
          size="sm"
          onClick={onClear}
          className={cn('text-muted')}
          aria-label="Clear filters"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
          Clear ({activeCount})
        </Button>
      ) : null}

      {right ? <div className="ml-auto flex items-center gap-2">{right}</div> : null}
    </div>
  );
}
