import { EmptyState } from '@/components/common/States';
import { PageHeader } from '@/components/layout/PageHeader';

/** /reports (spec 9.15): phase-5 placeholder behind the reports.view_org guard. */
export default function ReportsPage() {
  return (
    <>
      <PageHeader title="Reports" description="Organisation-wide metrics and exports." />
      <EmptyState
        title="Coming in a later release"
        description="Reports and exports are coming in a later release."
      />
    </>
  );
}
