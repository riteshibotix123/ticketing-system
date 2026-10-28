/**
 * MOCK-SERVER-side SLA engine. The mock acts as the backend, so every level,
 * kind and deadline below is computed here — never in the browser (spec 18).
 *
 * Policy defaults per spec 11.2 (read from db.policy, never hardcoded in UI):
 * - initial response 24h for all priorities
 * - L1 warning at warning_hours (18/18/18/12 for critical)
 * - L2 breach at initial_response_hours, at update_cadence_hours of silence,
 *   or when the ETA is overdue
 * - L3 at l3_hours (48/48/36/30)
 *
 * ASSUMPTION: for the update-cadence rule this mock uses warning_hours for L1
 * and l3_hours for L3 (requirement 6); spec 11.2's 20h/48h cadence escalations
 * are effectively the same shape (cadence 24h, L3 at 48h for most priorities).
 */
import type { PolicyConfig, Priority, SlaState, SlaKind, Ticket } from '@/types/domain';
import { db, findTicket, HOUR_MS, type DbTicket } from './db';

interface Candidate {
  kind: SlaKind;
  due: number;
  label: string;
}

function statusLabel(status: Ticket['status']): string {
  return status === 'closed' ? 'Closed' : 'Cancelled';
}

/**
 * Recompute `ticket.sla` from the stored deadlines and current status, then
 * return it. Deadlines are already in the display frame (they were shifted by
 * the demo clock), so levels are derived by comparing them against real now.
 */
export function recomputeSla(rec: DbTicket): SlaState {
  const t = rec.ticket;
  const policy = db.policy;
  const now = Date.now();

  // Stopped: final states show the status itself (spec 11.3).
  if (t.status === 'closed' || t.status === 'cancelled') {
    return apply(t, {
      level: 0,
      kind: null,
      paused: false,
      stopped: true,
      due_at: null,
      label: statusLabel(t.status),
    });
  }
  // Resolved: timer stopped-but-not-stopped, awaiting requester confirmation.
  if (t.status === 'resolved') {
    return apply(t, {
      level: 0,
      kind: null,
      paused: true,
      stopped: false,
      due_at: null,
      label: 'Awaiting closure',
    });
  }
  // Paused states: on hold / awaiting requester freeze the countdown (spec 11.3).
  if (t.status === 'on_hold' || t.status === 'awaiting_requester') {
    return apply(t, {
      level: 0,
      kind: null,
      paused: true,
      stopped: false,
      due_at: null,
      label: 'Timer paused',
    });
  }

  const candidates: Candidate[] = [];
  if (!t.acknowledged_at && rec.resp_due != null) {
    candidates.push({ kind: 'initial_response', due: rec.resp_due, label: 'Initial response due' });
  }
  if (rec.update_due != null) {
    candidates.push({ kind: 'progress_update', due: rec.update_due, label: 'Update cadence due' });
  }
  if (t.eta) {
    const eta = Date.parse(t.eta);
    if (!Number.isNaN(eta)) {
      candidates.push({ kind: 'eta', due: eta, label: eta <= now ? 'ETA overdue' : 'ETA due' });
    }
  }
  if (candidates.length === 0) {
    // Defensive fallback: an active ticket without deadlines counts as on track.
    return apply(t, {
      level: 0,
      kind: null,
      paused: false,
      stopped: false,
      due_at: null,
      label: 'No deadline set',
    });
  }

  // Next deadline drives kind/label/countdown; levels take the WORST rule so an
  // overdue ETA breaches (L2) even when the cadence deadline is still ahead.
  let next = candidates[0];
  for (const c of candidates) if (c.due < next.due) next = c;
  let level: 0 | 1 | 2 | 3 = 0;
  for (const c of candidates) {
    const l = levelFor(c, t.priority, policy, now);
    if (l > level) level = l;
  }
  return apply(t, {
    level,
    kind: next.kind,
    paused: false,
    stopped: false,
    due_at: new Date(next.due).toISOString(),
    label: next.label,
  });
}

/**
 * Thresholds are linear from a shared base, so they are derived from the stored
 * deadline: L1 = due - (step - warning), L2 = due, L3 = due + (l3 - step).
 * The eta candidate only contributes the L2 (overdue) rule; L1/L3 for silence
 * come from the cadence candidate.
 */
function levelFor(
  c: Candidate,
  priority: Priority,
  policy: PolicyConfig,
  now: number,
): 0 | 1 | 2 | 3 {
  const warn = policy.warning_hours[priority] * HOUR_MS;
  const l3 = policy.l3_hours[priority] * HOUR_MS;
  if (c.kind === 'eta') return now >= c.due ? 2 : 0;

  const step =
    c.kind === 'initial_response'
      ? policy.initial_response_hours * HOUR_MS
      : policy.update_cadence_hours * HOUR_MS;
  const warnAt = c.due - (step - warn);
  const l3At = c.due + (l3 - step);
  if (now >= l3At) return 3;
  if (now >= c.due) return 2;
  if (now >= warnAt) return 1;
  return 0;
}

function apply(t: Ticket, sla: SlaState): SlaState {
  t.sla = sla;
  return sla;
}

/**
 * Per-viewer serialization. A requester in the requester position never sees
 * levels or escalation context (spec 11.3): they get plain, safe text only.
 */
export function slaForViewer(rec: DbTicket, requesterPosition: boolean): SlaState {
  const sla = recomputeSla(rec);
  if (!requesterPosition) return sla;
  const t = rec.ticket;
  let label: string;
  if (sla.stopped) label = t.status === 'closed' ? 'Closed' : 'Cancelled';
  else if (t.status === 'resolved') label = 'Awaiting closure';
  else if (sla.paused) label = 'Timer paused';
  else label = sla.kind === 'initial_response' ? 'Awaiting first response' : 'In progress';
  return { ...sla, level: 0, kind: sla.kind, label };
}

/** Recompute every ticket (policy change / demo clock / test reset). */
export function recomputeAll(): void {
  for (const rec of db.tickets) recomputeSla(rec);
}

/** Convenience: recompute a ticket looked up by id (no-op when unknown). */
export function recomputeById(id: string): void {
  const rec = findTicket(id);
  if (rec) recomputeSla(rec);
}

/** Pause the timers (on hold / awaiting requester): remember the pause point. */
export function pauseTimers(rec: DbTicket): void {
  if (!rec.pause) rec.pause = { at: Date.now(), off: db.clockOffsetMs };
}

/**
 * Resume after a pause: push every outstanding deadline forward by the real
 * time spent paused. The demo-clock shift counters are NOT touched — they
 * only track clock subtractions, so a later `resetMockClock` still restores
 * exactly the clock-driven part while keeping the pause extension.
 */
export function resumeTimers(rec: DbTicket): void {
  const pause = rec.pause;
  if (!pause) return;
  const elapsed = Math.max(0, Date.now() - pause.at);
  if (rec.resp_due != null) rec.resp_due += elapsed;
  if (rec.update_due != null) rec.update_due += elapsed;
  rec.pause = null;
}
