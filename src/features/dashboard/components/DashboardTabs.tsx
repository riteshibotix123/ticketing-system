import { ViewTabs } from '@/components/common/ViewTabs';
import type { DashboardView, DashboardViewId } from './statCards';

/**
 * Role switcher for viewers with several dashboards (spec 9.3).
 * The chosen tab lives in the URL as ?view= — the page owns that sync.
 */
export function DashboardTabs({
  views,
  value,
  onChange,
}: {
  views: DashboardView[];
  value: DashboardViewId;
  onChange: (id: DashboardViewId) => void;
}) {
  if (views.length < 2) return null;

  return (
    <ViewTabs
      label="Dashboard view"
      value={value}
      onChange={(next) => {
        // Values come from the known `views` list rendered above.
        onChange(next as DashboardViewId);
      }}
      items={views.map((v) => ({ id: v.id, label: v.label }))}
    />
  );
}
