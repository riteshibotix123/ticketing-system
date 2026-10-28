import { useEffect, useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { errorMessage, isApiError } from '@/api/client';
import { auditApi, type AuditListParams } from '@/api/endpoints/ops';
import { usersApi } from '@/api/endpoints/users';
import { queryKeys } from '@/api/queryKeys';
import { DataTable } from '@/components/common/DataTable';
import { EmptyState } from '@/components/common/States';
import { PageHeader } from '@/components/layout/PageHeader';
import { useDebounce } from '@/hooks/useDebounce';
import { useUrlFilters } from '@/hooks/useUrlFilters';
import { PAGE_SIZE } from '@/lib/constants';
import { dateInputToIso } from '@/lib/format';
import { auditColumns } from '../components/auditColumns';
import { AuditFilters } from '../components/AuditFilters';

interface TextFilters {
  q: string;
  action: string;
  ticket: string;
}

/**
 * /audit (spec 9.14): server-paginated, read-only audit log. Filters and page
 * are synced to the URL; text filters are debounced 300ms.
 */
export default function AuditPage() {
  const filters = useUrlFilters();
  const urlQ = filters.get('q');
  const urlAction = filters.get('action');
  const urlTicket = filters.get('ticket');

  const [text, setText] = useState<TextFilters>({
    q: urlQ,
    action: urlAction,
    ticket: urlTicket,
  });
  const debounced = useDebounce(text, 300);

  // Write debounced text filters through to the URL.
  useEffect(() => {
    if (debounced.q !== urlQ || debounced.action !== urlAction || debounced.ticket !== urlTicket) {
      filters.set({ q: debounced.q, action: debounced.action, ticket: debounced.ticket });
    }
  }, [debounced, urlQ, urlAction, urlTicket, filters]);

  // External URL changes (e.g. Clear) reset the local inputs.
  useEffect(() => {
    setText({ q: urlQ, action: urlAction, ticket: urlTicket });
  }, [urlQ, urlAction, urlTicket]);

  const usersQuery = useQuery({
    queryKey: queryKeys.users({ page_size: 100 }),
    queryFn: () => usersApi.list({ page_size: 100 }),
    retry: false,
  });

  const params = useMemo<AuditListParams>(
    () => ({
      q: debounced.q || undefined,
      actor_id: filters.get('actor') || undefined,
      action: debounced.action || undefined,
      ticket_id: debounced.ticket || undefined,
      from: dateInputToIso(filters.get('from')) ?? undefined,
      to: dateInputToIso(filters.get('to')) ?? undefined,
      page: filters.page,
      page_size: PAGE_SIZE,
    }),
    [debounced, filters],
  );

  const auditQuery = useQuery({
    queryKey: queryKeys.audit(params),
    queryFn: () => auditApi.list(params),
    placeholderData: keepPreviousData,
  });

  const page = auditQuery.data;
  const data = page ?? { items: [], total: 0, page: 1, page_size: PAGE_SIZE };

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Every change in the portal, newest first. Audit entries cannot be edited or deleted."
      />

      <div className="mb-3">
        <AuditFilters
          q={text.q}
          onQChange={(v) => setText((t) => ({ ...t, q: v }))}
          actorId={filters.get('actor')}
          onActorChange={(v) => filters.set({ actor: v })}
          actorOptions={
            usersQuery.isError
              ? null
              : (usersQuery.data?.items ?? []).map((u) => ({ id: u.id, name: u.name }))
          }
          action={text.action}
          onActionChange={(v) => setText((t) => ({ ...t, action: v }))}
          ticketId={text.ticket}
          onTicketChange={(v) => setText((t) => ({ ...t, ticket: v }))}
          from={filters.get('from')}
          onFromChange={(v) => filters.set({ from: v })}
          to={filters.get('to')}
          onToChange={(v) => filters.set({ to: v })}
          activeCount={filters.activeCount}
          onClear={() => filters.clear()}
        />
      </div>

      <DataTable
        caption="Audit log entries"
        columns={auditColumns}
        data={data.items}
        loading={auditQuery.isPending}
        error={
          auditQuery.isError
            ? {
                message: errorMessage(auditQuery.error),
                requestId: isApiError(auditQuery.error) ? auditQuery.error.requestId : undefined,
              }
            : null
        }
        onRetry={auditQuery.refetch}
        pagination={{
          page: data.page,
          pageSize: data.page_size,
          total: data.total,
        }}
        onPageChange={(p) => filters.set({ page: String(p) })}
        emptyState={
          <EmptyState
            variant="filtered"
            title="No audit entries match."
            description="Clear filters to see more."
          />
        }
      />
    </>
  );
}
