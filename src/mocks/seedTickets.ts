/**
 * Seeded tickets + timelines (spec section 14): 14 tickets covering on track,
 * approaching SLA, breached L2, persistent L3, acknowledged-but-stale, ETA
 * overdue, awaiting requester, on hold, resolved awaiting confirmation, closed,
 * reopened, cancelled, a confidential HR ticket and a Critical security ticket.
 *
 * Ticket IDs: `IBX-XXX-2026-NNNNNN` where XXX is the department id uppercased
 * and padded right with 'X' to 3 chars ('IT' -> 'ITX', 'HR' -> 'HRX').
 * The 6-digit suffix increments globally, so new tickets continue at 000015.
 */
import type { Attachment, Priority, Ticket, TicketStatus, TimelineEvent } from '@/types/domain';
import {
  db,
  findUser,
  HOUR_MS,
  nextTicketId,
  ref,
  spokesOf,
  type DbTicket,
  type DbUser,
} from './db';
import { recomputeSla } from './sla';
import { addAudit, fmtWhen, notifyUsers, pushEvent } from './helpers';

/** Seed anchors to "now" so relative ages always look right on first load. */
const T0 = Date.now();
const agoIso = (h: number): string => new Date(T0 - h * HOUR_MS).toISOString();
const inIso = (h: number): string => new Date(T0 + h * HOUR_MS).toISOString();

interface SeedEvent {
  /** Hours before seed time. */
  h: number;
  /** User id or 'system'. */
  actor: string;
  action: string;
  detail?: string;
  body?: string;
  type?: TimelineEvent['type'];
  public?: boolean;
}

interface SeedEscalation {
  level: 0 | 1 | 2 | 3;
  /** Hours before seed time. */
  h: number;
  /** Escalation kind text for the notification, e.g. 'initial response'. */
  kind: string;
}

interface SeedTicket {
  dept: string;
  cat: string;
  title: string;
  description: string;
  priority: Priority;
  status: TicketStatus;
  requester: string;
  createdH: number;
  confidential?: boolean;
  owner?: string;
  assignee?: string;
  /** Hours ago of the acknowledgement. */
  ackH?: number;
  /** Hours relative to now (negative = already overdue). */
  etaH?: number;
  /** Hours ago of the last team update (defaults to ackH). */
  updateH?: number;
  resolvedH?: number;
  closedH?: number;
  reopenCount?: number;
  hold?: { reason: string; reviewH: number };
  summary?: string;
  escalation?: SeedEscalation;
  attachments?: Attachment[];
  events: SeedEvent[];
}

const ATT_SCREENSHOT: Attachment = {
  id: 'att-seed-1',
  name: 'vpn-error.png',
  size: 184_320,
  mime: 'image/png',
  scan_status: 'clean',
};

const SPECS: SeedTicket[] = [
  {
    // 1 — on track, acknowledged, delegated, ETA in the future
    dept: 'IT',
    cat: 'c-it-4',
    title: 'VPN disconnects every few minutes from home',
    description:
      'Since this morning the VPN drops every 5-10 minutes on my home broadband. Reconnecting works but it breaks calls and uploads.',
    priority: 'medium',
    status: 'in_progress',
    requester: 'u-asha',
    createdH: 5,
    owner: 'u-rohan',
    assignee: 'u-dev',
    ackH: 4.5,
    etaH: 8,
    updateH: 1,
    attachments: [ATT_SCREENSHOT],
    events: [
      { h: 4.5, actor: 'u-rohan', action: 'Acknowledged' },
      {
        h: 4,
        actor: 'u-dev',
        action: 'Comment',
        body: "Thanks — I can see the drops on the gateway. Rolling back yesterday's profile change now.",
      },
      {
        h: 1,
        actor: 'u-rohan',
        action: 'Internal note',
        type: 'internal_note',
        public: false,
        body: 'ISP issue likely; keep the fallback LTE route until confirmed.',
      },
    ],
  },
  {
    // 2 — approaching SLA: unacknowledged for 19h, L1 warning at 18h
    dept: 'FIN',
    cat: 'c-fin-1',
    title: 'October reimbursement not credited',
    description:
      'My October reimbursement (claim #4471) was approved on the 2nd but has not reached my account yet.',
    priority: 'high',
    status: 'new',
    requester: 'u-meera',
    createdH: 19,
    escalation: { level: 1, h: 1, kind: 'initial response' },
    events: [{ h: 1, actor: 'system', action: 'Escalation L1', public: false }],
  },
  {
    // 3 — breached L2: unacknowledged for 27h (L1 at 18h, L2 at 24h)
    dept: 'FAC',
    cat: 'c-fac-2',
    title: 'Meeting room AC broken in Block C',
    description:
      'Room C-302 is unusable above 32°C — the AC has not run for two days and we have board meetings booked.',
    priority: 'high',
    status: 'new',
    requester: 'u-asha',
    createdH: 27,
    escalation: { level: 2, h: 3, kind: 'initial response' },
    events: [
      { h: 9, actor: 'system', action: 'Escalation L1', public: false },
      { h: 3, actor: 'system', action: 'Escalation L2', public: false },
    ],
  },
  {
    // 4 — persistent L3: acknowledged long ago, no update for 50h
    dept: 'IT',
    cat: 'c-it-3',
    title: 'Licence seats exhausted for the design team',
    description:
      'Six designers cannot launch the editor — the floating licence pool is exhausted during peak hours.',
    priority: 'low',
    status: 'acknowledged',
    requester: 'u-meera',
    createdH: 52,
    owner: 'u-isha',
    ackH: 50,
    updateH: 50,
    escalation: { level: 3, h: 2, kind: 'update cadence' },
    events: [
      {
        h: 50,
        actor: 'u-isha',
        action: 'Acknowledged',
        detail:
          'Owner Isha Gupta, no ETA yet: waiting on procurement. Next checkpoint: vendor quote by tomorrow morning.',
      },
      { h: 26, actor: 'system', action: 'Escalation L2', public: false },
      { h: 2, actor: 'system', action: 'Escalation L3', public: false },
    ],
  },
  {
    // 5 — acknowledged but stale: update cadence breached 2h ago
    dept: 'FIN',
    cat: 'c-fin-3',
    title: 'Finance system access for new analyst',
    description:
      'The new analyst cannot open the ledger app — access request FIN-2291 is still pending provisioning.',
    priority: 'medium',
    status: 'in_progress',
    requester: 'u-asha',
    createdH: 30,
    owner: 'u-sanjay',
    ackH: 28,
    updateH: 26,
    escalation: { level: 2, h: 2, kind: 'update cadence' },
    events: [
      { h: 28, actor: 'u-sanjay', action: 'Acknowledged' },
      { h: 8, actor: 'system', action: 'Escalation L1', public: false },
      { h: 2, actor: 'system', action: 'Escalation L2', public: false },
    ],
  },
  {
    // 6 — ETA overdue (L2 via the eta rule)
    dept: 'LGL',
    cat: 'c-lgl-1',
    title: 'Vendor contract review for Q4 renewal',
    description:
      'The vendor sent the renewal draft; Legal review was due before the procurement freeze.',
    priority: 'high',
    status: 'in_progress',
    requester: 'u-meera',
    createdH: 40,
    owner: 'u-aarav',
    assignee: 'u-aarav',
    ackH: 36,
    etaH: -2,
    updateH: 4,
    escalation: { level: 2, h: 2, kind: 'ETA' },
    events: [
      { h: 36, actor: 'u-aarav', action: 'Acknowledged' },
      {
        h: 4,
        actor: 'u-aarav',
        action: 'Comment',
        body: 'Redlines are almost done — two liability clauses still need the vendor sign-off.',
      },
      { h: 2, actor: 'system', action: 'Escalation L2', public: false },
    ],
  },
  {
    // 7 — awaiting requester (timer paused)
    dept: 'IT',
    cat: 'c-it-1',
    title: 'SSO access for the analytics dashboard',
    description: 'Access needs the reporting manager approval — replying here speeds things up.',
    priority: 'medium',
    status: 'awaiting_requester',
    requester: 'u-meera',
    createdH: 20,
    owner: 'u-rohan',
    ackH: 18,
    updateH: 16,
    events: [
      { h: 18, actor: 'u-rohan', action: 'Acknowledged' },
      {
        h: 16,
        actor: 'u-rohan',
        action: 'Awaiting requester',
        detail: 'Please confirm which reports you need access to.',
      },
    ],
  },
  {
    // 8 — on hold (timer paused, review scheduled)
    dept: 'FAC',
    cat: 'c-fac-3',
    title: 'Ergonomic chair replacement for floor 4',
    description:
      'Three chairs on floor 4 are broken. Replacement needs the quarterly budget window.',
    priority: 'low',
    status: 'on_hold',
    requester: 'u-dev',
    createdH: 30,
    owner: 'u-tara',
    ackH: 28,
    updateH: 20,
    hold: { reason: 'Waiting for the facilities budget release next week.', reviewH: 46 },
    events: [
      { h: 28, actor: 'u-tara', action: 'Acknowledged' },
      {
        h: 20,
        actor: 'u-tara',
        action: 'On hold',
        detail: 'Waiting for the facilities budget release next week.',
      },
    ],
  },
  {
    // 9 — resolved, awaiting requester confirmation (paused)
    dept: 'FIN',
    cat: 'c-fin-2',
    title: 'Duplicate invoice paid to Northwind',
    description: 'Invoice NW-8891 appears to have been paid twice in the last cycle.',
    priority: 'high',
    status: 'resolved',
    requester: 'u-asha',
    createdH: 40,
    owner: 'u-sanjay',
    assignee: 'u-sanjay',
    ackH: 38,
    etaH: -10,
    updateH: 10,
    resolvedH: 8,
    summary:
      'The duplicate payment was recovered by bank recall; the corrected remittance advice is attached to the vendor record.',
    events: [
      { h: 38, actor: 'u-sanjay', action: 'Acknowledged' },
      {
        h: 10,
        actor: 'u-sanjay',
        action: 'Comment',
        body: 'Bank has initiated the recall; expecting settlement today.',
      },
      {
        h: 8,
        actor: 'u-sanjay',
        action: 'Resolved',
        detail: 'Duplicate payment recovered; remittance corrected.',
      },
    ],
  },
  {
    // 10 — closed
    dept: 'SEC',
    cat: 'c-sec-3',
    title: 'Quarterly access review evidence',
    description: 'Provide the Q3 access review export for the audit folder.',
    priority: 'medium',
    status: 'closed',
    requester: 'u-meera',
    createdH: 72,
    owner: 'u-vikram',
    assignee: 'u-vikram',
    ackH: 70,
    etaH: -32,
    updateH: 44,
    resolvedH: 30,
    closedH: 20,
    summary:
      'Access review export uploaded to the audit folder and acknowledged by Internal Audit.',
    events: [
      { h: 70, actor: 'u-vikram', action: 'Acknowledged' },
      {
        h: 30,
        actor: 'u-vikram',
        action: 'Resolved',
        detail: 'Access review export uploaded to the audit folder.',
      },
      { h: 20, actor: 'u-meera', action: 'Closed', detail: 'Confirmed — thank you.' },
    ],
  },
  {
    // 11 — reopened
    dept: 'IT',
    cat: 'c-it-2',
    title: 'New laptop for the design lead',
    description:
      'The replacement laptop arrived with a faulty keyboard; the issue reopened after the first fix.',
    priority: 'medium',
    status: 'reopened',
    requester: 'u-asha',
    createdH: 60,
    owner: 'u-rohan',
    assignee: 'u-dev',
    ackH: 58,
    etaH: 10,
    updateH: 5,
    reopenCount: 1,
    events: [
      { h: 58, actor: 'u-rohan', action: 'Acknowledged' },
      { h: 30, actor: 'u-dev', action: 'Resolved', detail: 'Replacement unit dispatched.' },
      {
        h: 5,
        actor: 'u-asha',
        action: 'Reopened',
        detail: 'The replacement has the same keyboard fault on the top row.',
      },
    ],
  },
  {
    // 12 — cancelled
    dept: 'FAC',
    cat: 'c-fac-1',
    title: 'Desk move for the support pod',
    description: 'Request to move four desks to the quiet zone.',
    priority: 'low',
    status: 'cancelled',
    requester: 'u-dev',
    createdH: 40,
    owner: 'u-tara',
    ackH: 38,
    updateH: 36,
    events: [
      { h: 38, actor: 'u-tara', action: 'Acknowledged' },
      {
        h: 36,
        actor: 'u-dev',
        action: 'Cancelled',
        detail: 'We agreed to keep the current layout after the team survey.',
      },
    ],
  },
  {
    // 13 — confidential HR ticket (requester must not see the internal note)
    dept: 'HR',
    cat: 'c-hr-3',
    title: 'Workplace concern — escalation review',
    description:
      'I would like to raise a concern about the on-call rotation and would prefer it stays within HR.',
    priority: 'high',
    status: 'in_progress',
    requester: 'u-meera',
    createdH: 14,
    confidential: true,
    owner: 'u-neha',
    assignee: 'u-neha',
    ackH: 12,
    etaH: 10,
    updateH: 10,
    events: [
      { h: 12, actor: 'u-neha', action: 'Acknowledged' },
      {
        h: 11,
        actor: 'u-neha',
        action: 'Comment',
        body: 'Thanks for writing in — this stays within the HR team. I will come back to you with the review plan.',
      },
      {
        h: 10,
        actor: 'u-neha',
        action: 'Internal note',
        type: 'internal_note',
        public: false,
        body: 'Pattern matches two earlier reports; draft plan ready for the HR head review.',
      },
    ],
  },
  {
    // 14 — Critical security ticket, unacknowledged, escalation contact notified at creation
    dept: 'SEC',
    cat: 'c-sec-2',
    title: 'Suspicious sign-in attempts on the build pipeline',
    description:
      'Multiple failed sign-ins from an unusual region hit the build service account overnight; one succeeded for 4 minutes.',
    priority: 'critical',
    status: 'new',
    requester: 'u-asha',
    createdH: 4,
    events: [],
  },
];

function mustUser(id: string): DbUser {
  const user = findUser(id);
  if (!user) throw new Error(`Seed error: unknown user ${id}`);
  return user;
}

function actorRef(actor: string): TimelineEvent['actor'] {
  if (actor === 'system') return { id: 'system', name: 'System' };
  return ref(mustUser(actor));
}

/** Timeline detail for seeded acknowledgements when the spec leaves it out. */
function ackDetail(ticket: Ticket): string {
  const owner = ticket.owner?.name ?? 'the team';
  if (ticket.eta) return `Owner ${owner}, ETA ${fmtWhen(ticket.eta)}`;
  return `Owner ${owner}`;
}

function escDetail(rec: DbTicket, action: string): string {
  const level = action.replace('Escalation L', '');
  const due = rec.ticket.eta ?? rec.resp_due ?? rec.update_due;
  return `L${level} escalation — next deadline ${due ? fmtWhen(new Date(due).toISOString()) : '—'}`;
}

function buildTicket(spec: SeedTicket): void {
  const requester = mustUser(spec.requester);
  const dept = db.departments.find((d) => d.id === spec.dept);
  if (!dept) throw new Error(`Seed error: unknown department ${spec.dept}`);
  const category = dept.categories.find((c) => c.id === spec.cat);
  if (!category) throw new Error(`Seed error: unknown category ${spec.cat}`);

  const createdMs = T0 - spec.createdH * HOUR_MS;
  const ackMs = spec.ackH != null ? T0 - spec.ackH * HOUR_MS : null;
  const updateBaseMs = spec.updateH != null ? T0 - spec.updateH * HOUR_MS : ackMs;
  const pausedStatus = spec.status === 'on_hold' || spec.status === 'awaiting_requester';
  const ticket: Ticket = {
    id: nextTicketId(spec.dept),
    title: spec.title,
    description: spec.description,
    department_id: dept.id,
    category_id: category.id,
    category_name: category.name,
    priority: spec.priority,
    requested_priority: spec.priority,
    status: spec.status,
    confidential: spec.confidential ?? false,
    requester: ref(requester),
    owner: spec.owner ? ref(mustUser(spec.owner)) : null,
    assignee: spec.assignee ? ref(mustUser(spec.assignee)) : null,
    collaborators: [],
    created_at: new Date(createdMs).toISOString(),
    sla_started_at: new Date(createdMs).toISOString(),
    acknowledged_at: ackMs != null ? new Date(ackMs).toISOString() : null,
    eta: spec.etaH != null ? inIso(spec.etaH) : null,
    next_checkpoint_at: null,
    last_team_update_at: updateBaseMs != null ? new Date(updateBaseMs).toISOString() : null,
    resolved_at: spec.resolvedH != null ? agoIso(spec.resolvedH) : null,
    closed_at: spec.closedH != null ? agoIso(spec.closedH) : null,
    reopen_count: spec.reopenCount ?? 0,
    hold: spec.hold ? { reason: spec.hold.reason, review_date: inIso(spec.hold.reviewH) } : null,
    resolution_summary: spec.summary ?? null,
    feedback: null,
    sla: { level: 0, kind: null, paused: false, stopped: false, due_at: null, label: '' },
    allowed_actions: [],
    attachments: spec.attachments ?? [],
  };

  const rec: DbTicket = {
    ticket,
    events: [],
    resp_due: null,
    resp_shift: 0,
    update_due: null,
    update_shift: 0,
    eta_shift: 0,
    // Only genuinely paused tickets carry a pause point (used when resuming).
    pause: pausedStatus && updateBaseMs != null ? { at: updateBaseMs, off: 0 } : null,
    last_escalation: null,
  };

  // Deadlines (display frame; the seed runs with clockOffsetMs = 0).
  if (ackMs != null && updateBaseMs != null) {
    rec.update_due = updateBaseMs + db.policy.update_cadence_hours * HOUR_MS;
  } else {
    rec.resp_due = createdMs + db.policy.initial_response_hours * HOUR_MS;
  }
  if (spec.escalation) {
    rec.last_escalation = {
      at: T0 - spec.escalation.h * HOUR_MS,
      off: 0,
      level: spec.escalation.level,
    };
  }

  pushEvent(rec, {
    actor: ref(requester),
    type: 'audit',
    action: 'Created',
    detail: `${spec.priority[0].toUpperCase()}${spec.priority.slice(1)} · ${category.name}`,
    public: true,
    at: ticket.created_at,
  });
  for (const ev of spec.events) {
    const detail =
      ev.detail ??
      (ev.action === 'Acknowledged'
        ? ackDetail(ticket)
        : ev.action.startsWith('Escalation L')
          ? escDetail(rec, ev.action)
          : undefined);
    pushEvent(rec, {
      actor: actorRef(ev.actor),
      type: ev.type ?? (ev.action === 'Comment' ? 'comment' : 'audit'),
      action: ev.action,
      ...(detail !== undefined ? { detail } : {}),
      ...(ev.body !== undefined ? { body: ev.body } : {}),
      public: ev.public ?? true,
      at: agoIso(ev.h),
    });
  }
  db.tickets.push(rec);
  recomputeSla(rec);
  seedNotifications(spec, rec);
}

/** 0-3 notifications per ticket: escalation > ack > assignment > confirmation. */
function seedNotifications(spec: SeedTicket, rec: DbTicket): void {
  const t = rec.ticket;
  const notes: { h: number; to: string[]; text: string; kind: string; critical?: boolean }[] = [];
  const spokes = spokesOf(t.department_id).map((u) => u.id);
  if (spec.escalation) {
    notes.push({
      h: spec.escalation.h,
      to: [...(t.owner ? [t.owner.id] : []), ...spokes],
      text: `L${spec.escalation.level} ${spec.escalation.kind} on ${t.id} (${t.title})`,
      kind: 'escalation',
      critical: spec.escalation.level >= 2,
    });
  }
  if (spec.ackH != null) {
    notes.push({
      h: spec.ackH,
      to: [t.requester.id],
      text: `Ticket ${t.id} was acknowledged by ${t.owner?.name ?? 'the team'}.`,
      kind: 'acknowledged',
    });
  }
  if (spec.assignee && spec.ackH != null) {
    notes.push({
      h: spec.ackH,
      to: [spec.assignee],
      text: `You were assigned ${t.id}: ${t.title}`,
      kind: 'assigned',
    });
  }
  notes.push({
    h: spec.createdH,
    to: [t.requester.id],
    text: `Ticket ${t.id} created. A first response is due within ${db.policy.initial_response_hours} hours.`,
    kind: 'ticket_created',
  });

  for (const note of notes.slice(0, 3)) {
    notifyUsers(note.to, {
      text: note.text,
      kind: note.kind,
      ...(note.critical ? { critical: true } : {}),
      ticket_id: t.id,
      at: agoIso(note.h),
      read: note.h >= 12, // older items pre-read so the bell shows a realistic set
    });
  }
}

export function buildSeedTickets(): void {
  for (const spec of SPECS) buildTicket(spec);
  // Seed the org audit log from ticket history.
  for (const rec of db.tickets) {
    for (const ev of rec.events) {
      addAudit({
        at: ev.at,
        actor: ev.actor,
        action: ev.action ?? 'updated',
        object_type: 'ticket',
        object_id: rec.ticket.id,
        ...(ev.detail ? { detail: ev.detail } : {}),
        ...(ev.body ? { detail: ev.body.slice(0, 120) } : {}),
      });
    }
  }
}
