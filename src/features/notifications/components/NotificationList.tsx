import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { RelativeTime } from '@/components/common/RelativeTime';
import { EmptyState, ErrorState } from '@/components/common/States';
import type { Notification } from '@/types/domain';

export interface NotificationListProps {
  items: Notification[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onOpen: (notification: Notification) => void;
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

function SkeletonRows() {
  return (
    <div className="card divide-y divide-line" aria-hidden="true">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="px-3 py-3">
          <Skeleton className="h-3.5 w-3/4" />
          <Skeleton className="mt-2 h-3 w-24" />
        </div>
      ))}
    </div>
  );
}

/** Notification list, newest first, unread bold, escalation pill (spec 9.10/12). */
export function NotificationList({
  items,
  loading,
  error,
  onRetry,
  onOpen,
  page,
  pageSize,
  total,
  onPageChange,
}: NotificationListProps) {
  if (loading && items.length === 0) return <SkeletonRows />;
  if (error) return <ErrorState message={error} onRetry={onRetry} />;
  if (items.length === 0)
    return <EmptyState title="Nothing new." description="You are all caught up." />;

  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);

  return (
    <div className="flex flex-col gap-2">
      <ul className="card divide-y divide-line">
        {items.map((n) => (
          <li key={n.id}>
            <button
              type="button"
              onClick={() => onOpen(n)}
              className="hover:bg-surface-2/70 flex w-full items-start gap-2 px-3 py-2.5 text-left transition-colors"
            >
              <span className="min-w-0 flex-1">
                <span
                  className={n.read ? 'text-body text-muted' : 'text-body font-semibold text-fg'}
                >
                  {!n.read ? <span className="sr-only">Unread. </span> : null}
                  {n.text}
                </span>
                <span className="mt-0.5 block text-small text-muted">
                  <RelativeTime iso={n.created_at} />
                </span>
              </span>
              {n.critical ? (
                <Badge variant="crit" className="shrink-0">
                  Escalation
                </Badge>
              ) : null}
            </button>
          </li>
        ))}
      </ul>

      {total > pageSize ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="tabular text-small text-muted" aria-live="polite">
            {from}–{to} of {total}
          </p>
          <div className="flex items-center gap-1">
            <Button
              variant="secondary"
              size="iconSm"
              onClick={() => onPageChange(page - 1)}
              disabled={page <= 1}
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            </Button>
            <span className="tabular px-2 text-small text-muted">Page {page}</span>
            <Button
              variant="secondary"
              size="iconSm"
              onClick={() => onPageChange(page + 1)}
              disabled={to >= total}
              aria-label="Next page"
            >
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
