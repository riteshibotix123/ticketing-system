import { formatDuration } from '@/lib/format';
import type { AdminDashboard, EmployeeDashboard, SpokeDashboard } from '@/types/domain';

/** Which dashboards the viewer qualifies for, highest first (spec 9.3). */
export type DashboardViewId = 'admin' | 'spoke' | 'employee';

export interface DashboardView {
  id: DashboardViewId;
  label: string;
}

/**
 * Tab labels from spec 9.3: "Organisation" (Admin), "My department" (Spoke),
 * "My requests" (every viewer raises tickets, so the employee variant is
 * always available as the base case).
 */
export function dashboardViews(canViewAll: boolean, spokeDepartmentCount: number): DashboardView[] {
  const views: DashboardView[] = [];
  if (canViewAll) views.push({ id: 'admin', label: 'Organisation' });
  if (spokeDepartmentCount > 0) views.push({ id: 'spoke', label: 'My department' });
  views.push({ id: 'employee', label: 'My requests' });
  return views;
}

/** A KPI tile: big tabular number + label + hint, optionally deep-linking into /tickets. */
export interface StatCard {
  key: string;
  value: string;
  label: string;
  hint: string;
  /** Deep link into the filtered ticket list with the same count; undefined = informational tile. */
  to?: string;
}

function formatPct(n: number): string {
  return `${Number.isInteger(n) ? n : n.toFixed(1)}%`;
}

/** "12s" under a minute, otherwise the shared duration format ("5h 12m", spec 11.3). */
function formatSeconds(seconds: number): string {
  return seconds >= 60 ? formatDuration(seconds * 1000) : `${seconds}s`;
}

const ALL = '/tickets?tab=all';
const QUEUE = '/tickets?tab=queue';
const MINE = '/tickets?tab=mine';

/** Admin KPI tiles (spec 9.3). sla_met_pct and reopen_rate_pct are informational. */
export function adminStatCards(d: AdminDashboard): StatCard[] {
  return [
    {
      key: 'open',
      label: 'Open tickets',
      value: String(d.open_count),
      hint: 'Across all departments',
      to: `${ALL}&status=open`,
    },
    {
      key: 'sla-met',
      label: 'SLA met',
      value: formatPct(d.sla_met_pct),
      hint: 'Answered within the deadline',
    },
    {
      key: 'avg-response',
      label: 'Avg first response',
      value: formatSeconds(d.avg_initial_response_seconds),
      hint: 'Ticket created to first reply',
    },
    {
      key: 'breached',
      label: 'SLA breached',
      value: String(d.breached_count),
      hint: 'The deadline passed',
      to: `${ALL}&sla_state=breached`,
    },
    {
      key: 'l3',
      label: 'Escalated L3',
      value: String(d.l3_count),
      hint: 'Highest escalation level',
      to: `${ALL}&escalation_level=3`,
    },
    {
      key: 'stale',
      label: 'Stale',
      value: String(d.stale_count),
      hint: 'No update for too long',
      to: `${ALL}&sla_state=stale`,
    },
    {
      key: 'reopen-rate',
      label: 'Reopen rate',
      value: formatPct(d.reopen_rate_pct),
      hint: 'Reopened after resolve',
    },
  ];
}

/** Spoke KPI tiles — all deep-link into the department queue (spec 9.3). */
export function spokeStatCards(d: SpokeDashboard): StatCard[] {
  return [
    {
      key: 'unacknowledged',
      label: 'New, not acknowledged',
      value: String(d.new_unacknowledged),
      hint: 'Waiting for a first response',
      to: `${QUEUE}&sla_state=unacknowledged`,
    },
    {
      key: 'approaching',
      label: 'Approaching SLA',
      value: String(d.approaching_sla),
      hint: 'Warning level',
      to: `${QUEUE}&sla_state=warning`,
    },
    {
      key: 'breached',
      label: 'Breached',
      value: String(d.breached),
      hint: 'The deadline passed',
      to: `${QUEUE}&sla_state=breached`,
    },
    {
      key: 'stale',
      label: 'Stale or ETA overdue',
      value: String(d.stale_or_eta_overdue),
      hint: 'Silent too long, or ETA missed',
      to: `${QUEUE}&sla_state=stale`,
    },
    {
      key: 'awaiting-requester',
      label: 'Awaiting requester',
      value: String(d.awaiting_requester),
      hint: 'Timer paused',
      to: `${QUEUE}&status=awaiting_requester`,
    },
    {
      key: 'on-hold',
      label: 'On hold',
      value: String(d.on_hold),
      hint: 'Timer paused',
      to: `${QUEUE}&status=on_hold`,
    },
    {
      key: 'resolved',
      label: 'Resolved, awaiting closure',
      value: String(d.resolved_pending_closure),
      hint: 'Requester to confirm',
      to: `${QUEUE}&status=resolved`,
    },
  ];
}

/** Employee KPI tiles — all deep-link into "Raised by me" (spec 9.3). */
export function employeeStatCards(d: EmployeeDashboard): StatCard[] {
  return [
    {
      key: 'open',
      label: 'Open requests',
      value: String(d.open),
      hint: 'Tickets you raised',
      to: `${MINE}&status=open`,
    },
    {
      key: 'awaiting-me',
      label: 'Awaiting my response',
      value: String(d.awaiting_my_response),
      hint: 'The team asked you something',
      to: `${MINE}&status=awaiting_requester`,
    },
    {
      key: 'to-confirm',
      label: 'Resolved, to confirm',
      value: String(d.resolved_to_confirm),
      hint: 'Confirm closure or reopen',
      to: `${MINE}&status=resolved`,
    },
    {
      key: 'closed',
      label: 'Closed',
      value: String(d.closed),
      hint: 'Finished tickets',
      to: `${MINE}&status=closed`,
    },
  ];
}
