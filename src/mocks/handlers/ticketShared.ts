/**
 * Helpers shared by the ticket mutation handler groups (actions + close):
 * loading a record, the requester/staff notification copy and the audit
 * emitter, plus the field validators used by several action bodies.
 */
import { findTicket, type DbTicket, type DbUser } from '../db';
import { actorRef, addAudit, notifyUsers, str, throw404, throw422 } from '../helpers';

export function loadTicket(id: string): DbTicket {
  const rec = findTicket(id);
  if (!rec) throw404();
  return rec;
}

export function staffIds(rec: DbTicket): string[] {
  return [rec.ticket.owner?.id, rec.ticket.assignee?.id].filter((x): x is string => Boolean(x));
}

export function notifyRequester(rec: DbTicket, text: string, critical = false): void {
  notifyUsers([rec.ticket.requester.id], {
    text,
    kind: 'ticket_update',
    critical,
    ticket_id: rec.ticket.id,
  });
}

export function audit(
  user: DbUser,
  rec: DbTicket,
  action: string,
  detail: string,
  extra?: { reason?: string },
): void {
  addAudit({
    actor: actorRef(user),
    action,
    object_type: 'ticket',
    object_id: rec.ticket.id,
    detail,
    ...(extra?.reason ? { reason: extra.reason } : {}),
  });
}

/** Validate a future ISO timestamp, returning ms since epoch. */
export function futureMs(raw: unknown, field: string): number {
  const value = str(raw);
  const ms = Date.parse(value);
  if (!value || Number.isNaN(ms)) throw422({ [field]: 'Pick a valid date and time.' });
  if (ms <= Date.now()) throw422({ [field]: 'Pick a time in the future.' });
  return ms;
}

/** An assignee must be an active member of the department, Admin or Super Admin. */
export function assertAssignable(user: DbUser, departmentId: string): void {
  const eligible =
    user.state === 'active' &&
    (user.department_id === departmentId ||
      user.spoke_departments.includes(departmentId) ||
      user.roles.includes('admin') ||
      user.roles.includes('super_admin'));
  if (!eligible) {
    throw422({ assignee_id: 'Pick an active member of this department.' });
  }
}
