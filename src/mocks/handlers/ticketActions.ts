/**
 * Ticket routing actions (spec 6.3 / 9.7): acknowledge, assign and transfer.
 * Each re-checks `allowed_actions` on the server, records a timeline event,
 * audit entry and notifications, then returns the updated Ticket for the
 * acting viewer.
 */
import { http } from 'msw';
import { db, findDepartment, findUser, HOUR_MS, ref } from '../db';
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
import { recomputeSla } from '../sla';
import { requireUser } from './guard';
import {
  audit,
  assertAssignable,
  futureMs,
  loadTicket,
  notifyRequester,
  staffIds,
} from './ticketShared';
import { p } from './paths';

export const ticketActionHandlers = [
  http.post(p('/tickets/:id/acknowledge'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      const rec = loadTicket(String(params.id));
      assertAction(rec, user, 'acknowledge');
      const body = await readJson<{ eta?: string; no_eta_reason?: string; checkpoint?: string }>(
        request,
      );
      const now = Date.now();

      let etaIso: string | null = null;
      if (str(body.eta)) {
        etaIso = new Date(futureMs(body.eta, 'eta')).toISOString();
      } else {
        // Spec 10.4: no ETA needs a reason AND a next checkpoint.
        const fields: Record<string, string> = {};
        if (!str(body.no_eta_reason)) fields.no_eta_reason = 'Explain why no ETA can be committed.';
        if (!str(body.checkpoint)) fields.checkpoint = 'Set the next checkpoint.';
        if (Object.keys(fields).length > 0) throw422(fields);
      }

      const t = rec.ticket;
      t.acknowledged_at = new Date(now).toISOString();
      if (!t.owner) t.owner = actorRef(user);
      t.status = t.assignee ? 'assigned' : 'acknowledged';
      t.eta = etaIso;
      rec.eta_shift = 0;
      rec.resp_due = null; // initial response met
      rec.update_due = now + db.policy.update_cadence_hours * HOUR_MS;
      // Fresh deadlines start unshifted: `*_shift` only records demo-clock
      // subtractions applied AFTER the deadline was set (see db.ts).
      rec.update_shift = 0;

      const detail = etaIso
        ? `Owner ${t.owner?.name ?? user.name}, ETA ${fmtWhen(etaIso)}`
        : `Owner ${t.owner?.name ?? user.name}, no ETA — ${str(body.no_eta_reason)} (checkpoint ${fmtWhen(body.checkpoint)})`;
      pushEvent(rec, {
        actor: actorRef(user),
        type: 'audit',
        action: 'Acknowledged',
        detail,
        public: true,
      });
      recomputeSla(rec);
      notifyRequester(
        rec,
        `Ticket ${t.id} acknowledged. ${etaIso ? `ETA ${fmtWhen(etaIso)}.` : 'The team will update you at the next checkpoint.'}`,
      );
      audit(user, rec, 'ticket.acknowledged', detail);
      return ok(ticketDto(rec, user), request);
    }),
  ),

  http.post(p('/tickets/:id/assign'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      const rec = loadTicket(String(params.id));
      assertAction(rec, user, 'assign');
      const body = await readJson<{ assignee_id?: string; reason?: string }>(request);
      const assignee = findUser(str(body.assignee_id));
      if (!assignee) throw422({ assignee_id: 'Pick an active person.' });
      assertAssignable(assignee, rec.ticket.department_id);

      const t = rec.ticket;
      t.assignee = ref(assignee);
      if (t.status === 'new' || t.status === 'acknowledged') t.status = 'assigned';
      pushEvent(rec, {
        actor: actorRef(user),
        type: 'audit',
        action: 'Assigned',
        detail: str(body.reason)
          ? `Delegated to ${assignee.name}. ${str(body.reason)}`
          : `Delegated to ${assignee.name}. ${user.name} keeps supervisory access.`,
        public: true,
      });
      recomputeSla(rec);
      notifyUsers([assignee.id], {
        text: `Ticket ${t.id} assigned to you by ${user.name}: ${t.title}`,
        kind: 'assignment',
        critical: t.sla.level >= 2,
        ticket_id: t.id,
      });
      notifyRequester(rec, `Ticket ${t.id} delegated to ${assignee.name}.`);
      audit(
        user,
        rec,
        'ticket.assigned',
        `Delegated to ${assignee.name}`,
        str(body.reason) ? { reason: str(body.reason) } : undefined,
      );
      return ok(ticketDto(rec, user), request);
    }),
  ),

  http.post(p('/tickets/:id/transfer'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      const rec = loadTicket(String(params.id));
      assertAction(rec, user, 'transfer');
      const body = await readJson<{
        department_id?: string;
        category_id?: string;
        reason?: string;
      }>(request);
      const reason = str(body.reason);
      if (!reason) throw422({ reason: 'Transfers need a reason.' });
      const dept = findDepartment(str(body.department_id));
      if (!dept || !dept.active) throw422({ department_id: 'Choose an active department.' });
      if (dept.spokes.length === 0) {
        throw422({
          department_id: 'No active Spoke yet — this department cannot receive tickets.',
        });
      }
      const category =
        dept.categories.find((c) => c.id === str(body.category_id)) ?? dept.categories[0] ?? null;
      if (!category) throw422({ category_id: 'Pick a category in the new department.' });

      const t = rec.ticket;
      const fromName = findDepartment(t.department_id)?.name ?? t.department_id;
      t.department_id = dept.id;
      t.category_id = category.id;
      t.category_name = category.name;
      // The old assignee may not work the new queue; supervisory access stays.
      t.assignee = null;
      if (!t.acknowledged_at) {
        // Fresh queue, fresh response window.
        rec.resp_due = Date.now() + db.policy.initial_response_hours * HOUR_MS;
        rec.resp_shift = 0;
      }
      pushEvent(rec, {
        actor: actorRef(user),
        type: 'audit',
        action: 'Transferred',
        detail: `Transferred from ${fromName} to ${dept.name} (${category.name}). Reason: ${reason}`,
        public: true,
      });
      recomputeSla(rec);
      notifyRequester(rec, `Ticket ${t.id} transferred to ${dept.name}. Reason: ${reason}`);
      notifyUsers([...dept.spokes.map((s) => s.id), ...staffIds(rec)], {
        text: `Ticket ${t.id} transferred into ${dept.name}: ${t.title}`,
        kind: 'transfer',
        critical: t.sla.level >= 2,
        ticket_id: t.id,
      });
      audit(user, rec, 'ticket.transferred', `From ${fromName} to ${dept.name}`, { reason });
      return ok(ticketDto(rec, user), request);
    }),
  ),
];
