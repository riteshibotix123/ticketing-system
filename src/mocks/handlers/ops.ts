/**
 * Notifications, audit log and role dashboards (spec 6.4, 9.3, 9.10, 9.14).
 * Notifications are per-user with a `count_only` fast path; the audit log is
 * Admin/Super Admin only and read-only; dashboards aggregate on the server.
 */
import { http } from 'msw';
import type {
  AdminDashboard,
  EmployeeDashboard,
  SpokeDashboard,
  Ticket,
  TimelineEvent,
} from '@/types/domain';
import { db, HOUR_MS, paginate, type DbTicket, type DbUser } from '../db';
import { ok, publicNotification, qs, respond, str, throw403, throw404 } from '../helpers';
import { can, scopedTickets, ticketDto, timelineFor } from '../access';
import { recomputeSla } from '../sla';
import { requireUser } from './guard';
import { p } from './paths';

/* --------------------------------------------------------- notifications */

function myNotifications(user: DbUser) {
  return db.notifications.filter((n) => n.user_id === user.id).sort((a, b) => b.seq - a.seq);
}

export const notificationHandlers = [
  http.get(p('/notifications'), ({ request }) =>
    respond(request, () => {
      const user = requireUser(request);
      const params = qs(request);
      const unreadOnly = str(params.get('unread')) === 'true';
      const rows = myNotifications(user).filter((n) => !unreadOnly || !n.read);
      if (params.get('count_only') === 'true') {
        return ok({ count: rows.filter((n) => !n.read).length }, request);
      }
      return ok(
        paginate(rows.map(publicNotification), params.get('page'), params.get('page_size')),
        request,
      );
    }),
  ),

  http.post(p('/notifications/:id/read'), ({ params, request }) =>
    respond(request, () => {
      const user = requireUser(request);
      const row = db.notifications.find((n) => n.id === String(params.id) && n.user_id === user.id);
      if (!row) throw404();
      row.read = true;
      return ok(publicNotification(row), request);
    }),
  ),

  http.post(p('/notifications/read-all'), ({ request }) =>
    respond(request, () => {
      const user = requireUser(request);
      let updated = 0;
      for (const row of myNotifications(user)) {
        if (!row.read) {
          row.read = true;
          updated += 1;
        }
      }
      return ok({ updated }, request);
    }),
  ),
];

/* ---------------------------------------------------------------- audit */

export const auditHandlers = [
  http.get(p('/audit'), ({ request }) =>
    respond(request, () => {
      const user = requireUser(request);
      if (!can(user, 'audit.view_all'))
        throw403('Only Admins and Super Admins can view the audit log.');
      const params = qs(request);
      const q = str(params.get('q')).toLowerCase();
      const actorId = str(params.get('actor_id'));
      const action = str(params.get('action'));
      const ticketId = str(params.get('ticket_id'));
      const from = str(params.get('from'));
      const to = str(params.get('to'));
      const rows = [...db.audit]
        .sort((a, b) => b.seq - a.seq)
        .filter((e) => {
          if (q && !`${e.action} ${e.detail ?? ''} ${e.reason ?? ''}`.toLowerCase().includes(q))
            return false;
          if (actorId && e.actor.id !== actorId) return false;
          if (action && !e.action.toLowerCase().includes(action.toLowerCase())) return false;
          if (ticketId && e.object_id !== ticketId) return false;
          if (from && e.at < from) return false;
          if (to && e.at > to) return false;
          return true;
        })
        .map(stripSeq);
      return ok(paginate(rows, params.get('page'), params.get('page_size')), request);
    }),
  ),
];

/** Drop the internal monotonic seq before serving an audit entry. */
function stripSeq(entry: (typeof db.audit)[number]): Omit<(typeof db.audit)[number], 'seq'> {
  const { seq, ...rest } = entry;
  void seq;
  return rest;
}

/* ------------------------------------------------------------ dashboards */

function open(rec: DbTicket): boolean {
  const s = rec.ticket.status;
  return s !== 'resolved' && s !== 'closed' && s !== 'cancelled';
}

function etaOverdue(rec: DbTicket): boolean {
  const eta = rec.ticket.eta;
  return eta != null && Date.parse(eta) <= Date.now();
}

function stale(rec: DbTicket): boolean {
  const last = rec.ticket.last_team_update_at ?? rec.ticket.created_at;
  return Date.now() - Date.parse(last) > db.policy.update_cadence_hours * HOUR_MS;
}

function attention(recs: DbTicket[], user: DbUser, limit = 8): Ticket[] {
  return [...recs]
    .sort(
      (a, b) =>
        b.ticket.sla.level - a.ticket.sla.level ||
        a.ticket.sla_started_at.localeCompare(b.ticket.sla_started_at),
    )
    .slice(0, limit)
    .map((rec) => ticketDto(rec, user));
}

function recomputeVisible(recs: DbTicket[]): DbTicket[] {
  recs.forEach((rec) => recomputeSla(rec));
  return recs;
}

export const dashboardHandlers = [
  http.get(p('/dashboard/admin'), ({ request }) =>
    respond(request, () => {
      const user = requireUser(request);
      if (!can(user, 'reports.view_org'))
        throw403('Only Admins and Super Admins can view the organisation dashboard.');
      const all = recomputeVisible([...db.tickets]);
      const openRecs = all.filter(open);
      const acknowledged = all.filter((r) => r.ticket.acknowledged_at);
      const responseSeconds = acknowledged.map(
        (r) => (Date.parse(r.ticket.acknowledged_at!) - Date.parse(r.ticket.created_at)) / 1000,
      );
      const met = openRecs.filter((r) => r.ticket.sla.level < 2).length;
      const reopens = all.filter((r) => r.ticket.reopen_count > 0).length;
      const dashboard: AdminDashboard = {
        open_count: openRecs.length,
        sla_met_pct: openRecs.length === 0 ? 100 : Math.round((met / openRecs.length) * 100),
        avg_initial_response_seconds:
          responseSeconds.length === 0
            ? 0
            : Math.round(responseSeconds.reduce((a, b) => a + b, 0) / responseSeconds.length),
        breached_count: openRecs.filter((r) => r.ticket.sla.level >= 2).length,
        l3_count: openRecs.filter((r) => r.ticket.sla.level === 3).length,
        stale_count: openRecs.filter(stale).length,
        reopen_rate_pct: all.length === 0 ? 0 : Math.round((reopens / all.length) * 100),
        by_department: db.departments.map((d) => {
          const rows = openRecs.filter((r) => r.ticket.department_id === d.id);
          return {
            department_id: d.id,
            name: d.name,
            on_track: rows.filter((r) => r.ticket.sla.level === 0).length,
            warning: rows.filter((r) => r.ticket.sla.level === 1).length,
            breached: rows.filter((r) => r.ticket.sla.level >= 2).length,
          };
        }),
        attention: attention(openRecs, user),
      };
      return ok(dashboard, request);
    }),
  ),

  http.get(p('/dashboard/spoke'), ({ request }) =>
    respond(request, () => {
      const user = requireUser(request);
      const mine = recomputeVisible(
        db.tickets.filter((rec) => user.spoke_departments.includes(rec.ticket.department_id)),
      );
      const dashboard: SpokeDashboard = {
        new_unacknowledged: mine.filter((r) => r.ticket.status === 'new').length,
        approaching_sla: mine.filter((r) => r.ticket.sla.level === 1).length,
        breached: mine.filter((r) => r.ticket.sla.level >= 2).length,
        stale_or_eta_overdue: mine.filter((r) => open(r) && (stale(r) || etaOverdue(r))).length,
        awaiting_requester: mine.filter((r) => r.ticket.status === 'awaiting_requester').length,
        on_hold: mine.filter((r) => r.ticket.status === 'on_hold').length,
        resolved_pending_closure: mine.filter((r) => r.ticket.status === 'resolved').length,
        attention: attention(mine.filter(open), user),
      };
      return ok(dashboard, request);
    }),
  ),

  http.get(p('/dashboard/employee'), ({ request }) =>
    respond(request, () => {
      const user = requireUser(request);
      const mine = recomputeVisible(scopedTickets(user, 'mine'));
      const recent: TimelineEvent[] = mine
        .flatMap((rec) => timelineFor(rec, user).map((ev) => ev))
        .sort((a, b) => b.at.localeCompare(a.at))
        .slice(0, 10);
      const dashboard: EmployeeDashboard = {
        open: mine.filter(open).length,
        awaiting_my_response: mine.filter((r) => r.ticket.status === 'awaiting_requester').length,
        resolved_to_confirm: mine.filter((r) => r.ticket.status === 'resolved').length,
        closed: mine.filter((r) => r.ticket.status === 'closed' || r.ticket.status === 'cancelled')
          .length,
        recent_updates: recent,
        attention: attention(mine.filter(open), user),
      };
      return ok(dashboard, request);
    }),
  ),
];
