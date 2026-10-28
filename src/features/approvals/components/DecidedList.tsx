import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Check, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { SkeletonTable } from '@/components/ui/skeleton';
import { EmptyState, ErrorState } from '@/components/common/States';
import { RelativeTime } from '@/components/common/RelativeTime';
import { errorMessage, isApiError } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import { usersApi } from '@/api/endpoints/users';
import type { SignupRequest } from '@/types/domain';

type Outcome = 'approved' | 'rejected';

const OUTCOME_META: Record<Outcome, { label: string; variant: 'ok' | 'crit'; Icon: typeof Check }> =
  {
    approved: { label: 'Approved', variant: 'ok', Icon: Check },
    rejected: { label: 'Rejected', variant: 'crit', Icon: X },
  };

function decidedAt(request: SignupRequest): number {
  return new Date(request.decided_at ?? request.created_at).getTime();
}

/** Decided requests: outcome pill, approver, decided time and rejection reason (spec 9.11). */
export function DecidedList() {
  const approvedQuery = useQuery({
    queryKey: queryKeys.signupRequests({ status: 'approved' }),
    queryFn: () => usersApi.signupRequests('approved'),
  });
  const rejectedQuery = useQuery({
    queryKey: queryKeys.signupRequests({ status: 'rejected' }),
    queryFn: () => usersApi.signupRequests('rejected'),
  });

  const rows = useMemo(() => {
    const merged: { request: SignupRequest; outcome: Outcome }[] = [
      ...(approvedQuery.data?.items ?? []).map((request) => ({
        request,
        outcome: 'approved' as const,
      })),
      ...(rejectedQuery.data?.items ?? []).map((request) => ({
        request,
        outcome: 'rejected' as const,
      })),
    ];
    return merged.sort((a, b) => decidedAt(b.request) - decidedAt(a.request));
  }, [approvedQuery.data, rejectedQuery.data]);

  const error = approvedQuery.isError
    ? approvedQuery.error
    : rejectedQuery.isError
      ? rejectedQuery.error
      : null;

  if (approvedQuery.isLoading || rejectedQuery.isLoading) {
    return <SkeletonTable rows={5} columns={4} />;
  }
  if (error) {
    return (
      <ErrorState
        message={errorMessage(error)}
        requestId={isApiError(error) ? error.requestId : undefined}
        onRetry={() => {
          void approvedQuery.refetch();
          void rejectedQuery.refetch();
        }}
      />
    );
  }
  if (rows.length === 0) {
    return (
      <EmptyState
        title="No decided requests yet."
        description="Approvals and rejections will appear here."
      />
    );
  }

  return (
    <ul className="flex flex-col gap-2" aria-label="Decided access requests">
      {rows.map((row) => {
        const meta = OUTCOME_META[row.outcome];
        const Icon = meta.Icon;
        return (
          <li
            key={row.request.id}
            className="card flex flex-wrap items-start justify-between gap-3 p-4"
          >
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-body font-medium text-fg">{row.request.name}</span>
                <Badge variant={meta.variant}>
                  <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                  {meta.label}
                </Badge>
              </div>
              <p className="break-all text-small text-muted">{row.request.email}</p>
              <p className="text-small text-muted">
                {meta.label} by {row.request.decided_by?.name ?? '—'}
              </p>
              {row.request.status === 'rejected' && row.request.rejection_reason ? (
                <p className="text-small text-muted">Reason: {row.request.rejection_reason}</p>
              ) : null}
            </div>
            <RelativeTime iso={row.request.decided_at} className="text-small text-muted" />
          </li>
        );
      })}
    </ul>
  );
}
