import { formatDateTime, formatDateTimeFull, formatRelative } from '@/lib/format';
import { cn } from '@/lib/cn';

/**
 * Relative time with the absolute Asia/Kolkata time in the tooltip.
 * `tooltip` shows full absolute time (spec 3.5).
 */
export function RelativeTime({
  iso,
  className,
  mode = 'relative',
}: {
  iso: string | null | undefined;
  className?: string;
  /** relative → "2 hours ago" with absolute tooltip; absolute → "26 Oct, 4:30 pm". */
  mode?: 'relative' | 'absolute';
}) {
  if (!iso) return <span className={cn('text-muted', className)}>—</span>;
  return (
    <time
      dateTime={iso}
      title={formatDateTimeFull(iso)}
      className={cn('whitespace-nowrap', className)}
    >
      {mode === 'relative' ? formatRelative(iso) : formatDateTime(iso)}
    </time>
  );
}
