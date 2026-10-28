import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell } from 'lucide-react';
import { notificationsApi } from '@/api/endpoints/ops';
import { queryKeys } from '@/api/queryKeys';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Badge } from '@/components/ui/badge';
import { RelativeTime } from '@/components/common/RelativeTime';
import { EmptyState } from '@/components/common/States';
import { useToast } from '@/hooks/useToast';

/** Notification bell: unread count + popover with the latest 8 and "View all". */
export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { error: toastError } = useToast();

  const { data } = useQuery({
    queryKey: queryKeys.notifications({ recent: 8 }),
    queryFn: () => notificationsApi.list({ page: 1, page_size: 8 }),
    refetchInterval: 60_000,
    retry: false,
  });

  // Authoritative badge count — the recent-8 page can miss older unread items,
  // and the sidebar uses the same endpoint (the two must agree).
  const { data: counts } = useQuery({
    queryKey: queryKeys.unreadCount,
    queryFn: () => notificationsApi.unreadCount(),
    refetchInterval: 60_000,
    retry: false,
  });

  const unread = counts?.count ?? 0;

  const markRead = useMutation({
    mutationFn: (id: string) => notificationsApi.markRead(id),
    // Optimistic update — the only optimistic mutation in the app (spec 13).
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.notifications({ recent: 8 }) });
      const previous = queryClient.getQueryData(queryKeys.notifications({ recent: 8 }));
      queryClient.setQueryData<{ items: { id: string; read: boolean }[] }>(
        queryKeys.notifications({ recent: 8 }),
        (old) =>
          old
            ? { ...old, items: old.items.map((n) => (n.id === id ? { ...n, read: true } : n)) }
            : old,
      );
      return { previous };
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.previous)
        queryClient.setQueryData(queryKeys.notifications({ recent: 8 }), ctx.previous);
      toastError('Could not mark as read.');
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
      queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount });
    },
  });

  function openItem(ticketId?: string, id?: string) {
    if (id && !markRead.isPending) markRead.mutate(id);
    setOpen(false);
    if (ticketId) navigate(`/tickets/${ticketId}`);
    else navigate('/notifications');
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Notifications, ${unread} unread`}
          data-testid="bell"
        >
          <span className="relative">
            <Bell className="h-4 w-4" aria-hidden="true" />
            {unread > 0 ? (
              <span className="tabular absolute -right-1.5 -top-1.5 min-w-[16px] rounded-full bg-crit px-1 text-[10px] font-semibold leading-4 text-white">
                {unread > 99 ? '99+' : unread}
              </span>
            ) : null}
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[340px] p-2">
        <div className="flex items-center justify-between px-1 pb-2">
          <h2 className="label-caps text-muted">Notifications</h2>
          <button
            type="button"
            className="text-small text-accent underline-offset-4 hover:underline"
            onClick={() => {
              setOpen(false);
              navigate('/notifications');
            }}
          >
            View all
          </button>
        </div>
        {!data || data.items.length === 0 ? (
          <EmptyState title="Nothing new." description="You are all caught up." />
        ) : (
          <ul className="max-h-[320px] flex-col gap-1 overflow-y-auto">
            {data.items.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => openItem(n.ticket_id, n.id)}
                  className="w-full rounded px-2 py-2 text-left hover:bg-surface-2"
                >
                  <span className="flex items-start gap-2">
                    <span
                      className={
                        n.read ? 'text-body text-muted' : 'text-body font-semibold text-fg'
                      }
                    >
                      {n.text}
                    </span>
                    {n.critical ? (
                      <Badge variant="crit" className="ml-auto shrink-0">
                        Escalation
                      </Badge>
                    ) : null}
                  </span>
                  <span className="mt-0.5 block text-small text-muted">
                    <RelativeTime iso={n.created_at} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  );
}
