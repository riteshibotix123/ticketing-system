import { ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/cn';

/** Muted pill "Confidential". */
export function ConfidentialBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-line bg-surface-2 px-2 py-0.5 text-small font-medium text-muted',
        className,
      )}
    >
      <ShieldAlert className="h-3 w-3" aria-hidden="true" />
      Confidential
    </span>
  );
}
