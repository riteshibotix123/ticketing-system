import type { ColumnDef, SortingState } from '@tanstack/react-table';
import { ConfidentialBadge } from '@/components/common/ConfidentialBadge';
import { CopyButton } from '@/components/common/CopyButton';
import { PriorityBadge } from '@/components/common/PriorityBadge';
import { RelativeTime } from '@/components/common/RelativeTime';
import { SlaIndicator } from '@/components/common/SlaIndicator';
import { StatusBadge } from '@/components/common/StatusBadge';
import type { Ticket } from '@/types/domain';

/** Spec 11.4 / R.9: the server's `urgency` order (escalation level, priority, oldest SLA start). */
export const DEFAULT_SORT = 'urgency';

/**
 * Column id -> server sort token per direction (contract R.9 whitelist). A direction the
 * server lacks falls back to the default order. Columns outside this map are not sortable.
 */
const SORT_TOKENS: Record<string, { asc?: string; desc?: string }> = {
  title: { asc: 'title' },
  priority: { asc: 'priority', desc: '-priority' },
  status: { asc: 'status' },
  created: { asc: 'created_at', desc: '-created_at' },
};

/** Parse the URL `sort` param into table sorting state. */
export function sortToSortingState(sort: string): SortingState {
  for (const [id, tokens] of Object.entries(SORT_TOKENS)) {
    if (tokens.asc === sort) return [{ id, desc: false }];
    if (tokens.desc === sort) return [{ id, desc: true }];
  }
  return [];
}

/** Write sorting state back to the URL as a single server sort token. */
export function sortingStateToSort(next: SortingState): string {
  const first = next[0];
  if (!first) return DEFAULT_SORT;
  const tokens = SORT_TOKENS[first.id];
  return (first.desc ? tokens?.desc : tokens?.asc) ?? DEFAULT_SORT;
}

export interface TicketColumnsOptions {
  currentUserId: string | null;
  /** Non-staff viewers only ever see the requester-safe SLA text (spec 11.3). */
  requesterView: boolean;
  departmentName: (departmentId: string) => string | undefined;
}

export function buildTicketColumns({
  currentUserId,
  requesterView,
  departmentName,
}: TicketColumnsOptions): ColumnDef<Ticket, unknown>[] {
  return [
    {
      id: 'id',
      header: 'ID',
      enableSorting: false,
      cell: ({ row }) => (
        <span className="inline-flex items-center gap-0.5">
          <span className="mono text-small">{row.original.id}</span>
          <CopyButton value={row.original.id} label="Copy ticket ID" />
        </span>
      ),
    },
    {
      id: 'title',
      header: 'Title',
      cell: ({ row }) => {
        const ticket = row.original;
        return (
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="text-fg">{ticket.title}</span>
            {ticket.confidential ? <ConfidentialBadge /> : null}
            {currentUserId && ticket.requester.id !== currentUserId ? (
              <span className="whitespace-nowrap text-small text-muted">
                {ticket.requester.name}
              </span>
            ) : null}
          </span>
        );
      },
    },
    {
      id: 'department',
      header: 'Department',
      enableSorting: false,
      cell: ({ row }) => departmentName(row.original.department_id) ?? '—',
    },
    {
      id: 'priority',
      header: 'Priority',
      cell: ({ row }) => <PriorityBadge priority={row.original.priority} />,
    },
    {
      id: 'status',
      header: 'Status',
      cell: ({ row }) => <StatusBadge status={row.original.status} />,
    },
    {
      id: 'assignee',
      header: 'Owner/Assignee',
      enableSorting: false,
      cell: ({ row }) =>
        row.original.assignee?.name ??
        row.original.owner?.name ?? <span className="text-muted">Unassigned</span>,
    },
    {
      id: 'sla',
      header: 'SLA',
      enableSorting: false,
      cell: ({ row }) => (
        <SlaIndicator sla={row.original.sla} requesterView={requesterView} compact />
      ),
    },
    {
      id: 'created',
      header: 'Created',
      cell: ({ row }) => <RelativeTime iso={row.original.created_at} />,
    },
  ];
}
