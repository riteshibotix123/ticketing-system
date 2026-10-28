import type { ColumnDef, SortingState } from '@tanstack/react-table';
import { ConfidentialBadge } from '@/components/common/ConfidentialBadge';
import { CopyButton } from '@/components/common/CopyButton';
import { PriorityBadge } from '@/components/common/PriorityBadge';
import { RelativeTime } from '@/components/common/RelativeTime';
import { SlaIndicator } from '@/components/common/SlaIndicator';
import { StatusBadge } from '@/components/common/StatusBadge';
import type { Ticket } from '@/types/domain';

/** Spec 11.4: escalation level desc, priority desc, oldest SLA start first. */
export const DEFAULT_SORT = 'escalation_level:desc,priority:desc,sla_started_at:asc';

/** Column id -> server sort field. Columns outside this map are not sortable. */
const SORT_FIELD: Record<string, string> = {
  id: 'id',
  title: 'title',
  priority: 'priority',
  status: 'status',
  sla: 'sla_started_at',
  created: 'created_at',
};

/** Parse the URL `sort` param (first term only; server sorts by a single field). */
export function sortToSortingState(sort: string): SortingState {
  const [first] = sort.split(',');
  if (!first) return [];
  const [field, dir] = first.split(':');
  const columnId = Object.entries(SORT_FIELD).find(([, f]) => f === field)?.[0];
  if (!columnId) return [];
  return [{ id: columnId, desc: dir !== 'asc' }];
}

/** Write sorting state back to the URL, toggling `column:asc|desc` for that column only. */
export function sortingStateToSort(next: SortingState): string {
  const first = next[0];
  if (!first) return DEFAULT_SORT;
  const field = SORT_FIELD[first.id];
  return field ? `${field}:${first.desc ? 'desc' : 'asc'}` : DEFAULT_SORT;
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
