import { Clock } from 'lucide-react';
import { formatDateTime } from '@/lib/format';
import type { Ticket } from '@/types/domain';

/** Spec 9.6 card 3: reason and next review date while the ticket is on hold. */
export function HoldCard({ ticket }: { ticket: Ticket }) {
  if (ticket.status !== 'on_hold' || !ticket.hold) return null;

  return (
    <section className="card p-4">
      <h2 className="flex items-center gap-2 text-section-title text-fg">
        <Clock className="h-4 w-4 text-muted" aria-hidden="true" />
        On hold
      </h2>
      <p className="prose-body mt-2">{ticket.hold.reason}</p>
      <div className="mt-3">
        <p className="label-caps">Next review</p>
        <p className="mt-0.5 text-body text-fg">{formatDateTime(ticket.hold.review_date)}</p>
      </div>
    </section>
  );
}
