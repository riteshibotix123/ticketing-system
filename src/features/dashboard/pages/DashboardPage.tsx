import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '@/api/endpoints/ops';
import { queryKeys } from '@/api/queryKeys';
import { errorMessage } from '@/api/client';
import { PageHeader } from '@/components/layout/PageHeader';
import { ErrorState } from '@/components/common/States';
import { SkeletonTable, SkeletonTiles } from '@/components/ui/skeleton';
import { usePermissions } from '@/hooks/usePermissions';
import { useUrlFilters } from '@/hooks/useUrlFilters';
import { AttentionTable } from '../components/AttentionTable';
import { DashboardTabs } from '../components/DashboardTabs';
import { DepartmentBars } from '../components/DepartmentBars';
import { KpiTile } from '../components/KpiTile';
import { RecentUpdates } from '../components/RecentUpdates';
import {
  adminStatCards,
  dashboardViews,
  employeeStatCards,
  spokeStatCards,
  type DashboardViewId,
} from '../components/statCards';

/**
 * Poll every 60s (spec 9.3). `refetchIntervalInBackground: false` keeps the
 * interval paused while the browser tab is hidden — TanStack Query skips
 * interval refetches when `document.visibilityState` is not "visible" unless
 * background refetching is enabled.
 */
const POLL = { refetchInterval: 60_000, refetchIntervalInBackground: false } as const;

/** Role dashboards (spec 6.4/9.3): highest role wins; several roles get a switcher in ?view=. */
export default function DashboardPage() {
  const { can, isStaff, me } = usePermissions();
  const { get, set } = useUrlFilters();

  const views = useMemo(
    () => dashboardViews(can('tickets.view_all'), me?.spoke_departments.length ?? 0),
    [can, me],
  );

  const requested = get('view');
  const defaultView = views[0]?.id ?? 'employee';
  // `requested` is validated against the viewer's own views before the cast.
  const view: DashboardViewId = views.some((v) => v.id === requested)
    ? (requested as DashboardViewId)
    : defaultView;

  const adminQuery = useQuery({
    queryKey: queryKeys.dashboard('admin'),
    queryFn: dashboardApi.admin,
    enabled: view === 'admin',
    ...POLL,
  });
  const spokeQuery = useQuery({
    queryKey: queryKeys.dashboard('spoke'),
    queryFn: dashboardApi.spoke,
    enabled: view === 'spoke',
    ...POLL,
  });
  const employeeQuery = useQuery({
    queryKey: queryKeys.dashboard('employee'),
    queryFn: dashboardApi.employee,
    enabled: view === 'employee',
    ...POLL,
  });

  const active = view === 'admin' ? adminQuery : view === 'spoke' ? spokeQuery : employeeQuery;

  const cards = useMemo(() => {
    if (view === 'admin' && adminQuery.data) return adminStatCards(adminQuery.data);
    if (view === 'spoke' && spokeQuery.data) return spokeStatCards(spokeQuery.data);
    if (view === 'employee' && employeeQuery.data) return employeeStatCards(employeeQuery.data);
    return [];
  }, [view, adminQuery.data, spokeQuery.data, employeeQuery.data]);

  const attention =
    (view === 'admin'
      ? adminQuery.data?.attention
      : view === 'spoke'
        ? spokeQuery.data?.attention
        : employeeQuery.data?.attention) ?? [];

  // Admin and spoke dashboards show 7 tiles, the employee dashboard 4.
  const tileCount = view === 'employee' ? 4 : 7;

  function changeView(id: DashboardViewId) {
    set({ view: id === defaultView ? null : id });
  }

  return (
    <div>
      <PageHeader title="Dashboard" />
      <DashboardTabs views={views} value={view} onChange={changeView} />

      {active.isLoading ? (
        <div className="mt-4 flex flex-col gap-4">
          <SkeletonTiles count={tileCount} />
          <SkeletonTable rows={4} columns={6} />
        </div>
      ) : active.isError ? (
        <div className="mt-4">
          <ErrorState message={errorMessage(active.error)} onRetry={() => active.refetch()} />
        </div>
      ) : (
        <div className="mt-4 flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {cards.map((card) => (
              <KpiTile key={card.key} card={card} />
            ))}
          </div>

          <AttentionTable tickets={attention} isStaff={isStaff} />

          {view === 'admin' && adminQuery.data ? (
            <DepartmentBars rows={adminQuery.data.by_department} />
          ) : null}

          {view === 'employee' && employeeQuery.data ? (
            <RecentUpdates events={employeeQuery.data.recent_updates} />
          ) : null}
        </div>
      )}
    </div>
  );
}
