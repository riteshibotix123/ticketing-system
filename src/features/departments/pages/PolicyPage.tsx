import { useQuery } from '@tanstack/react-query';
import { errorMessage, isApiError } from '@/api/client';
import { departmentsApi } from '@/api/endpoints/departments';
import { queryKeys } from '@/api/queryKeys';
import { ErrorState } from '@/components/common/States';
import { SkeletonCard } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { PageHeader } from '@/components/layout/PageHeader';
import { ConfigTabs } from '../components/ConfigTabs';
import { usePermissions } from '@/hooks/usePermissions';
import { PRIORITY_LABEL, PRIORITY_MEANING, PRIORITY_ORDER } from '@/lib/constants';
import { PolicyForm } from '../components/PolicyForm';
import type { PolicyConfig } from '@/types/domain';

/**
 * /config/policy (spec 9.13 + 11.2): read-only view of the current policy plus
 * an edit form. Editing is Super Admin only (policy.manage); Admins may view.
 */
export default function PolicyPage() {
  const { can } = usePermissions();
  const canManage = can('policy.manage');

  const policyQuery = useQuery({
    queryKey: queryKeys.policy,
    queryFn: departmentsApi.policy,
  });

  const header = (
    <>
      <PageHeader
        title="SLA and escalation policy"
        description="All priorities share the same initial-response SLA. Priority changes escalation speed only. Values are read from the server."
      />
      <ConfigTabs />
    </>
  );

  if (policyQuery.isPending) {
    return (
      <>
        {header}
        <SkeletonCard />
      </>
    );
  }

  if (policyQuery.isError) {
    return (
      <>
        {header}
        <ErrorState
          message={errorMessage(policyQuery.error)}
          requestId={isApiError(policyQuery.error) ? policyQuery.error.requestId : undefined}
          onRetry={policyQuery.refetch}
        />
      </>
    );
  }

  const policy = policyQuery.data;

  return (
    <>
      {header}
      <PolicySummary policy={policy} />
      <div className="mt-4">
        <PolicyForm policy={policy} readOnly={!canManage} />
      </div>
    </>
  );
}

/** Read-only view of the current policy (spec 9.13). */
function PolicySummary({ policy }: { policy: PolicyConfig }) {
  const orgSettings: { label: string; value: string; note: string }[] = [
    {
      label: 'Update cadence',
      value: `${policy.update_cadence_hours} h`,
      note: 'Maximum silence from the team while a ticket is open.',
    },
    {
      label: 'Requester reminder',
      value: `${policy.requester_reminder_hours} h`,
      note: 'Hours before the requester is reminded to respond.',
    },
    {
      label: 'Auto-close',
      value:
        policy.auto_close_business_days === null
          ? 'Off'
          : `${policy.auto_close_business_days} business day(s)`,
      note: 'Resolved tickets close by themselves after this many days without confirmation.',
    },
    {
      label: 'SLA mode',
      value: policy.sla_mode === 'calendar' ? 'Calendar hours' : 'Business hours',
      note: 'Business-hours mode is not active yet.',
    },
  ];

  return (
    <div className="card scroll-thin overflow-x-auto">
      <Table>
        <caption className="sr-only">Current SLA and escalation policy</caption>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Priority</TableHead>
            <TableHead>Meaning</TableHead>
            <TableHead>Initial response (hours)</TableHead>
            <TableHead>Warning L1 (hours)</TableHead>
            <TableHead>L3 (hours)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {PRIORITY_ORDER.map((priority) => (
            <TableRow key={priority}>
              <TableCell className="font-medium text-fg">{PRIORITY_LABEL[priority]}</TableCell>
              <TableCell className="max-w-[36ch] text-small text-muted">
                {PRIORITY_MEANING[priority]}
              </TableCell>
              <TableCell className="tabular text-fg">{policy.initial_response_hours}</TableCell>
              <TableCell className="tabular text-fg">{policy.warning_hours[priority]}</TableCell>
              <TableCell className="tabular text-fg">{policy.l3_hours[priority]}</TableCell>
            </TableRow>
          ))}
          <TableRow className="hover:bg-transparent">
            <TableCell colSpan={5} className="bg-surface-2/60">
              <span className="label-caps text-muted">Organisation settings</span>
            </TableCell>
          </TableRow>
          {orgSettings.map((row) => (
            <TableRow key={row.label}>
              <th scope="row" className="px-3 py-2.5 text-left align-middle font-medium text-fg">
                {row.label}
              </th>
              <TableCell className="tabular text-fg">{row.value}</TableCell>
              <TableCell colSpan={3} className="text-small text-muted">
                {row.note}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
