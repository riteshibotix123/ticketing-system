import type { TicketStatus } from '@/types/domain';
import { STATUS_LABEL } from '@/lib/constants';
import { cn } from '@/lib/cn';

/** Outlined pill. Resolved=ok, Reopened=warn, Awaiting/On Hold=info, Closed/Cancelled=muted. */
const TONE: Record<TicketStatus, string> = {
  new: 'border-accent/50 text-accent',
  acknowledged: 'border-info/50 text-info',
  assigned: 'border-info/50 text-info',
  in_progress: 'border-info/50 text-info',
  awaiting_requester: 'border-info/50 text-info',
  on_hold: 'border-info/50 text-info',
  resolved: 'border-ok/50 text-ok',
  reopened: 'border-warn/50 text-warn',
  closed: 'border-line text-muted',
  cancelled: 'border-line text-muted',
};

const ICON: Record<TicketStatus, string> = {
  new: '•',
  acknowledged: '✓',
  assigned: '→',
  in_progress: '◐',
  awaiting_requester: '◐',
  on_hold: '◷',
  resolved: '✓',
  reopened: '↻',
  closed: '■',
  cancelled: '×',
};

export function StatusBadge({
  status,
  className,
  showIcon = true,
}: {
  status: TicketStatus;
  className?: string;
  showIcon?: boolean;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full border bg-surface px-2 py-0.5 text-small font-medium',
        TONE[status],
        className,
      )}
    >
      {showIcon ? (
        <span aria-hidden="true" className="font-mono text-[11px] leading-none">
          {ICON[status]}
        </span>
      ) : null}
      {STATUS_LABEL[status]}
    </span>
  );
}
