import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import type { SortingState } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { errorMessage, isApiError } from '@/api/client';
import { departmentsApi } from '@/api/endpoints/departments';
import { ticketsApi, type TicketListParams } from '@/api/endpoints/tickets';
import { queryKeys } from '@/api/queryKeys';
import { DataTable } from '@/components/common/DataTable';
import { EmptyState } from '@/components/common/States';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/layout/PageHeader';
import { OPEN_STATUSES, PAGE_SIZE, TICKET_TABS, type TicketTabId } from '@/lib/constants';
import { useDebounce } from '@/hooks/useDebounce';
import { usePermissions } from '@/hooks/usePermissions';
import { useUrlFilters } from '@/hooks/useUrlFilters';
import type { Ticket } from '@/types/domain';
import { TicketFilters, type TicketFilterValues } from '../components/list/TicketFilters';
import { defaultTicketTab, TicketTabs, visibleTicketTabs } from '../components/list/TicketTabs';
import {
  buildTicketColumns,
  DEFAULT_SORT,
  sortToSortingState,
  sortingStateToSort,
} from '../components/list/ticketColumns';

export default function TicketListPage() {
  const { get, set, clear, page, activeCount } = useUrlFilters();
  const { me, can, primaryRole, isStaff } = usePermissions();
  const navigate = useNavigate();

  // ---- tabs (value lives in the URL, spec 8) ------------------------------
  const tabs = useMemo(
    () => visibleTicketTabs(can('tickets.view_department'), can('tickets.view_all')),
    [can],
  );
  const defaultTab = defaultTicketTab(primaryRole, can('tickets.view_all'));
  const urlTab = get('tab');
  const tab: TicketTabId = tabs.some((t) => t.id === urlTab)
    ? (urlTab as TicketTabId)
    : tabs.some((t) => t.id === defaultTab)
      ? defaultTab
      : 'mine';
  const scope = TICKET_TABS.find((t) => t.id === tab)?.scope ?? 'mine';

  // ---- filters (URL state; search debounced 300ms, spec 9.4) --------------
  // Two-way sync: the input pushes into the URL after 300ms of silence, and
  // external URL changes (back/forward, Clear) flow back into the input.
  const urlQ = get('q');
  const [searchInput, setSearchInput] = useState(urlQ);
  const pushedQ = useRef(urlQ);
  const debouncedQ = useDebounce(searchInput, 300);
  useEffect(() => {
    if (urlQ !== pushedQ.current) {
      pushedQ.current = urlQ;
      setSearchInput(urlQ);
    }
  }, [urlQ]);
  useEffect(() => {
    if (debouncedQ !== urlQ) {
      pushedQ.current = debouncedQ;
      set({ q: debouncedQ });
    }
    // `urlQ` is read fresh from the URL on every change.
  }, [debouncedQ, urlQ, set]);

  const values: TicketFilterValues = {
    q: get('q'),
    status: get('status') || 'any',
    priority: get('priority') || 'any',
    department: get('department'),
    sla: get('sla') || 'any',
    confidential: get('confidential'),
    overdue: get('overdue'),
  };

  const handleFiltersChange = useCallback(
    (next: TicketFilterValues) => {
      set({
        status: next.status !== 'any' ? next.status : null,
        priority: next.priority !== 'any' ? next.priority : null,
        department: next.department || null,
        sla: next.sla !== 'any' ? next.sla : null,
        confidential: next.confidential || null,
        overdue: next.overdue || null,
      });
    },
    [set],
  );

  const clearAllFilters = useCallback(() => {
    setSearchInput('');
    clear(['tab']);
  }, [clear]);

  // ---- queries ------------------------------------------------------------
  const params: TicketListParams = {
    scope,
    q: values.q || undefined,
    status:
      values.status === 'any'
        ? undefined
        : values.status === 'open'
          ? OPEN_STATUSES
          : [values.status],
    priority: values.priority === 'any' ? undefined : [values.priority],
    department_id: values.department || undefined,
    sla_state: values.sla === 'any' ? undefined : values.sla,
    confidential: values.confidential === '1' ? true : undefined,
    overdue_eta: values.overdue === '1' ? true : undefined,
    sort: get('sort') || DEFAULT_SORT,
    page,
    page_size: PAGE_SIZE,
  };

  const listQuery = useQuery({
    queryKey: queryKeys.tickets(params),
    queryFn: () => ticketsApi.list(params),
    placeholderData: keepPreviousData,
  });

  const departmentsQuery = useQuery({
    queryKey: queryKeys.departments,
    queryFn: () => departmentsApi.list(),
    staleTime: 5 * 60_000,
  });
  const departments = useMemo(() => departmentsQuery.data ?? [], [departmentsQuery.data]);
  const departmentName = useCallback(
    (id: string) => departments.find((dept) => dept.id === id)?.name,
    [departments],
  );

  // ---- table --------------------------------------------------------------
  const columns = useMemo(
    () =>
      buildTicketColumns({
        currentUserId: me?.id ?? null,
        requesterView: !isStaff,
        departmentName,
      }),
    [me?.id, isStaff, departmentName],
  );

  const sorting = useMemo(() => sortToSortingState(params.sort ?? DEFAULT_SORT), [params.sort]);
  const handleSortingChange = useCallback(
    (next: SortingState) => set({ sort: sortingStateToSort(next) }),
    [set],
  );

  const openTicket = useCallback((ticket: Ticket) => navigate(`/tickets/${ticket.id}`), [navigate]);

  const emptyState =
    activeCount > 0 ? (
      <EmptyState
        variant="filtered"
        title="No tickets match."
        description="Clear filters to see more."
        action={
          <Button variant="secondary" size="sm" onClick={clearAllFilters}>
            Clear filters
          </Button>
        }
      />
    ) : (
      <EmptyState title="Nothing open." description="You are all caught up." />
    );

  return (
    <div>
      <PageHeader
        title="Tickets"
        actions={
          can('tickets.create') ? (
            <Button variant="primary" asChild>
              <Link to="/tickets/new">
                <Plus className="h-4 w-4" aria-hidden="true" />
                New ticket
              </Link>
            </Button>
          ) : null
        }
      />

      <div className="mb-3">
        <TicketTabs tabs={tabs} value={tab} onValueChange={(id) => set({ tab: id })} />
      </div>

      <div className="mb-3">
        <TicketFilters
          values={values}
          onSearchChange={setSearchInput}
          onChange={handleFiltersChange}
          departments={departments}
          showDepartment={can('tickets.view_all')}
          activeCount={activeCount}
          onClear={clearAllFilters}
        />
      </div>

      <DataTable<Ticket>
        caption="Tickets"
        columns={columns}
        data={listQuery.data?.items ?? []}
        loading={listQuery.isPending}
        error={
          listQuery.error
            ? {
                message: errorMessage(listQuery.error),
                requestId: isApiError(listQuery.error) ? listQuery.error.requestId : undefined,
              }
            : null
        }
        onRetry={() => void listQuery.refetch()}
        onRowClick={openTicket}
        emptyState={emptyState}
        sorting={sorting}
        onSortingChange={handleSortingChange}
        pagination={{
          page: listQuery.data?.page ?? page,
          pageSize: listQuery.data?.page_size ?? PAGE_SIZE,
          total: listQuery.data?.total ?? 0,
        }}
        onPageChange={(nextPage) => set({ page: String(nextPage) })}
      />
    </div>
  );
}
