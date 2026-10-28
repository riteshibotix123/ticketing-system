import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { cn } from '@/lib/cn';

/** Standard page header: title, optional description/back link, action buttons. */
export function PageHeader({
  title,
  description,
  backTo,
  backLabel = 'Back',
  actions,
  badge,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  backTo?: string;
  backLabel?: string;
  actions?: React.ReactNode;
  badge?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('mb-4 flex flex-wrap items-start justify-between gap-3', className)}>
      <div className="min-w-0">
        {backTo ? (
          <Link
            to={backTo}
            className="mb-1 inline-flex items-center gap-1 text-small text-muted hover:text-fg"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            {backLabel}
          </Link>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-page-title text-fg">{title}</h1>
          {badge}
        </div>
        {description ? (
          <p className="mt-1 max-w-[65ch] text-small text-muted">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
