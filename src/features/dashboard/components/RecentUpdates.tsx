import { Cog, MessageSquare, StickyNote } from 'lucide-react';
import { RelativeTime } from '@/components/common/RelativeTime';
import { EmptyState } from '@/components/common/States';
import { cn } from '@/lib/cn';
import type { TimelineEvent } from '@/types/domain';

const TYPE_META = {
  comment: { icon: MessageSquare, tone: 'text-info', label: 'Comment' },
  internal_note: { icon: StickyNote, tone: 'text-warn', label: 'Internal note' },
  audit: { icon: Cog, tone: 'text-muted', label: 'System update' },
} as const;

/** One readable line for an event: "action: detail", falling back to the comment body. */
function eventText(event: TimelineEvent): string {
  if (event.action && event.detail) return `${event.action}: ${event.detail}`;
  return event.action ?? event.detail ?? event.body ?? '';
}

function eventIconClass(type: TimelineEvent['type']): string {
  if (type === 'internal_note') return 'border-warn/40 bg-warn-soft';
  if (type === 'comment') return 'border-info/40 bg-info-soft';
  return 'border-line bg-surface-2';
}

/**
 * Employee dashboard: recent updates on the viewer's tickets (spec 9.3).
 * Staff-only events are already filtered server-side (spec 9.8/12).
 */
export function RecentUpdates({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) {
    return <EmptyState title="No recent updates." />;
  }

  return (
    <section className="card p-4" aria-labelledby="recent-updates-title">
      <h2 id="recent-updates-title" className="text-section-title text-fg">
        Recent updates
      </h2>
      <ul className="mt-3 divide-y divide-line">
        {events.map((event) => {
          const meta = TYPE_META[event.type];
          const Icon = meta.icon;
          const text = eventText(event);
          return (
            <li key={event.id} className="flex items-start gap-2.5 py-2.5 first:pt-0 last:pb-0">
              <span
                className={cn(
                  'mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border',
                  eventIconClass(event.type),
                )}
                aria-hidden="true"
              >
                <Icon className={cn('h-3.5 w-3.5', meta.tone)} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-body font-medium text-fg">{event.actor.name}</span>
                  <span className="text-small text-muted">
                    <RelativeTime iso={event.at} />
                  </span>
                </span>
                {text ? <span className="mt-0.5 block text-body text-muted">{text}</span> : null}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
