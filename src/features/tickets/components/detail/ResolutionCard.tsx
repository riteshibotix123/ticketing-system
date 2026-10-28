import { Info } from 'lucide-react';
import type { Ticket } from '@/types/domain';

/**
 * Spec 9.6 card 2: shown when resolved or closed. For the requester while
 * Resolved, prompt to confirm closure or reopen.
 */
export function ResolutionCard({ ticket, isRequester }: { ticket: Ticket; isRequester: boolean }) {
  if (ticket.status !== 'resolved' && ticket.status !== 'closed') return null;

  return (
    <section className="card p-4">
      <h2 className="text-section-title text-fg">Resolution summary</h2>
      <p className="prose-body mt-2">
        {ticket.resolution_summary ?? 'No resolution summary was provided.'}
      </p>
      {isRequester && ticket.status === 'resolved' ? (
        <p className="border-info/40 mt-3 flex items-start gap-2 rounded-md border bg-info-soft px-3 py-2 text-small text-info">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          Confirm closure if it is fixed, or reopen with a reason.
        </p>
      ) : null}
    </section>
  );
}
