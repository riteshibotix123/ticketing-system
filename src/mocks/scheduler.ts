/**
 * Demo clock (spec 14). The browser has NO virtual clock — countdowns read the
 * real clock against `sla.due_at`. So advancing the clock:
 *   1. adds `hours` to db.clockOffsetMs,
 *   2. shifts every outstanding deadline BACK by the same amount
 *      (resp_due, update_due, ticket.eta) so a real-clock countdown immediately
 *      reads e.g. "Response overdue 6h",
 *   3. recomputes every ticket's sla level/kind/label,
 *   4. emits escalation timeline events (public:false), notifications and audit
 *      entries for level increases (and the 24h repeat from spec 11.2).
 * Paused (on_hold / awaiting_requester / resolved) tickets are frozen: their
 * deadlines do not move while the timer is paused — that is what "paused" means.
 * Reset undoes exactly the shift that was applied (per-deadline `*_shift`),
 * making advance/reset deterministic and idempotent.
 */
import type { DbTicket } from './db';
import { db, HOUR_MS, spokesOf, usersWithRole, findDepartment } from './db';
import { recomputeSla } from './sla';
import { addAudit, fmtWhen, notifyUsers, pushEvent } from './helpers';

const REPEAT_MS = 24 * HOUR_MS;

function isFrozen(rec: DbTicket): boolean {
  const s = rec.ticket.status;
  return (
    s === 'on_hold' ||
    s === 'awaiting_requester' ||
    s === 'resolved' ||
    s === 'closed' ||
    s === 'cancelled'
  );
}

export function advanceMockClock(hours: number): number {
  const amount = Math.round(hours * HOUR_MS);
  if (!Number.isFinite(amount) || amount <= 0) return db.clockOffsetMs;
  db.clockOffsetMs += amount;
  const now = Date.now();

  for (const rec of db.tickets) {
    if (!isFrozen(rec)) {
      if (rec.resp_due != null) {
        rec.resp_due -= amount;
        rec.resp_shift += amount;
      }
      if (rec.update_due != null) {
        rec.update_due -= amount;
        rec.update_shift += amount;
      }
      if (rec.ticket.eta) {
        rec.ticket.eta = new Date(Date.parse(rec.ticket.eta) - amount).toISOString();
        rec.eta_shift += amount;
      }
    }
    const before = rec.ticket.sla.level;
    const after = recomputeSla(rec);
    if (after.level > before) emitEscalation(rec, after.level, now);
    else maybeRepeatEscalation(rec, after.level, now);
  }
  return db.clockOffsetMs;
}

/** Reset: undo the applied shift on every deadline, recompute, emit nothing. */
export function resetMockClock(): number {
  for (const rec of db.tickets) {
    if (rec.resp_due != null && rec.resp_shift !== 0) rec.resp_due += rec.resp_shift;
    rec.resp_shift = 0;
    if (rec.update_due != null && rec.update_shift !== 0) rec.update_due += rec.update_shift;
    rec.update_shift = 0;
    if (rec.ticket.eta && rec.eta_shift !== 0) {
      rec.ticket.eta = new Date(Date.parse(rec.ticket.eta) + rec.eta_shift).toISOString();
    }
    rec.eta_shift = 0;
    rec.last_escalation = null;
    recomputeSla(rec);
  }
  db.clockOffsetMs = 0;
  return 0;
}

/* ------------------------------------------------------------- escalations */

function maybeRepeatEscalation(rec: DbTicket, level: 0 | 1 | 2 | 3, now: number): void {
  // Spec 11.2: escalations repeat every 24h (virtual hours, so +24h demo clock).
  if (level < 1) return;
  const last = rec.last_escalation;
  if (!last || last.level !== level) return;
  const virtualElapsed = now - last.at + (db.clockOffsetMs - last.off);
  if (virtualElapsed >= REPEAT_MS) emitEscalation(rec, level, now, true);
}

function emitEscalation(rec: DbTicket, level: 0 | 1 | 2 | 3, now: number, repeat = false): void {
  if (level < 1) return;
  const t = rec.ticket;
  const kindLabel =
    t.sla.kind === 'initial_response'
      ? 'initial response'
      : t.sla.kind === 'eta'
        ? 'ETA'
        : 'update cadence';
  const detail = `L${level} ${kindLabel} escalation${repeat ? ' (repeat)' : ''} — due ${t.sla.due_at ? fmtWhen(t.sla.due_at) : '—'}`;

  // Timeline event is always internal (public:false — spec 9.8).
  pushEvent(rec, {
    actor: { id: 'system', name: 'System' },
    type: 'audit',
    action: `Escalation L${level}`,
    detail,
    public: false,
  });

  addAudit({
    actor: { id: 'system', name: 'System' },
    action: `Escalation L${level}`,
    object_type: 'ticket',
    object_id: t.id,
    detail,
  });

  for (const user of escalationRecipients(rec, level)) {
    notifyUsers([user.id], {
      // Copy deck: "L{n} {kind} on {id} ({title})". Confidential tickets show
      // only the ID + a generic line to users who cannot open the content.
      text: confidentialText(rec, user, `L${level} ${kindLabel} on ${t.id} (${t.title})`),
      kind: 'escalation',
      critical: level >= 2,
      ticket_id: t.id,
    });
  }
  rec.last_escalation = { at: now, off: db.clockOffsetMs, level };
}

/**
 * Spec 1.3.4 recipients:
 * L1 → owner + department Spokes.
 * L2 → Spokes + Admins + the department's escalation contact (backup, then
 *      Admin, then Super Admin fallbacks).
 * L3 → Admins + the Super Admin / CXO group (the CEO seed is a super_admin).
 */
function escalationRecipients(rec: DbTicket, level: 0 | 1 | 2 | 3): { id: string }[] {
  const t = rec.ticket;
  const dept = findDepartment(t.department_id);
  const spokes = spokesOf(t.department_id).map((u) => ({ id: u.id }));
  const admins = usersWithRole('admin').map((u) => ({ id: u.id }));
  const supers = usersWithRole('super_admin').map((u) => ({ id: u.id }));
  const contact = dept?.escalation_contact ? [{ id: dept.escalation_contact.id }] : [];

  let list: { id: string }[];
  if (level === 1) {
    const owner = t.owner ? [{ id: t.owner.id }] : [];
    list = [...owner, ...spokes];
  } else if (level === 2) {
    const fallback = contact.length > 0 ? contact : [...admins, ...supers];
    list = [...spokes, ...admins, ...fallback];
  } else {
    list = [...admins, ...supers];
  }
  const ids = new Set<string>();
  const unique: { id: string }[] = [];
  for (const r of list) {
    if (!ids.has(r.id)) {
      ids.add(r.id);
      unique.push(r);
    }
  }
  return unique;
}

function confidentialText(rec: DbTicket, user: { id: string }, full: string): string {
  if (!rec.ticket.confidential) return full;
  const u = db.users.find((x) => x.id === user.id);
  const allowed =
    rec.ticket.requester.id === user.id ||
    rec.ticket.owner?.id === user.id ||
    rec.ticket.assignee?.id === user.id ||
    rec.ticket.collaborators.some((c) => c.id === user.id) ||
    Boolean(u?.roles.includes('super_admin'));
  return allowed ? full : `New escalation on ${rec.ticket.id}. Open the ticket for details.`;
}
