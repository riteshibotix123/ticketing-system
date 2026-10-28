import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PageHeader } from '@/components/layout/PageHeader';
import { DataTable } from '@/components/common/DataTable';
import { EmptyState } from '@/components/common/States';
import { errorMessage, isApiError } from '@/api/client';
import { departmentsApi } from '@/api/endpoints/departments';
import { usersApi } from '@/api/endpoints/users';
import { queryKeys } from '@/api/queryKeys';
import { PAGE_SIZE } from '@/lib/constants';
import { useUrlFilters } from '@/hooks/useUrlFilters';
import type { AccountState, Role, UserListItem } from '@/types/domain';
import { UserFilters } from '@/features/users/components/UserFilters';
import { getUserColumns } from '@/features/users/components/userColumns';
import { RolesDialog } from '@/features/users/components/RolesDialog';
import { DeactivateDialog } from '@/features/users/components/DeactivateDialog';

/** Users and roles: server-side list with URL-synced filters (spec 9.12). */
export default function UsersPage() {
  const filters = useUrlFilters();
  const q = filters.get('q');
  const role = filters.get('role') as Role | undefined;
  const state = filters.get('state') as AccountState | undefined;
  const departmentFilter = filters.get('department_id');

  const params = useMemo(
    () => ({
      q: q || undefined,
      role: role || undefined,
      state: state || undefined,
      department_id: departmentFilter || undefined,
      page: filters.page,
      page_size: PAGE_SIZE,
    }),
    [q, role, state, departmentFilter, filters.page],
  );

  const usersQuery = useQuery({
    queryKey: queryKeys.users(params),
    queryFn: () => usersApi.list(params),
  });
  const departmentsQuery = useQuery({
    queryKey: queryKeys.departments,
    queryFn: departmentsApi.list,
    staleTime: 60_000,
  });

  const [rolesTarget, setRolesTarget] = useState<UserListItem | null>(null);
  const [accountTarget, setAccountTarget] = useState<UserListItem | null>(null);

  const columns = useMemo(
    () =>
      getUserColumns({
        departments: departmentsQuery.data ?? [],
        onRoles: setRolesTarget,
        onAccount: setAccountTarget,
      }),
    [departmentsQuery.data],
  );

  const error = usersQuery.isError
    ? {
        message: errorMessage(usersQuery.error),
        requestId: isApiError(usersQuery.error) ? usersQuery.error.requestId : undefined,
      }
    : null;

  const emptyState =
    filters.activeCount > 0 ? (
      <EmptyState
        variant="filtered"
        title="No users match."
        description="Clear filters to see more."
      />
    ) : (
      <EmptyState
        title="No users yet."
        description="Accounts appear here as people sign up or are created."
      />
    );

  return (
    <div>
      <PageHeader
        title="Users"
        description="Search people, manage Spoke departments, and activate or deactivate accounts. Every change asks for a reason and is audit logged."
      />

      <UserFilters filters={filters} departments={departmentsQuery.data ?? []} />

      <div className="mt-3">
        <DataTable
          caption="Users of the ticketing portal"
          columns={columns}
          data={usersQuery.data?.items ?? []}
          loading={usersQuery.isLoading}
          error={error}
          onRetry={() => void usersQuery.refetch()}
          emptyState={emptyState}
          pagination={{
            page: filters.page,
            pageSize: PAGE_SIZE,
            total: usersQuery.data?.total ?? 0,
          }}
          onPageChange={(page) => filters.set({ page: String(page) })}
        />
      </div>

      {rolesTarget ? (
        <RolesDialog
          user={rolesTarget}
          open
          onOpenChange={(open) => {
            if (!open) setRolesTarget(null);
          }}
        />
      ) : null}
      {accountTarget ? (
        <DeactivateDialog
          user={accountTarget}
          open
          onOpenChange={(open) => {
            if (!open) setAccountTarget(null);
          }}
        />
      ) : null}
    </div>
  );
}
