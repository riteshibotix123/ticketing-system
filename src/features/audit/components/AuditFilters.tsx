import { FilterBar } from '@/components/common/FilterBar';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

export interface AuditActorOption {
  id: string;
  name: string;
}

/**
 * Audit filters (spec 9.14): text, actor, action, ticket ID, date range.
 * State lives in the URL — the parent owns `useUrlFilters`.
 */
export function AuditFilters({
  q,
  onQChange,
  actorId,
  onActorChange,
  actorOptions,
  action,
  onActionChange,
  ticketId,
  onTicketChange,
  from,
  onFromChange,
  to,
  onToChange,
  activeCount,
  onClear,
}: {
  q: string;
  onQChange: (value: string) => void;
  actorId: string;
  onActorChange: (value: string) => void;
  /** null → /users was refused; the actor filter is hidden. */
  actorOptions: AuditActorOption[] | null;
  action: string;
  onActionChange: (value: string) => void;
  ticketId: string;
  onTicketChange: (value: string) => void;
  from: string;
  onFromChange: (value: string) => void;
  to: string;
  onToChange: (value: string) => void;
  activeCount: number;
  onClear: () => void;
}) {
  return (
    <FilterBar
      searchValue={q}
      onSearchChange={onQChange}
      searchPlaceholder="Search audit text…"
      searchLabel="Search audit entries"
      activeCount={activeCount}
      onClear={onClear}
    >
      {actorOptions ? (
        <div className="flex flex-col gap-1">
          <span className="label-caps text-muted">Actor</span>
          <Select
            value={actorId || 'any'}
            onValueChange={(v) => onActorChange(v === 'any' ? '' : v)}
          >
            <SelectTrigger className="w-[180px]" aria-label="Actor">
              <SelectValue placeholder="Any actor" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Any actor</SelectItem>
              {actorOptions.map((actor) => (
                <SelectItem key={actor.id} value={actor.id}>
                  {actor.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : null}

      <div className="flex flex-col gap-1">
        <label htmlFor="audit-action" className="label-caps text-muted">
          Action
        </label>
        <Input
          id="audit-action"
          value={action}
          onChange={(e) => onActionChange(e.target.value)}
          placeholder="e.g. Escalation"
          className="w-[150px]"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="audit-ticket" className="label-caps text-muted">
          Ticket ID
        </label>
        <Input
          id="audit-ticket"
          value={ticketId}
          onChange={(e) => onTicketChange(e.target.value)}
          placeholder="IBX-…"
          className="w-[160px]"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="audit-from" className="label-caps text-muted">
          From
        </label>
        <Input
          id="audit-from"
          type="date"
          value={from}
          onChange={(e) => onFromChange(e.target.value)}
          className="w-[150px]"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="audit-to" className="label-caps text-muted">
          To
        </label>
        <Input
          id="audit-to"
          type="date"
          value={to}
          onChange={(e) => onToChange(e.target.value)}
          className="w-[150px]"
        />
      </div>
    </FilterBar>
  );
}
