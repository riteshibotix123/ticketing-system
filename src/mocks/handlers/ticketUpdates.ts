/**
 * Ticket update actions (spec 6.3 / 9.7): priority, ETA revision and the
 * start-work / awaiting-requester status toggle. Priority changes may escalate
 * immediately (tighter thresholds), so a level increase emits its escalation
 * event right here rather than waiting for the demo clock.
 */
import { http } from 'msw';
import type { Ticket, TicketAction } from '@/types/domain';
import { db, findDepartment, HOUR_MS } from '../db';
import {
  actorRef,
  addAudit,
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
import { pauseTimers, recomputeSla, resumeTimers } from '../sla';
import { requireUser } from './guard';
import { audit, futureMs, loadTicket, notifyRequester } from './ticketShared';
import { p } from './paths';

export const ticketUpdateHandlers = [
  http.post(p('/tickets/:id/priority'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      const rec = loadTicket(String(params.id));
      assertAction(rec, user, 'change_priority');
      const body = await readJson<{ priority?: string; reason?: string }>(request);
      const priority = str(body.priority);
      const reason = str(body.reason);
      if (!['low', 'medium', 'high', 'critical'].includes(priority)) {
        throw422({ priority: 'Choose a priority.' });
      }
      if (!reason) throw422({ reason: 'Priority changes need a reason.' });

      const t = rec.ticket;
      const before = t.sla.level;
      const oldPriority = t.priority;
      t.priority = priority as Ticket['priority'];
      pushEvent(rec, {
        actor: actorRef(user),
        type: 'audit',
        action: 'Priority changed',
        detail: `Priority ${oldPriority} → ${priority}. Reason: ${reason}`,
        public: true,
      });
      recomputeSla(rec);
      // New thresholds may escalate immediately; the scheduler only reacts to
      // demo-clock moves, so emit the level change here as well.
      if (t.sla.level > before) {
        pushEvent(rec, {
          actor: { id: 'system', name: 'System' },
          type: 'audit',
          action: `Escalation L${t.sla.level}`,
          detail: `Priority raised to ${priority} — escalation level now L${t.sla.level}`,
          public: false,
        });
        addAudit({
          actor: { id: 'system', name: 'System' },
          action: `Escalation L${t.sla.level}`,
          object_type: 'ticket',
          object_id: t.id,
          detail: `Escalated after priority change to ${priority}`,
        });
      }
      notifyRequester(
        rec,
        `Ticket ${t.id} priority is now ${priority}. Reason: ${reason}`,
        t.priority === 'critical',
      );
      if (t.priority === 'critical') {
        const dept = findDepartment(t.department_id);
        if (dept?.escalation_primary) {
          notifyUsers([dept.escalation_primary.id], {
            text: `Critical ticket ${t.id} (${t.title}) in ${dept.name}`,
            kind: 'escalation',
            critical: true,
            ticket_id: t.id,
          });
        }
      }
      audit(user, rec, 'ticket.priority_changed', `${oldPriority} → ${priority}`, { reason });
      return ok(ticketDto(rec, user), request);
    }),
  ),

  http.post(p('/tickets/:id/eta'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      const rec = loadTicket(String(params.id));
      assertAction(rec, user, 'revise_eta');
      const body = await readJson<{ eta?: string; reason?: string }>(request);
      const reason = str(body.reason);
      const fields: Record<string, string> = {};
      let ms = Number.NaN;
      try {
        ms = futureMs(body.eta, 'eta');
      } catch {
        fields.eta = 'Pick a valid time in the future.';
      }
      if (!reason) fields.reason = 'Every ETA change needs a reason.';
      if (Object.keys(fields).length > 0) throw422(fields);

      const t = rec.ticket;
      const oldEta = t.eta;
      t.eta = new Date(ms).toISOString();
      rec.eta_shift = 0;
      const now = Date.now();
      t.last_team_update_at = new Date(now).toISOString();
      rec.update_due = now + db.policy.update_cadence_hours * HOUR_MS;
      // Fresh deadlines start unshifted: `*_shift` only records demo-clock
      // subtractions applied AFTER the deadline was set (see db.ts).
      rec.update_shift = 0;
      rec.pause = null;
      pushEvent(rec, {
        actor: actorRef(user),
        type: 'audit',
        action: 'ETA revised',
        detail: `ETA ${oldEta ? fmtWhen(oldEta) : 'not set'} → ${fmtWhen(t.eta)}. Reason: ${reason}`,
        public: true,
      });
      recomputeSla(rec);
      notifyRequester(rec, `Ticket ${t.id} ETA is now ${fmtWhen(t.eta)}. Reason: ${reason}`);
      audit(user, rec, 'ticket.eta_revised', `ETA set to ${fmtWhen(t.eta)}`, { reason });
      return ok(ticketDto(rec, user), request);
    }),
  ),

  http.post(p('/tickets/:id/status'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      const rec = loadTicket(String(params.id));
      const body = await readJson<{ status?: string; checkpoint?: string }>(request);
      const next = str(body.status);
      const action: TicketAction = next === 'awaiting_requester' ? 'ask_requester' : 'start_work';
      assertAction(rec, user, action);
      if (next !== 'in_progress' && next !== 'awaiting_requester') {
        throw422({ status: 'Choose the new status.' });
      }

      const t = rec.ticket;
      const now = Date.now();
      t.status = next;
      if (next === 'in_progress') {
        resumeTimers(rec);
        t.last_team_update_at = new Date(now).toISOString();
        if (rec.update_due == null && t.acknowledged_at) {
          rec.update_due = now + db.policy.update_cadence_hours * HOUR_MS;
          rec.update_shift = 0;
        }
        pushEvent(rec, {
          actor: actorRef(user),
          type: 'audit',
          action: 'Work started',
          detail: `Work started by ${user.name}`,
          public: true,
        });
        notifyRequester(rec, `Work on ticket ${t.id} has started.`);
      } else {
        pauseTimers(rec);
        pushEvent(rec, {
          actor: actorRef(user),
          type: 'audit',
          action: 'Awaiting requester',
          detail: str(body.checkpoint)
            ? `Waiting for the requester. Next checkpoint ${fmtWhen(body.checkpoint)}`
            : 'Waiting for the requester to respond.',
          public: true,
        });
        notifyRequester(rec, `Ticket ${t.id} is waiting for your response.`);
      }
      recomputeSla(rec);
      audit(
        user,
        rec,
        next === 'in_progress' ? 'ticket.work_started' : 'ticket.awaiting_requester',
        `Status → ${next}`,
      );
      return ok(ticketDto(rec, user), request);
    }),
  ),
];
