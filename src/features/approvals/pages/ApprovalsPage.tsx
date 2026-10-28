import { useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState, ErrorState } from '@/components/common/States';
import { SkeletonTable } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { errorMessage, isApiError } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import { usersApi } from '@/api/endpoints/users';
import { useUrlFilters } from '@/hooks/useUrlFilters';
import type { SignupRequest } from '@/types/domain';
import { DecidedList } from '@/features/approvals/components/DecidedList';
import { RequestRow } from '@/features/approvals/components/RequestRow';
import { ReviewDialog } from '@/features/approvals/components/ReviewDialog';

/** Access requests screen: Pending / Decided tabs synced to `?tab=` (spec 9.11). */
export default function ApprovalsPage() {
  const { get, set } = useUrlFilters();
  const [reviewTarget, setReviewTarget] = useState<SignupRequest | null>(null);
  const tab = get('tab') === 'decided' ? 'decided' : 'pending';

  const pendingQuery = useQuery({
    queryKey: queryKeys.signupRequests({ status: 'pending' }),
    queryFn: () => usersApi.signupRequests({ status: 'pending' }),
  });

  let pendingContent: ReactNode;
  if (pendingQuery.isLoading) {
    pendingContent = <SkeletonTable rows={6} columns={4} />;
  } else if (pendingQuery.isError) {
    pendingContent = (
      <ErrorState
        message={errorMessage(pendingQuery.error)}
        requestId={isApiError(pendingQuery.error) ? pendingQuery.error.requestId : undefined}
        onRetry={() => void pendingQuery.refetch()}
      />
    );
  } else {
    const items = pendingQuery.data?.items ?? [];
    pendingContent =
      items.length === 0 ? (
        <EmptyState title="No pending requests. You are all caught up." />
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Pending access requests">
          {items.map((request) => (
            <RequestRow key={request.id} request={request} onReview={setReviewTarget} />
          ))}
        </ul>
      );
  }

  return (
    <div>
      <PageHeader
        title="Access requests"
        description="Approve or reject signup requests. Nobody can review their own request, and the applicant is emailed every decision."
      />

      <Tabs value={tab} onValueChange={(value) => set({ tab: value })}>
        <TabsList>
          <TabsTrigger value="pending">Pending</TabsTrigger>
          <TabsTrigger value="decided">Decided</TabsTrigger>
        </TabsList>
        <TabsContent value="pending">{pendingContent}</TabsContent>
        <TabsContent value="decided">
          <DecidedList />
        </TabsContent>
      </Tabs>

      {reviewTarget ? (
        <ReviewDialog
          key={reviewTarget.id}
          request={reviewTarget}
          open
          onOpenChange={(open) => {
            if (!open) setReviewTarget(null);
          }}
        />
      ) : null}
    </div>
  );
}
