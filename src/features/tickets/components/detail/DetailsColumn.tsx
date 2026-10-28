import type { ReactNode } from 'react';
import { diffMs, formatDuration } from '@/lib/format';
import { RelativeTime } from '@/components/common/RelativeTime';
import { cn } from '@/lib/cn';
import type { Department, Ticket } from '@/types/domain';

function DetailRow({
  label,
  children,
  muted,
}: {
  label: string;
  children: ReactNode;
  muted?: boolean;
}) {
  return (
    <div>
      <dt className="label-caps">{label}</dt>
      <dd className={cn('mt-0.5 text-body', muted ? 'text-muted' : 'text-fg')}>{children}</dd>
    </div>
  );
}

/**
 * Spec 9.6 details column (300px, stacks under 860px): requester, department,
 * category, owner, assignee, ETA, created, acknowledged (+ latency after
 * submit), escalation contact (staff only) and collaborators.
 */
export function DetailsColumn({
  ticket,
  department,
  isStaff,
}: {
  ticket: Ticket;
  department: Department | null;
  isStaff: boolean;
}) {
  const ackLatency = ticket.acknowledged_at
    ? formatDuration(diffMs(ticket.acknowledged_at, ticket.created_at))
    : null;

  return (
    <section className="card p-4">
      <h2 className="text-section-title text-fg">Details</h2>
      <dl className="mt-3 flex flex-col gap-3">
        <DetailRow label="Requester">
          <span className="block font-medium">{ticket.requester.name}</span>
          <span className="block text-small text-muted">{ticket.requester.email}</span>
        </DetailRow>
        <DetailRow label="Department">{department?.name ?? ticket.department_id}</DetailRow>
        <DetailRow label="Category">{ticket.category_name}</DetailRow>
        <DetailRow label="Owner" muted={!ticket.owner}>
          {ticket.owner?.name ?? 'Unassigned'}
        </DetailRow>
        <DetailRow label="Assignee" muted={!ticket.assignee}>
          {ticket.assignee?.name ?? 'Unassigned'}
        </DetailRow>
        <DetailRow label="ETA">
          <RelativeTime iso={ticket.eta} mode="absolute" />
        </DetailRow>
        <DetailRow label="Created">
          <RelativeTime iso={ticket.created_at} mode="absolute" />
        </DetailRow>
        <DetailRow label="Acknowledged">
          {ticket.acknowledged_at ? (
            <>
              <RelativeTime iso={ticket.acknowledged_at} mode="absolute" />
              {ackLatency ? (
                <span className="ml-1.5 text-small text-muted">{ackLatency} after submit</span>
              ) : null}
            </>
          ) : (
            <span className="text-muted">—</span>
          )}
        </DetailRow>
        {isStaff ? (
          <DetailRow label="Escalation contact" muted={!department?.escalation_primary}>
            {department?.escalation_primary?.name ?? 'Not set'}
          </DetailRow>
        ) : null}
        <DetailRow label="Collaborators" muted={ticket.collaborators.length === 0}>
          {ticket.collaborators.length > 0 ? (
            <ul className="flex flex-col gap-0.5">
              {ticket.collaborators.map((c) => (
                <li key={c.id}>{c.name}</li>
              ))}
            </ul>
          ) : (
            'None'
          )}
        </DetailRow>
      </dl>
    </section>
  );
}
