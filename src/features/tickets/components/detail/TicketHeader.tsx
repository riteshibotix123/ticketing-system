import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { ConfidentialBadge } from '@/components/common/ConfidentialBadge';
import { CopyButton } from '@/components/common/CopyButton';
import { PriorityBadge } from '@/components/common/PriorityBadge';
import { StatusBadge } from '@/components/common/StatusBadge';
import type { Ticket } from '@/types/domain';

/** Spec 9.6 header: back link, mono ID + copy, title, badges (status, priority, confidential, reopened). */
export function TicketHeader({ ticket }: { ticket: Ticket }) {
  return (
    <header className="card p-4">
      <Link
        to="/tickets"
        className="inline-flex items-center gap-1 text-small text-muted hover:text-fg"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        Back to tickets
      </Link>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        <span className="mono text-small text-muted">{ticket.id}</span>
        <CopyButton value={ticket.id} label="Copy ticket ID" />
      </div>
      <div className="mt-1 flex flex-wrap items-start justify-between gap-2">
        <h1 className="min-w-0 text-page-title text-fg">{ticket.title}</h1>
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge status={ticket.status} />
          <PriorityBadge priority={ticket.priority} />
          {ticket.confidential ? <ConfidentialBadge /> : null}
          {ticket.reopen_count > 0 ? (
            <Badge variant="warn">{`Reopened ${ticket.reopen_count}×`}</Badge>
          ) : null}
        </div>
      </div>
    </header>
  );
}
