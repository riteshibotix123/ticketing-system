import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { errorMessage, isApiError } from '@/api/client';
import { departmentsApi } from '@/api/endpoints/departments';
import { usersApi } from '@/api/endpoints/users';
import { queryKeys } from '@/api/queryKeys';
import { EmptyState, ErrorState } from '@/components/common/States';
import { Button } from '@/components/ui/button';
import { SkeletonTable } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/layout/PageHeader';
import { ConfigTabs } from '../components/ConfigTabs';
import { usePermissions } from '@/hooks/usePermissions';
import { DepartmentDialog } from '../components/DepartmentDialog';
import { DepartmentTable } from '../components/DepartmentTable';
import { ReadOnlyBanner } from '../components/ReadOnlyBanner';
import type { Department } from '@/types/domain';

/**
 * /config/departments (spec 9.13): departments, Spokes, escalation contacts,
 * categories. Editable with departments.manage; otherwise read-only with a banner.
 */
export default function DepartmentsPage() {
  const { can } = usePermissions();
  const editable = can('departments.manage');
  // nonce forces fresh form defaults when reopening the dialog.
  const [dialog, setDialog] = useState<{ department: Department | null; nonce: number } | null>(
    null,
  );

  const departmentsQuery = useQuery({
    queryKey: queryKeys.departments,
    queryFn: departmentsApi.list,
  });

  const spokeUsersQuery = useQuery({
    queryKey: queryKeys.users({ role: 'spoke', page_size: 100 }),
    queryFn: () => usersApi.list({ role: 'spoke', page_size: 100 }),
    enabled: editable,
    retry: false,
  });

  const allUsersQuery = useQuery({
    queryKey: queryKeys.users({ page_size: 100 }),
    queryFn: () => usersApi.list({ page_size: 100 }),
    enabled: editable,
    retry: false,
  });

  const openCreate = () => setDialog({ department: null, nonce: Date.now() });
  const openEdit = (department: Department) => setDialog({ department, nonce: Date.now() });

  const header = (
    <>
      <PageHeader
        title="Departments"
        description="Departments, Spokes, escalation contacts and categories."
        actions={
          editable ? (
            <Button variant="primary" onClick={openCreate}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add department
            </Button>
          ) : undefined
        }
      />
      <ConfigTabs />
    </>
  );

  if (departmentsQuery.isPending) {
    return (
      <>
        {header}
        <SkeletonTable rows={6} columns={5} />
      </>
    );
  }

  if (departmentsQuery.isError) {
    return (
      <>
        {header}
        <ErrorState
          message={errorMessage(departmentsQuery.error)}
          requestId={
            isApiError(departmentsQuery.error) ? departmentsQuery.error.requestId : undefined
          }
          onRetry={departmentsQuery.refetch}
        />
      </>
    );
  }

  const departments = departmentsQuery.data;
  // 403 fallback: when /users is refused, pick candidates from each
  // department's own Spokes (handled per row in DepartmentTable).
  const spokeCandidates = spokeUsersQuery.isError ? null : (spokeUsersQuery.data?.items ?? []);
  const escalationCandidates = allUsersQuery.isError ? null : (allUsersQuery.data?.items ?? []);

  return (
    <>
      {header}
      {!editable ? <ReadOnlyBanner /> : null}
      {departments.length === 0 ? (
        <EmptyState
          title="No departments yet."
          description="Create the first department to start routing tickets."
          action={
            editable ? (
              <Button variant="primary" onClick={openCreate}>
                <Plus className="h-4 w-4" aria-hidden="true" />
                Add department
              </Button>
            ) : undefined
          }
        />
      ) : (
        <DepartmentTable
          departments={departments}
          editable={editable}
          spokeCandidates={spokeCandidates}
          escalationCandidates={escalationCandidates}
          onEdit={openEdit}
        />
      )}

      {dialog ? (
        <DepartmentDialog
          key={dialog.nonce}
          department={dialog.department}
          open
          onOpenChange={(v) => {
            if (!v) setDialog(null);
          }}
        />
      ) : null}
    </>
  );
}
