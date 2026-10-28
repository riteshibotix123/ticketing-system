import type { Priority } from '@/types/domain';
import { PRIORITY_LABEL } from '@/lib/constants';
import { cn } from '@/lib/cn';

const TONE: Record<Priority, string> = {
  low: 'border-line bg-surface-2 text-muted',
  medium: 'border-info/40 bg-info-soft text-info',
  high: 'border-warn/40 bg-warn-soft text-warn',
  critical: 'border-crit/40 bg-crit-soft text-crit',
};

const ICON: Record<Priority, string> = {
  low: '↓',
  medium: '→',
  high: '↑',
  critical: '!',
};

/**
 * Priority pill: colour AND text AND icon (never colour alone, spec 3.1).
 * Low=muted, Medium=info, High=warn, Critical=crit.
 */
export function PriorityBadge({
  priority,
  className,
  showIcon = true,
}: {
  priority: Priority;
  className?: string;
  showIcon?: boolean;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-small font-medium',
        TONE[priority],
        className,
      )}
    >
      {showIcon ? (
        <span aria-hidden="true" className="font-mono text-[11px] leading-none">
          {ICON[priority]}
        </span>
      ) : null}
      {PRIORITY_LABEL[priority]}
    </span>
  );
}
