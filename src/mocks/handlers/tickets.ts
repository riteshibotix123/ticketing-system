/**
 * Ticket list and creation (spec 6.3, 9.4, 9.5). The list applies scope,
 * filters, the urgency sort and pagination server-side; SLA is recomputed on
 * every read so the demo clock is always reflected without client maths.
 */
import { http } from 'msw';
import type { Paged, Ticket } from '@/types/domain';
import { db, findDepartment, HOUR_MS, nextTicketId, paginate, type DbTicket } from '../db';
import {
  actorRef,
  addAudit,
  notifyUsers,
  ok,
  pushEvent,
  qs,
  readJson,
  respond,
  str,
  throw422,
} from '../helpers';
import { byUrgency, defaultScope, scopedTickets, ticketDto } from '../access';
import { recomputeSla } from '../sla';
import { requireUser } from './guard';
import { resolveAttachments } from './ticketDetail';
import { p } from './paths';

/* ------------------------------------------------------------------ list */

/** sla_state filter ids from lib/sla.ts SLA_STATE_FILTERS. */
function matchesSlaState(rec: DbTicket, filter: string): boolean {
  const t = rec.ticket;
  const now = Date.now();
  switch (filter) {
    case 'unacknowledged':
      return !t.acknowledged_at;
    case 'warning':
      return t.sla.level === 1;
    case 'breached':
      return t.sla.level >= 2;
    case 'stale':
      return Boolean(t.acknowledged_at) && (isUpdateOverdue(rec, now) || isEtaOverdue(t, now));
    default:
      return true;
  }
}

function isUpdateOverdue(rec: DbTicket, now: number): boolean {
  return rec.update_due != null && rec.update_due <= now;
}

function isEtaOverdue(t: Ticket, now: number): boolean {
  return t.eta != null && Date.parse(t.eta) <= now;
}

function matchesFilters(rec: DbTicket, params: URLSearchParams): boolean {
  const t = rec.ticket;
  const q = str(params.get('q')).toLowerCase();
  if (q && !`${t.id} ${t.title} ${t.description}`.toLowerCase().includes(q)) return false;
  const statuses = params.getAll('status').filter(Boolean);
  if (statuses.length > 0 && !statuses.includes(t.status)) return false;
  const priorities = params.getAll('priority').filter(Boolean);
  if (priorities.length > 0 && !priorities.includes(t.priority)) return false;
  const dept = str(params.get('department_id'));
  if (dept && t.department_id !== dept) return false;
  const cat = str(params.get('category_id'));
  if (cat && t.category_id !== cat) return false;
  const slaState = str(params.get('sla_state'));
  if (slaState && !matchesSlaState(rec, slaState)) return false;
  const level = str(params.get('escalation_level'));
  if (level && String(t.sla.level) !== level) return false;
  const requester = str(params.get('requester_id'));
  if (requester && t.requester.id !== requester) return false;
  const assignee = str(params.get('assignee_id'));
  if (assignee && t.assignee?.id !== assignee) return false;
  const confidential = str(params.get('confidential'));
  if (confidential && (confidential === 'true') !== t.confidential) return false;
  if (str(params.get('overdue_eta')) === 'true' && !isEtaOverdue(t, Date.now())) return false;
  const from = str(params.get('created_from'));
  if (from && t.created_at < from) return false;
  const to = str(params.get('created_to'));
  if (to && t.created_at > to) return false;
  return true;
}

const SORTS: Record<string, (a: DbTicket, b: DbTicket) => number> = {
  urgency: byUrgency,
  newest: (a, b) => b.ticket.created_at.localeCompare(a.ticket.created_at),
  oldest: (a, b) => a.ticket.created_at.localeCompare(b.ticket.created_at),
};

/* ---------------------------------------------------------------- create */

interface CreateTicketBody {
  department_id?: string;
  category_id?: string;
  title?: string;
  description?: string;
  priority?: string;
  confidential?: boolean;
  attachment_ids?: string[];
}

const PRIORITIES = ['low', 'medium', 'high', 'critical'];

function validateCreate(body: CreateTicketBody): Record<string, string> {
  const fields: Record<string, string> = {};
  const dept = findDepartment(str(body.department_id));
  if (!dept) fields.department_id = 'Choose a department.';
  else if (!dept.active) fields.department_id = 'This department is not active.';
  else if (dept.spokes.length === 0) {
    // Requirement 15 / spec 10.3: no active Spoke -> cannot raise tickets there.
    fields.department_id = 'No active Spoke yet — this department cannot receive tickets.';
  }
  const category = dept?.categories.find((c) => c.id === str(body.category_id));
  if (!category) fields.category_id = 'Choose a category.';
  const title = str(body.title);
  if (title.length < 1 || title.length > 120) fields.title = 'Use 1 to 120 characters.';
  const description = str(body.description);
  if (description.length < 1 || description.length > 5000)
    fields.description = 'Use 1 to 5000 characters.';
  if (!PRIORITIES.includes(str(body.priority))) fields.priority = 'Choose a priority.';
  return fields;
}

/* -------------------------------------------------------------- handlers */

export const ticketHandlers = [
  http.get(p('/tickets'), ({ request }) =>
    respond(request, () => {
      const user = requireUser(request);
      const params = qs(request);
      const scope = str(params.get('scope')) || defaultScope(user);
      // scopedTickets throws 403 for scopes the caller may not open.
      const candidates = scopedTickets(user, scope).filter((rec) => {
        recomputeSla(rec);
        return matchesFilters(rec, params);
      });
      const sort = SORTS[str(params.get('sort'))] ?? byUrgency;
      const sorted = [...candidates].sort(sort);
      const page = paginate(
        sorted.map((rec) => ticketDto(rec, user)),
        params.get('page'),
        params.get('page_size'),
      );
      return ok(page satisfies Paged<Ticket>, request);
    }),
  ),

  http.post(p('/tickets'), ({ request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      const body = await readJson<CreateTicketBody>(request);
      const fields = validateCreate(body);
      if (Object.keys(fields).length > 0) throw422(fields);
      const dept = findDepartment(str(body.department_id))!;
      const category = dept.categories.find((c) => c.id === str(body.category_id))!;
      const now = Date.now();
      const rec: DbTicket = {
        ticket: {
          id: nextTicketId(dept.id),
          title: str(body.title),
          description: str(body.description),
          department_id: dept.id,
          category_id: category.id,
          category_name: category.name,
          priority: str(body.priority) as Ticket['priority'],
          status: 'new',
          confidential: body.confidential === true,
          requester: actorRef(user),
          owner: null,
          assignee: null,
          collaborators: [],
          created_at: new Date(now).toISOString(),
          sla_started_at: new Date(now).toISOString(),
          acknowledged_at: null,
          eta: null,
          last_team_update_at: null,
          resolved_at: null,
          closed_at: null,
          reopen_count: 0,
          hold: null,
          resolution_summary: null,
          sla: { level: 0, kind: null, paused: false, stopped: false, due_at: null, label: '' },
          allowed_actions: [],
          attachments: resolveAttachments(body.attachment_ids),
        },
        events: [],
        // Fresh deadline: no demo-clock shift has touched it yet (db.ts).
        resp_due: now + db.policy.initial_response_hours * HOUR_MS,
        resp_shift: 0,
        update_due: null,
        update_shift: 0,
        eta_shift: 0,
        pause: null,
        last_escalation: null,
      };

      pushEvent(rec, {
        actor: actorRef(user),
        type: 'audit',
        action: 'Created',
        detail: `${str(body.priority)} · ${category.name}`,
        public: true,
      });
      db.tickets.push(rec);
      recomputeSla(rec);

      const spokes = dept.spokes.map((s) => s.id);
      notifyUsers(spokes, {
        text: `New ticket ${rec.ticket.id} in ${dept.name} (${rec.ticket.priority}): ${rec.ticket.title}`,
        kind: 'ticket_created',
        critical: rec.ticket.priority === 'critical',
        ticket_id: rec.ticket.id,
      });
      if (rec.ticket.priority === 'critical' && dept.escalation_primary) {
        notifyUsers([dept.escalation_primary.id], {
          text: `Critical ticket ${rec.ticket.id} raised in ${dept.name} (${rec.ticket.title})`,
          kind: 'ticket_created',
          critical: true,
          ticket_id: rec.ticket.id,
        });
      }
      addAudit({
        actor: actorRef(user),
        action: 'ticket.created',
        object_type: 'ticket',
        object_id: rec.ticket.id,
        detail: `${rec.ticket.id} created in ${dept.name} (${category.name})`,
      });
      return ok(ticketDto(rec, user), request, 201);
    }),
  ),
];
