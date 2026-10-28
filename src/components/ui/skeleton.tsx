import { cn } from '@/lib/cn';

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('skeleton', className)} {...props} />;
}

/** Skeleton shaped like table rows (spec 13: no spinners over blank pages). */
export function SkeletonTable({ rows = 8, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div className="card overflow-hidden" aria-hidden="true">
      <div className="flex gap-3 border-b border-line bg-surface-2 px-3 py-2.5">
        {Array.from({ length: columns }).map((_, i) => (
          <Skeleton key={i} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div
          key={r}
          className="flex items-center gap-3 border-b border-line px-3 py-3 last:border-b-0"
        >
          {Array.from({ length: columns }).map((_, c) => (
            <Skeleton key={c} className="h-3.5 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

/** Skeleton shaped like KPI tiles. */
export function SkeletonTiles({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-hidden="true">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="card p-4">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-3 h-7 w-14" />
          <Skeleton className="mt-2 h-3 w-32" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="card p-4" aria-hidden="true">
      <Skeleton className="h-4 w-40" />
      <div className="mt-3 space-y-2">
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} className="h-3 w-full" />
        ))}
      </div>
    </div>
  );
}

/** Full-page skeleton shown while `/auth/me` loads on app start (spec 7). */
export function FullPageSkeleton() {
  return (
    <div className="min-h-dvh bg-bg" role="status" aria-label="Loading">
      <div className="flex min-h-dvh">
        <div className="hidden w-[236px] shrink-0 border-r border-line bg-surface p-4 md:block">
          <Skeleton className="h-6 w-32" />
          <div className="mt-6 space-y-3">
            {Array.from({ length: 7 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        </div>
        <div className="flex-1 p-6">
          <Skeleton className="h-9 w-full" />
          <div className="mt-6 space-y-4">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        </div>
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  );
}
