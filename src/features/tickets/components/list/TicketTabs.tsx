import { ViewTabs } from '@/components/common/ViewTabs';
import { TICKET_TABS, type TicketTabId } from '@/lib/constants';
import type { Role } from '@/types/domain';

export interface TicketTabOption {
  id: TicketTabId;
  label: string;
}

/** Default tab per spec 9.4: Admin+ -> All, Spoke -> Queue, else Mine. */
export function defaultTicketTab(primaryRole: Role | null, canViewAll: boolean): TicketTabId {
  if (canViewAll) return 'all';
  if (primaryRole === 'spoke') return 'queue';
  return 'mine';
}

/** Tabs shown by permission (spec 4/9.4): queue needs the department flag, all needs view_all. */
export function visibleTicketTabs(
  canViewDepartment: boolean,
  canViewAll: boolean,
): TicketTabOption[] {
  return TICKET_TABS.filter(
    (tab) =>
      tab.id === 'mine' ||
      tab.id === 'assigned' ||
      (tab.id === 'queue' && (canViewDepartment || canViewAll)) ||
      (tab.id === 'all' && canViewAll),
  ).map((tab) => ({ id: tab.id, label: tab.label }));
}

/** Controlled tab strip; the parent owns the value (URL query string). */
export function TicketTabs({
  tabs,
  value,
  onValueChange,
}: {
  tabs: TicketTabOption[];
  value: string;
  onValueChange: (id: string) => void;
}) {
  return <ViewTabs label="Ticket views" value={value} onChange={onValueChange} items={tabs} />;
}
