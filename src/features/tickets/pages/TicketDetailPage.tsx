import { useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage, isApiError } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import { departmentsApi } from '@/api/endpoints/departments';
import { ticketsApi } from '@/api/endpoints/tickets';
import { useCountdown } from '@/hooks/useCountdown';
import { usePermissions } from '@/hooks/usePermissions';
import { ErrorState, NotFoundState } from '@/components/common/States';
import { SlaBanner } from '@/components/common/SlaIndicator';
import { Timeline } from '@/components/common/Timeline';
import { Skeleton, SkeletonCard } from '@/components/ui/skeleton';
import { TicketHeader } from '../components/detail/TicketHeader';
import { RequestCard } from '../components/detail/RequestCard';
import { ResolutionCard } from '../components/detail/ResolutionCard';
import { HoldCard } from '../components/detail/HoldCard';
import { TicketActionPanel } from '../components/detail/TicketActionPanel';
import { DetailsColumn } from '../components/detail/DetailsColumn';
import { CommentBox } from '../components/detail/CommentBox';

/** Client errors never get better on retry; transient failures retry twice. */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (isApiError(error) && error.status < 500) return false;
  return failureCount < 2;
}

/** Spec 13: skeletons shaped like the final content, no spinners over blanks. */
function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-4" role="status" aria-label="Loading ticket">
      <div className="card p-4">
        <Skeleton className="h-3 w-32" />
        <Skeleton className="mt-3 h-4 w-44" />
        <Skeleton className="mt-3 h-7 w-3/4" />
      </div>
      <Skeleton className="h-12 w-full" />
      <div className="flex flex-col gap-4 nav:flex-row nav:items-start">
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <SkeletonCard lines={4} />
          <SkeletonCard lines={6} />
        </div>
        <div className="w-full nav:w-[300px]">
          <SkeletonCard lines={8} />
        </div>
      </div>
      <span className="sr-only">Loading ticket…</span>
    </div>
  );
}

/**
 * Spec 9.6 ticket detail. 404/403 renders "Access denied or not found." with
 * nothing about the ticket; the client only ever displays `ticket.sla`.
 */
export default function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const ticketId = id ?? '';
  const queryClient = useQueryClient();
  const { isStaff } = usePermissions();

  const ticketQuery = useQuery({
    queryKey: queryKeys.ticket(ticketId),
    queryFn: () => ticketsApi.get(ticketId),
    enabled: ticketId.length > 0,
    retry: shouldRetry,
  });
  const ticket = ticketQuery.data;

  const departmentsQuery = useQuery({
    queryKey: queryKeys.departments,
    queryFn: departmentsApi.list,
    enabled: Boolean(ticket),
    retry: shouldRetry,
  });

  const timelineQuery = useQuery({
    queryKey: queryKeys.timeline(ticketId),
    queryFn: () => ticketsApi.timeline(ticketId),
    enabled: Boolean(ticket),
    retry: shouldRetry,
  });

  // Refetch when the deadline passes so the banner refreshes (spec 11.3).
  const handleExpired = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.ticket(ticketId) });
  }, [queryClient, ticketId]);
  const countdown = useCountdown(ticket?.sla.due_at ?? null, handleExpired);

  if (ticketId.length === 0) return <NotFoundState />;
  if (ticketQuery.isPending) return <DetailSkeleton />;
  if (ticketQuery.isError || !ticket) {
    const err = ticketQuery.error;
    if (isApiError(err) && (err.status === 403 || err.status === 404)) {
      // Spec 9.6/18: no title, no counts, nothing about the ticket.
      return <NotFoundState />;
    }
    return (
      <ErrorState
        message={errorMessage(err)}
        requestId={isApiError(err) ? err.requestId : undefined}
        onRetry={() => void ticketQuery.refetch()}
      />
    );
  }

  const isRequester = !isStaff;
  const department =
    (departmentsQuery.data ?? []).find((d) => d.id === ticket.department_id) ?? null;

  return (
    <div className="flex flex-col gap-4">
      <TicketHeader ticket={ticket} />
      <SlaBanner ticket={ticket} now={countdown.now} isRequester={isRequester} />
      <div className="flex flex-col gap-4 nav:flex-row nav:items-start">
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <RequestCard ticket={ticket} />
          <ResolutionCard ticket={ticket} isRequester={isRequester} />
          <HoldCard ticket={ticket} />
          <TicketActionPanel ticket={ticket} />
          <section className="card p-4">
            <h2 className="text-section-title text-fg">Timeline</h2>
            {timelineQuery.isPending ? (
              <div className="mt-3 flex flex-col gap-3" role="status" aria-label="Loading timeline">
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-10 w-3/4" />
              </div>
            ) : timelineQuery.isError ? (
              <div className="mt-3">
                <ErrorState
                  message={errorMessage(timelineQuery.error)}
                  onRetry={() => void timelineQuery.refetch()}
                />
              </div>
            ) : (
              <Timeline events={timelineQuery.data ?? []} isRequester={isRequester} />
            )}
          </section>
          <CommentBox ticket={ticket} />
        </div>
        <aside className="w-full shrink-0 nav:w-[300px]">
          <DetailsColumn ticket={ticket} department={department} isStaff={isStaff} />
        </aside>
      </div>
    </div>
  );
}
