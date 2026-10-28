import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import { ticketsApi, type TicketScope } from '@/api/endpoints/tickets';
import { useDebounce } from '@/hooks/useDebounce';
import { usePermissions } from '@/hooks/usePermissions';
import { Input } from '@/components/ui/input';

/**
 * Global ticket search (spec 9.2): Enter opens the first result when there is
 * one, otherwise the ticket list with the query — which lives in the URL.
 */
export function GlobalSearch() {
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const debounced = useDebounce(value, 300);
  const navigate = useNavigate();
  const { can } = usePermissions();

  const scope: TicketScope = can('tickets.view_all')
    ? 'all'
    : can('tickets.view_department')
      ? 'queue'
      : 'mine';

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const q = debounced.trim();
    if (!q) return;
    setBusy(true);
    ticketsApi
      .list({ scope, q, page: 1, page_size: 5 })
      .then((res) => {
        const first = res.items[0];
        const upper = q.toUpperCase();
        if (first && (first.id.toUpperCase() === upper || res.items.length === 1)) {
          navigate(`/tickets/${first.id}`);
        } else {
          navigate(`/tickets?q=${encodeURIComponent(q)}`);
        }
      })
      .catch(() => {
        // Never leak a search failure; fall through to the list view.
        navigate(`/tickets?q=${encodeURIComponent(q)}`);
      })
      .finally(() => setBusy(false));
  }

  return (
    <form
      onSubmit={onSubmit}
      role="search"
      aria-label="Search tickets"
      className="min-w-0 flex-1 sm:max-w-[420px]"
    >
      <label htmlFor="global-search" className="sr-only">
        Search tickets by ID or title
      </label>
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
          aria-hidden="true"
        />
        <Input
          id="global-search"
          type="search"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={busy ? 'Searching…' : 'Search tickets by ID or title…'}
          className="h-8 pl-8"
          autoComplete="off"
        />
      </div>
    </form>
  );
}
