import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { notificationsApi } from '@/api/endpoints/ops';
import { queryKeys } from '@/api/queryKeys';
import { errorMessage } from '@/api/client';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/button';
import { PAGE_SIZE } from '@/lib/constants';
import { useToast } from '@/hooks/useToast';
import { useUrlFilters } from '@/hooks/useUrlFilters';
import type { Notification, Paged } from '@/types/domain';
import { NotificationFilters, type NotificationFilter } from '../components/NotificationFilters';
import { NotificationList } from '../components/NotificationList';

/** Notification centre (spec 9.10/12): newest first, unread bold, escalation pill. */
export default function NotificationsPage() {
  const navigate = useNavigate();
  const { get, set, page } = useUrlFilters();
  const queryClient = useQueryClient();
  const { success, error: toastError } = useToast();

  const filter: NotificationFilter = get('filter') === 'unread' ? 'unread' : 'all';

  const params = useMemo(
    () => ({ page, page_size: PAGE_SIZE, ...(filter === 'unread' ? { unread: true } : {}) }),
    [page, filter],
  );

  const listKey = queryKeys.notifications(params);
  // Poll every 60s so the sidebar bell stays in sync (same query keys);
  // paused while the tab is hidden (refetchIntervalInBackground: false).
  const query = useQuery({
    queryKey: listKey,
    queryFn: () => notificationsApi.list(params),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

  const invalidateAll = () => {
    void queryClient.invalidateQueries({ queryKey: ['notifications'] });
    void queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount });
  };

  const markRead = useMutation({
    mutationFn: (id: string) => notificationsApi.markRead(id),
    // Optimistic update — the only optimistic mutation in the app (spec 13).
    onMutate: async (id: string) => {
      await queryClient.cancelQueries({ queryKey: listKey });
      const previous = queryClient.getQueryData<Paged<Notification>>(listKey);
      queryClient.setQueryData<Paged<Notification>>(listKey, (old) =>
        old
          ? { ...old, items: old.items.map((n) => (n.id === id ? { ...n, read: true } : n)) }
          : old,
      );
      return { previous };
    },
    onError: (err, _id, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(listKey, ctx.previous);
      toastError(errorMessage(err));
    },
    onSettled: invalidateAll,
  });

  const markAllRead = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: () => success('All notifications marked read.'),
    onError: (err) => toastError(errorMessage(err)),
    onSettled: invalidateAll,
  });

  function openNotification(n: Notification) {
    if (!n.read && !markRead.isPending) markRead.mutate(n.id);
    // Mark read then open the ticket; stay on the page when there is none.
    if (n.ticket_id) navigate(`/tickets/${n.ticket_id}`);
  }

  return (
    <div>
      <PageHeader
        title="Notifications"
        description="Also sent by email. Escalation emails cannot be turned off."
        actions={
          <Button
            variant="secondary"
            onClick={() => markAllRead.mutate()}
            loading={markAllRead.isPending}
            loadingLabel="Marking read"
          >
            Mark all read
          </Button>
        }
      />
      <div className="flex flex-col gap-3">
        <NotificationFilters
          value={filter}
          onChange={(v) => set({ filter: v === 'all' ? null : v })}
        />
        <NotificationList
          items={query.data?.items ?? []}
          loading={query.isLoading}
          error={query.isError ? errorMessage(query.error) : null}
          onRetry={() => query.refetch()}
          onOpen={openNotification}
          page={page}
          pageSize={PAGE_SIZE}
          total={query.data?.total ?? 0}
          onPageChange={(p) => set({ page: p === 1 ? null : String(p) }, { replace: false })}
        />
      </div>
    </div>
  );
}
