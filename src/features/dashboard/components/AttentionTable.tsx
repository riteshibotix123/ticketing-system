import { useNavigate } from 'react-router-dom';
import { ConfidentialBadge } from '@/components/common/ConfidentialBadge';
import { PriorityBadge } from '@/components/common/PriorityBadge';
import { SlaIndicator } from '@/components/common/SlaIndicator';
import { StatusBadge } from '@/components/common/StatusBadge';
import { EmptyState } from '@/components/common/States';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { compareUrgency } from '@/lib/sla';
import type { Ticket } from '@/types/domain';

/**
 * "Needs attention" (spec 9.3): up to 6 tickets sorted by urgency (spec 11.4).
 * Rows are keyboard-activatable and open the ticket detail.
 */
export function AttentionTable({ tickets, isStaff }: { tickets: Ticket[]; isStaff: boolean }) {
  const navigate = useNavigate();
  const rows = [...tickets].sort(compareUrgency).slice(0, 6);

  if (rows.length === 0) {
    return <EmptyState title="Nothing open. You are all caught up." />;
  }

  function open(ticket: Ticket) {
    navigate(`/tickets/${ticket.id}`);
  }

  return (
    <section className="card scroll-thin overflow-x-auto" aria-labelledby="attention-heading">
      <div className="border-b border-line px-3 py-2.5">
        <h2 id="attention-heading" className="text-section-title text-fg">
          Needs attention
        </h2>
        <p className="text-small text-muted">Most urgent first</p>
      </div>
      <Table>
        <caption className="sr-only">
          Tickets needing attention, sorted by escalation level, priority and age
        </caption>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>ID</TableHead>
            <TableHead>Title</TableHead>
            <TableHead>Priority</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>SLA</TableHead>
            <TableHead>Assignee</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((t) => (
            <TableRow
              key={t.id}
              tabIndex={0}
              className="cursor-pointer"
              onClick={() => open(t)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  open(t);
                }
              }}
            >
              <TableCell>
                <span className="mono whitespace-nowrap text-small">{t.id}</span>
              </TableCell>
              <TableCell>
                <span className="flex flex-wrap items-center gap-1.5">
                  <span className="text-body text-fg">{t.title}</span>
                  {t.confidential ? <ConfidentialBadge /> : null}
                </span>
              </TableCell>
              <TableCell>
                <PriorityBadge priority={t.priority} />
              </TableCell>
              <TableCell>
                <StatusBadge status={t.status} />
              </TableCell>
              <TableCell>
                <SlaIndicator sla={t.sla} compact requesterView={!isStaff} />
              </TableCell>
              <TableCell>
                {t.assignee ? (
                  <span className="whitespace-nowrap text-body">{t.assignee.name}</span>
                ) : (
                  <span className="whitespace-nowrap text-body text-muted">Unassigned</span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  );
}
