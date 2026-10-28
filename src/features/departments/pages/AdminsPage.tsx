import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { errorMessage } from '@/api/client';
import { departmentsApi } from '@/api/endpoints/departments';
import { usersApi } from '@/api/endpoints/users';
import { queryKeys } from '@/api/queryKeys';
import { EmptyState, ErrorState } from '@/components/common/States';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { SkeletonTable } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/layout/PageHeader';
import { ConfigTabs } from '../components/ConfigTabs';
import { useToast } from '@/hooks/useToast';
import { AddAdminDialog } from '../components/AddAdminDialog';
import { AdminList } from '../components/AdminList';

/**
 * /config/admins (spec 9.13 + rule 14): Super Admin only — the router guards
 * the route with admins.manage. Add, deactivate, activate, remove admins and
 * the "Admins can manage departments" toggle.
 */
export default function AdminsPage() {
  const { success, error: errorToast } = useToast();
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);

  const adminsQuery = useQuery({ queryKey: queryKeys.admins, queryFn: usersApi.admins });
  const policyQuery = useQuery({ queryKey: queryKeys.policy, queryFn: departmentsApi.policy });

  const toggleMutation = useMutation({
    mutationFn: (checked: boolean) => {
      const current = policyQuery.data;
      if (!current) throw new Error('Policy is still loading.');
      return departmentsApi.updatePolicy({ ...current, admins_can_manage_departments: checked });
    },
    onSuccess: () => {
      success('Setting updated.');
      void qc.invalidateQueries({ queryKey: queryKeys.policy });
      void qc.invalidateQueries({ queryKey: queryKeys.departments });
    },
    onError: (err) => errorToast(errorMessage(err)),
  });

  const header = (
    <>
      <PageHeader
        title="Admin accounts"
        description="Only Super Admin can add, deactivate or remove Admin accounts, or change global policy."
        actions={
          <Button variant="primary" onClick={() => setAddOpen(true)}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add Admin
          </Button>
        }
      />
      <ConfigTabs />
    </>
  );

  return (
    <>
      {header}

      <div className="card mb-4 p-4">
        <div className="flex items-start gap-2.5">
          <Checkbox
            id="admins-manage-toggle"
            checked={policyQuery.data?.admins_can_manage_departments ?? false}
            disabled={!policyQuery.data || toggleMutation.isPending}
            onCheckedChange={(v) => toggleMutation.mutate(v === true)}
            aria-describedby="admins-manage-toggle-hint"
          />
          <div className="flex flex-col gap-0.5">
            <label htmlFor="admins-manage-toggle" className="text-body font-medium text-fg">
              Admins can manage departments, categories, Spokes and escalation contacts
            </label>
            <p id="admins-manage-toggle-hint" className="text-small text-muted">
              When switched off, the Departments screen becomes read-only for Admins.
            </p>
          </div>
        </div>
        {policyQuery.isError ? (
          <div className="mt-3">
            <ErrorState message={errorMessage(policyQuery.error)} onRetry={policyQuery.refetch} />
          </div>
        ) : null}
      </div>

      {adminsQuery.isPending ? (
        <SkeletonTable rows={4} columns={4} />
      ) : adminsQuery.isError ? (
        <ErrorState message={errorMessage(adminsQuery.error)} onRetry={adminsQuery.refetch} />
      ) : adminsQuery.data.items.length === 0 ? (
        <EmptyState
          title="No admin accounts yet."
          description="Add the first Admin to help govern tickets and departments."
          action={
            <Button variant="primary" onClick={() => setAddOpen(true)}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add Admin
            </Button>
          }
        />
      ) : (
        <AdminList admins={adminsQuery.data.items} />
      )}

      <AddAdminDialog open={addOpen} onOpenChange={setAddOpen} />
    </>
  );
}
