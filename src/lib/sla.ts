import type { SlaState, Ticket } from '@/types/domain';
import { formatDuration } from './format';

export type Tone = 'ok' | 'warn' | 'crit' | 'muted' | 'info';

export interface SlaMeta {
  label: string;
  icon: string;
  tone: Tone;
}

/** Spec section 11.3 display table. Levels come from the server, never computed here. */
export const SLA_LEVEL_META: Record<0 | 1 | 2 | 3, SlaMeta> = {
  0: { label: 'On track', icon: '●', tone: 'ok' },
  1: { label: 'Warning', icon: '▲', tone: 'warn' },
  2: { label: 'Breached', icon: '■', tone: 'crit' },
  3: { label: 'Escalated L3', icon: '■', tone: 'crit' },
};

export interface SlaDisplay {
  icon: string;
  /** Level label ("On track", "Warning", "Breached", "Escalated L3") or server label when paused/stopped. */
  label: string;
  /** Countdown text, e.g. "Response due in 5h 12m". Empty string when no due_at. */
  text: string;
  tone: Tone;
  level: 0 | 1 | 2 | 3;
  paused: boolean;
  stopped: boolean;
  /** True when the deadline is in the past. */
  overdue: boolean;
}

function countdownText(sla: SlaState, now: number): { text: string; overdue: boolean } {
  if (!sla.due_at) return { text: '', overdue: false };
  const delta = new Date(sla.due_at).getTime() - now;
  const overdue = delta < 0;
  const amount = formatDuration(Math.abs(delta));
  switch (sla.kind) {
    case 'initial_response':
      return {
        text: overdue ? `Response overdue ${amount}` : `Response due in ${amount}`,
        overdue,
      };
    case 'progress_update':
      return { text: overdue ? `Update overdue ${amount}` : `Next update in ${amount}`, overdue };
    case 'eta':
      return { text: overdue ? `ETA overdue ${amount}` : `ETA due in ${amount}`, overdue };
    default:
      return { text: overdue ? `Overdue ${amount}` : `Due in ${amount}`, overdue };
  }
}

/**
 * Build the display state for an SLA banner / indicator.
 * The client displays `ticket.sla` — it never derives the level.
 */
export function slaDisplay(sla: SlaState, now: number = Date.now()): SlaDisplay {
  const meta = SLA_LEVEL_META[sla.level];
  if (sla.stopped) {
    return {
      icon: '◷',
      label: sla.label,
      text: '',
      tone: 'muted',
      level: sla.level,
      paused: false,
      stopped: true,
      overdue: false,
    };
  }
  if (sla.paused) {
    return {
      icon: '◷',
      label: sla.label || 'Timer paused',
      text: '',
      tone: 'muted',
      level: sla.level,
      paused: true,
      stopped: false,
      overdue: false,
    };
  }
  const { text, overdue } = countdownText(sla, now);
  return {
    icon: sla.level === 3 ? '■' : meta.icon,
    label: sla.level === 3 ? 'Escalated L3' : sla.label || meta.label,
    text,
    tone: meta.tone,
    level: sla.level,
    paused: false,
    stopped: false,
    overdue,
  };
}

/**
 * Requester-safe SLA text: never levels, never escalation detail.
 * "Awaiting first response" or "In progress" plus the ETA.
 */
export function requesterSlaText(
  ticket: Pick<Ticket, 'status' | 'acknowledged_at' | 'eta'>,
): string {
  if (ticket.eta) {
    return `ETA ${new Date(ticket.eta).toLocaleString()}`;
  }
  return ticket.acknowledged_at ? 'In progress' : 'Awaiting first response';
}

export const SLA_STATE_FILTERS = [
  { id: 'any', label: 'Any' },
  { id: 'unacknowledged', label: 'Unacknowledged' },
  { id: 'warning', label: 'Warning' },
  { id: 'breached', label: 'Breached' },
  { id: 'stale', label: 'Stale' },
] as const;

export type SlaStateFilterId = (typeof SLA_STATE_FILTERS)[number]['id'];

/** Priority ordering, critical first (used for client-side fallbacks only). */
const PRIORITY_RANK = { critical: 3, high: 2, medium: 1, low: 0 } as const;

/**
 * Default "urgency" sort (spec 11.4): escalation level desc, priority desc
 * (critical first), oldest SLA start first. Server applies this too; used as a
 * client fallback when no server ordering applies.
 */
export function compareUrgency(a: Ticket, b: Ticket): number {
  if (b.sla.level !== a.sla.level) return b.sla.level - a.sla.level;
  const p = PRIORITY_RANK[b.priority] - PRIORITY_RANK[a.priority];
  if (p !== 0) return p;
  return new Date(a.sla_started_at).getTime() - new Date(b.sla_started_at).getTime();
}
