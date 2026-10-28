import type { ColumnDef } from '@tanstack/react-table';
import { AlertTriangle, Cog } from 'lucide-react';
import { Link } from 'react-router-dom';
import { RelativeTime } from '@/components/common/RelativeTime';
import { Badge } from '@/components/ui/badge';
import type { AuditEntry } from '@/types/domain';

function isEscalation(action: string): boolean {
  return action.toLowerCase().includes('escalation');
}

function isTicketId(objectId: string | null): objectId is string {
  return objectId !== null && /^IBX-/i.test(objectId);
}

/**
 * Audit log columns (spec 9.14): When, Actor, Action (escalations get a red
 * pill — always with text), Ticket link, Detail. Read-only by design.
 */
export const auditColumns: ColumnDef<AuditEntry, unknown>[] = [
  {
    id: 'when',
    accessorFn: (row) => row.at,
    header: 'When',
    cell: ({ row }) => (
      <RelativeTime iso={row.original.at} mode="absolute" className="text-small" />
    ),
  },
  {
    id: 'actor',
    accessorFn: (row) => row.actor.name,
    header: 'Actor',
    cell: ({ row }) => {
      const { actor } = row.original;
      if (actor.id === 'system') {
        return (
          <span className="inline-flex items-center gap-1 text-muted">
            <Cog className="h-3.5 w-3.5" aria-hidden="true" />
            System
          </span>
        );
      }
      return <span className="text-fg">{actor.name}</span>;
    },
  },
  {
    id: 'action',
    accessorFn: (row) => row.action,
    header: 'Action',
    cell: ({ row }) => {
      const { action } = row.original;
      if (!isEscalation(action)) return <span className="text-fg">{action}</span>;
      return (
        <span className="inline-flex flex-wrap items-center gap-1.5">
          <Badge variant="crit">
            <AlertTriangle className="h-3 w-3" aria-hidden="true" />
            Escalation
          </Badge>
          <span className="text-fg">{action}</span>
        </span>
      );
    },
  },
  {
    id: 'ticket',
    accessorFn: (row) => row.object_id ?? '',
    header: 'Ticket',
    cell: ({ row }) => {
      const { object_id: objectId, object_type: objectType } = row.original;
      if (objectType === 'ticket' && isTicketId(objectId)) {
        return (
          <Link
            to={`/tickets/${objectId}`}
            className="mono text-small text-accent underline-offset-4 hover:underline"
          >
            {objectId}
          </Link>
        );
      }
      return <span className="mono text-small text-muted">{objectId || '—'}</span>;
    },
  },
  {
    id: 'detail',
    accessorFn: (row) => row.reason ?? row.detail ?? '',
    header: 'Detail',
    cell: ({ row }) => {
      const text = row.original.reason ?? row.original.detail ?? '';
      if (!text) return <span className="text-muted">—</span>;
      return (
        <span title={text} className="block max-w-[360px] truncate text-small text-muted">
          {text}
        </span>
      );
    },
  },
];
