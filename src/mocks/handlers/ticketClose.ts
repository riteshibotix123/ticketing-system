/**
 * Closing-lifecycle endpoints (spec 6.3 / 9.7): hold, resolve, confirm
 * closure, reopen and cancel. Hold/resume moves the SLA pause point; resolve
 * stops the timers but leaves the ticket open for the requester's confirmation.
 */
import { http } from 'msw';
import { db, HOUR_MS } from '../db';
import {
  actorRef,
  fmtWhen,
  notifyUsers,
  ok,
  pushEvent,
  readJson,
  respond,
  str,
  throw422,
} from '../helpers';
import { assertAction, ticketDto } from '../access';
import { pauseTimers, recomputeSla } from '../sla';
import { requireUser } from './guard';
import { audit, loadTicket, notifyRequester } from './ticketShared';
import { p } from './paths';

/** Staff (owner/assignee/spokes) minus the actor, for "responsible team" pings. */
function teamIds(rec: ReturnType<typeof loadTicket>, exceptId: string): string[] {
  const deptSpokes = db.users
    .filter((u) => u.state === 'active' && u.spoke_departments.includes(rec.ticket.department_id))
    .map((u) => u.id);
  return [...new Set([rec.ticket.owner?.id, rec.ticket.assignee?.id, ...deptSpokes])].filter(
    (x): x is string => Boolean(x) && x !== exceptId,
  );
}

export const ticketCloseHandlers = [
  http.post(p('/tickets/:id/hold'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      const rec = loadTicket(String(params.id));
      assertAction(rec, user, 'hold');
      const body = await readJson<{ reason?: string; review_date?: string }>(request);
      const reason = str(body.reason);
      const reviewRaw = str(body.review_date);
      const fields: Record<string, string> = {};
      if (!reason) fields.reason = 'Hold needs a reason.';
      const reviewMs = Date.parse(reviewRaw);
      if (!reviewRaw || Number.isNaN(reviewMs)) fields.review_date = 'Pick a next review date.';
      else if (reviewMs <= Date.now()) fields.review_date = 'Pick a date in the future.';
      if (Object.keys(fields).length > 0) throw422(fields);

      const t = rec.ticket;
      pauseTimers(rec);
      t.status = 'on_hold';
      t.hold = { reason, review_date: new Date(reviewMs).toISOString() };
      pushEvent(rec, {
        actor: actorRef(user),
        type: 'audit',
        action: 'On hold',
        detail: `${reason} Review on ${fmtWhen(t.hold.review_date)}. SLA timer paused.`,
        public: true,
      });
      recomputeSla(rec);
      notifyRequester(
        rec,
        `Ticket ${t.id} is on hold. Reason: ${reason} The team will review it on ${fmtWhen(t.hold.review_date)}.`,
      );
      audit(user, rec, 'ticket.on_hold', 'SLA timer paused', { reason });
      return ok(ticketDto(rec, user), request);
    }),
  ),

  http.post(p('/tickets/:id/resolve'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      const rec = loadTicket(String(params.id));
      assertAction(rec, user, 'resolve');
      const body = await readJson<{ summary?: string }>(request);
      const summary = str(body.summary);
      if (!summary) throw422({ summary: 'A resolution summary is required.' });

      const t = rec.ticket;
      const now = Date.now();
      t.status = 'resolved';
      t.resolved_at = new Date(now).toISOString();
      t.resolution_summary = summary;
      t.hold = null;
      rec.pause = null;
      t.last_team_update_at = new Date(now).toISOString();
      pushEvent(rec, {
        actor: actorRef(user),
        type: 'audit',
        action: 'Resolved',
        detail: summary,
        public: true,
      });
      recomputeSla(rec);
      notifyRequester(rec, `Ticket ${t.id} is resolved. Please confirm the closure or reopen it.`);
      audit(user, rec, 'ticket.resolved', 'Resolution summary recorded');
      return ok(ticketDto(rec, user), request);
    }),
  ),

  http.post(p('/tickets/:id/confirm-closure'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      const rec = loadTicket(String(params.id));
      assertAction(rec, user, 'confirm_closure');
      const t = rec.ticket;
      t.status = 'closed';
      t.closed_at = new Date().toISOString();
      t.hold = null;
      pushEvent(rec, {
        actor: actorRef(user),
        type: 'audit',
        action: 'Closed',
        detail: `Confirmed closed by ${user.name}`,
        public: true,
      });
      recomputeSla(rec);
      notifyUsers(teamIds(rec, user.id), {
        text: `Ticket ${t.id} confirmed closed by the requester.`,
        kind: 'ticket_update',
        ticket_id: t.id,
      });
      audit(user, rec, 'ticket.closed', 'Closure confirmed by requester');
      return ok(ticketDto(rec, user), request);
    }),
  ),

  http.post(p('/tickets/:id/reopen'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      const rec = loadTicket(String(params.id));
      assertAction(rec, user, 'reopen');
      const body = await readJson<{ reason?: string }>(request);
      const reason = str(body.reason);
      if (!reason) throw422({ reason: 'Reopening needs a reason.' });

      const t = rec.ticket;
      const now = Date.now();
      t.status = 'reopened';
      t.reopen_count += 1;
      t.resolved_at = null;
      t.closed_at = null;
      t.hold = null;
      rec.pause = null;
      // Timers restart: acknowledged tickets resume the update cadence, fresh
      // ones restart the initial-response window.
      if (t.acknowledged_at) {
        rec.update_due = now + db.policy.update_cadence_hours * HOUR_MS;
        rec.update_shift = 0;
      } else {
        rec.resp_due = now + db.policy.initial_response_hours * HOUR_MS;
        rec.resp_shift = 0;
      }
      pushEvent(rec, {
        actor: actorRef(user),
        type: 'audit',
        action: 'Reopened',
        detail: `Reopened by ${user.name}. Reason: ${reason}`,
        public: true,
      });
      recomputeSla(rec);
      notifyUsers(teamIds(rec, user.id), {
        text: `Ticket ${t.id} was reopened: ${t.title}`,
        kind: 'ticket_update',
        critical: t.sla.level >= 2,
        ticket_id: t.id,
      });
      audit(user, rec, 'ticket.reopened', 'Ticket reopened', { reason });
      return ok(ticketDto(rec, user), request);
    }),
  ),

  http.post(p('/tickets/:id/cancel'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      const rec = loadTicket(String(params.id));
      assertAction(rec, user, 'cancel');
      const body = await readJson<{ reason?: string }>(request);
      const reason = str(body.reason);
      if (!reason) throw422({ reason: 'Cancelling needs a reason.' });

      const t = rec.ticket;
      t.status = 'cancelled';
      t.closed_at = new Date().toISOString();
      t.hold = null;
      rec.pause = null;
      pushEvent(rec, {
        actor: actorRef(user),
        type: 'audit',
        action: 'Cancelled',
        detail: `Cancelled by ${user.name}. Reason: ${reason}`,
        public: true,
      });
      recomputeSla(rec);
      notifyUsers(teamIds(rec, user.id), {
        text: `Ticket ${t.id} was cancelled: ${t.title}`,
        kind: 'ticket_update',
        ticket_id: t.id,
      });
      audit(user, rec, 'ticket.cancelled', 'Ticket cancelled', { reason });
      return ok(ticketDto(rec, user), request);
    }),
  ),
];
