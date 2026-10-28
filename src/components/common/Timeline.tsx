import { Settings2 } from 'lucide-react';
import { initials } from '@/lib/format';
import type { TimelineEvent } from '@/types/domain';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/common/States';
import { RelativeTime } from '@/components/common/RelativeTime';

export interface TimelineProps {
  events: TimelineEvent[];
  isRequester: boolean;
  headerText?: string;
}

/** Spec 9.8: requesters only ever see public events, never internal notes. */
function visibleEvents(events: TimelineEvent[], isRequester: boolean): TimelineEvent[] {
  const filtered = isRequester
    ? events.filter((e) => e.public && e.type !== 'internal_note')
    : events;
  return [...filtered].sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
}

function Avatar({ children, dashed }: { children: React.ReactNode; dashed?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={
        dashed
          ? 'flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-dashed border-line bg-surface-2 text-muted'
          : 'flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line bg-surface-2 text-small font-medium text-muted'
      }
    >
      {children}
    </span>
  );
}

function CommentRow({ event, internal }: { event: TimelineEvent; internal: boolean }) {
  const body = (
    <>
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-body font-medium text-fg">{event.actor.name}</span>
        <RelativeTime iso={event.at} className="text-small text-muted" />
      </div>
      <p className="mt-1 whitespace-pre-wrap break-words text-body text-fg">{event.body}</p>
    </>
  );

  if (internal) {
    return (
      <li className="flex gap-3">
        <Avatar dashed>
          <span className="text-small font-medium">{initials(event.actor.name)}</span>
        </Avatar>
        <div className="border-warn/40 min-w-0 flex-1 rounded-md border border-dashed bg-note px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warn">Internal note</Badge>
            <span className="text-small font-medium text-fg">{event.actor.name}</span>
            <RelativeTime iso={event.at} className="text-small text-muted" />
          </div>
          <p className="mt-1 whitespace-pre-wrap break-words text-body text-fg">{event.body}</p>
        </div>
      </li>
    );
  }

  return (
    <li className="flex gap-3">
      <Avatar>
        <span>{initials(event.actor.name)}</span>
      </Avatar>
      <div className="min-w-0 flex-1">{body}</div>
    </li>
  );
}

function AuditRow({ event }: { event: TimelineEvent }) {
  const line = event.detail ? `${event.action ?? 'Update'}: ${event.detail}` : (event.action ?? '');
  return (
    <li className="flex gap-3">
      <Avatar dashed>
        <Settings2 className="h-3.5 w-3.5" />
      </Avatar>
      <div className="min-w-0 flex-1 pt-1.5">
        {line ? <p className="text-small text-muted">{line}</p> : null}
        <RelativeTime iso={event.at} className="mt-0.5 block text-small text-muted" />
      </div>
    </li>
  );
}

function TimelineRow({ event, isRequester }: { event: TimelineEvent; isRequester: boolean }) {
  if (event.type === 'comment') return <CommentRow event={event} internal={false} />;
  if (event.type === 'internal_note') {
    return isRequester ? null : <CommentRow event={event} internal />;
  }
  return <AuditRow event={event} />;
}

/**
 * Spec 9.8 merged chronological timeline: comments, internal notes (staff only)
 * and system/audit events, ascending by time. Never colour alone — every kind
 * is distinguished by shape, badge or icon as well.
 */
export function Timeline({ events, isRequester, headerText }: TimelineProps) {
  const text =
    headerText ??
    (isRequester ? 'Visible updates only' : 'Includes internal notes and escalations');
  const items = visibleEvents(events, isRequester);

  return (
    <div className="mt-1">
      <p className="text-small text-muted">{text}</p>
      {items.length === 0 ? (
        <EmptyState
          title="No updates yet."
          description="Comments and status changes will appear here."
        />
      ) : (
        <ol className="mt-3 flex flex-col gap-3">
          {items.map((event) => (
            <TimelineRow key={event.id} event={event} isRequester={isRequester} />
          ))}
        </ol>
      )}
    </div>
  );
}
