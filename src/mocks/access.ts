/**
 * Server-side access rules: permission flags (spec 4.1), ticket visibility
 * (requirement 3 — invisible tickets 404, never 403-with-detail), the
 * `allowed_actions` matrix (spec 4.2 + 9.7) and per-viewer serialization.
 */
import type { Me, Ticket, TicketAction, TimelineEvent, User } from '@/types/domain';
import { OPEN_STATUSES } from '@/lib/constants';
import { compareUrgency } from '@/lib/sla';
import { db, findTicket, type DbTicket, type DbUser } from './db';
import { slaForViewer } from './sla';
import { throw403, throw404 } from './helpers';

const ALL_FLAGS: readonly string[] = [
  'tickets.create',
  'tickets.view_all',
  'tickets.view_department',
  'tickets.acknowledge',
  'tickets.assign',
  'tickets.transfer',
  'tickets.change_priority',
  'tickets.revise_eta',
  'tickets.hold',
  'tickets.resolve',
  'tickets.close_admin',
  'tickets.reopen',
  'tickets.internal_notes',
  'users.approve_employee',
  'users.approve_admin',
  'users.approve_super_admin',
  'users.manage_roles',
  'admins.manage',
  'departments.manage',
  'policy.manage',
  'audit.view_all',
  'reports.view_org',
];

const ADMIN_TICKET_FLAGS = ALL_FLAGS.filter((f) =>
  [
    'tickets.create',
    'tickets.view_all',
    'tickets.acknowledge',
    'tickets.assign',
    'tickets.transfer',
    'tickets.change_priority',
    'tickets.revise_eta',
    'tickets.hold',
    'tickets.resolve',
    'tickets.close_admin',
    'tickets.reopen',
    'tickets.internal_notes',
  ].includes(f),
);
const SPOKE_FLAGS = ALL_FLAGS.filter((f) =>
  [
    'tickets.create',
    'tickets.view_department',
    'tickets.acknowledge',
    'tickets.assign',
    'tickets.transfer',
    'tickets.change_priority',
    'tickets.revise_eta',
    'tickets.hold',
    'tickets.resolve',
    'tickets.reopen',
    'tickets.internal_notes',
  ].includes(f),
);
// Resolver: work assigned to them (ack only ever fires when they ARE the assignee —
// see allowedActionsFor) plus notes. No assign/transfer/priority/reopen/cancel.
const RESOLVER_FLAGS = ALL_FLAGS.filter((f) =>
  [
    'tickets.create',
    'tickets.acknowledge',
    'tickets.revise_eta',
    'tickets.hold',
    'tickets.resolve',
    'tickets.internal_notes',
  ].includes(f),
);

/**
 * Effective permission flags for a user (spec 4.1). Super Admin wins outright;
 * Admin/Spoke/Resolver flags union. `departments.manage` for Admins honours the
 * Super Admin toggle (spec 1.3.5).
 */
export function permissionsFor(user: DbUser): string[] {
  const set = new Set<string>();
  if (user.roles.includes('super_admin')) return [...ALL_FLAGS];
  if (user.roles.includes('admin')) {
    ADMIN_TICKET_FLAGS.forEach((f) => set.add(f));
    ['users.approve_employee', 'users.manage_roles', 'audit.view_all', 'reports.view_org'].forEach(
      (f) => set.add(f),
    );
    if (db.policy.admins_can_manage_departments) set.add('departments.manage');
  }
  if (user.roles.includes('spoke')) SPOKE_FLAGS.forEach((f) => set.add(f));
  if (user.roles.includes('resolver')) RESOLVER_FLAGS.forEach((f) => set.add(f));
  set.add('tickets.create'); // everyone may raise tickets (spec 4.2)
  return [...set];
}

export function can(user: DbUser, flag: string): boolean {
  return permissionsFor(user).includes(flag);
}

/** `/auth/me` payload (Me + account_state). */
export function meFor(user: DbUser): Me & { account_state: User['state'] } {
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    ...(user.title ? { title: user.title } : {}),
    roles: user.roles,
    department_id: user.department_id,
    spoke_departments: user.spoke_departments,
    confidential_departments: user.confidential_departments,
    permissions: permissionsFor(user),
    mfa_enabled: user.mfa_enabled,
    theme: user.theme ?? 'system',
    account_state: user.state,
  };
}

export function serializeUser(user: DbUser): User {
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    ...(user.title ? { title: user.title } : {}),
    roles: user.roles,
    department_id: user.department_id,
    state: user.state,
    spoke_departments: user.spoke_departments,
    confidential_departments: user.confidential_departments,
    mfa_enabled: user.mfa_enabled,
    created_at: user.created_at,
  };
}

/* ------------------------------------------------------------- visibility */

/**
 * May `user` see this ticket at all? Confidential tickets are visible only to
 * the requester, the assignee/owner, `tickets.view_all`, or users whose
 * `confidential_departments` include the department. Collaborators are NOT in
 * that list (requirement 3). Failures surface as 404 so nothing leaks.
 */
export function canSeeTicket(user: DbUser, t: Ticket): boolean {
  const isRequester = t.requester.id === user.id;
  const isOwnerOrAssignee = t.owner?.id === user.id || t.assignee?.id === user.id;
  const viewAll = can(user, 'tickets.view_all');
  if (t.confidential) {
    return (
      isRequester ||
      isOwnerOrAssignee ||
      viewAll ||
      user.confidential_departments.includes(t.department_id)
    );
  }
  if (isRequester || isOwnerOrAssignee || viewAll) return true;
  if (user.spoke_departments.includes(t.department_id)) return true;
  return t.collaborators.some((c) => c.id === user.id);
}

/** Load a ticket the caller may see, or throw the generic 404. */
export function loadVisibleTicket(id: string, user: DbUser): DbTicket {
  const rec = findTicket(id);
  if (!rec || !canSeeTicket(user, rec.ticket)) throw404();
  return rec;
}

/** Requester position: hides internal notes/escalations/level detail (req 4). */
export function isRequesterPosition(user: DbUser, t: Ticket): boolean {
  return t.requester.id === user.id;
}

/* -------------------------------------------------------- allowed_actions */

const OPEN = new Set([
  'new',
  'acknowledged',
  'assigned',
  'in_progress',
  'awaiting_requester',
  'on_hold',
  'reopened',
]);
const LIFECYCLE = new Set([
  'acknowledged',
  'assigned',
  'in_progress',
  'awaiting_requester',
  'on_hold',
  'reopened',
]);
const ACKED_LIFECYCLE = LIFECYCLE; // these statuses imply the ticket was acknowledged

/**
 * Server decides which buttons exist (spec 4.2 matrix + 9.7).
 * The requester never gets `internal_note`; a resolver only gets actions when
 * they own/are assigned the work; Spoke/Admin actions need the department too.
 */
export function allowedActionsFor(user: DbUser, t: Ticket): TicketAction[] {
  const perms = permissionsFor(user);
  const flags = (f: string) => perms.includes(f);
  const isRequester = t.requester.id === user.id;
  const isOwner = t.owner?.id === user.id;
  const isAssignee = t.assignee?.id === user.id;
  const viewAll = flags('tickets.view_all');
  const spokeHere =
    flags('tickets.view_department') && user.spoke_departments.includes(t.department_id);
  /** Admin or Spoke of this department. */
  const elevated = viewAll || spokeHere;
  /** Supervisory access: elevated, or the acknowledging owner, or the assignee. */
  const working = elevated || isOwner || isAssignee;
  const s = t.status;
  const isOpen = OPEN.has(s);
  const out: TicketAction[] = [];

  if (isOpen) {
    if (
      !t.acknowledged_at &&
      s === 'new' &&
      (elevated || (isAssignee && flags('tickets.acknowledge')))
    ) {
      out.push('acknowledge');
    }
    if (flags('tickets.assign') && elevated) out.push('assign');
    if (flags('tickets.transfer') && elevated) out.push('transfer');
    if (flags('tickets.change_priority') && elevated) out.push('change_priority');
    if (flags('tickets.revise_eta') && working && ACKED_LIFECYCLE.has(s)) out.push('revise_eta');
    if (flags('tickets.hold') && working && LIFECYCLE.has(s) && s !== 'in_progress')
      out.push('start_work');
    if (flags('tickets.hold') && working && LIFECYCLE.has(s) && s !== 'awaiting_requester')
      out.push('ask_requester');
    if (flags('tickets.hold') && working && LIFECYCLE.has(s) && s !== 'on_hold') out.push('hold');
    if (flags('tickets.resolve') && working && LIFECYCLE.has(s)) out.push('resolve');
    // Cancel: requester only before resolved; Admin/Spoke until closed (spec 4.2).
    if (s !== 'closed' && s !== 'cancelled') {
      if (isRequester && LIFECYCLE.has(s)) out.push('cancel');
      else if (elevated) out.push('cancel');
    }
  }
  if (s === 'resolved' && (isRequester || viewAll)) out.push('confirm_closure');
  if ((s === 'resolved' || s === 'closed') && (isRequester || elevated)) out.push('reopen');
  if (s !== 'closed' && s !== 'cancelled') out.push('comment');
  // The requester NEVER gets internal_note (requirement 5).
  if (s !== 'closed' && s !== 'cancelled' && flags('tickets.internal_notes') && !isRequester) {
    out.push('internal_note');
  }
  return out;
}

export function assertAction(rec: DbTicket, user: DbUser, action: TicketAction): void {
  if (!allowedActionsFor(user, rec.ticket).includes(action)) throw403();
}

/* -------------------------------------------------------------- serializing */

/** Ticket DTO for a specific viewer (allowed_actions + requester-safe SLA). */
export function ticketDto(rec: DbTicket, user: DbUser): Ticket {
  const requesterPosition = isRequesterPosition(user, rec.ticket);
  return {
    ...rec.ticket,
    sla: slaForViewer(rec, requesterPosition),
    allowed_actions: allowedActionsFor(user, rec.ticket),
  };
}

/** Timeline already filtered for the caller (requirement 4). */
export function timelineFor(rec: DbTicket, user: DbUser): TimelineEvent[] {
  const requesterPosition = isRequesterPosition(user, rec.ticket);
  const staff = can(user, 'tickets.internal_notes');
  const visible = rec.events.filter((e) => {
    if (e.type === 'internal_note') return !requesterPosition && staff;
    if (requesterPosition) return e.public;
    if (staff) return true;
    return e.public; // non-staff non-requester (e.g. collaborator): public only
  });
  return [...visible].sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));
}

/** Tickets in a list scope (spec 6.3). 'all' needs tickets.view_all. */
export function scopedTickets(user: DbUser, scope: string): DbTicket[] {
  if (scope === 'all' && !can(user, 'tickets.view_all')) throw403();
  if (scope === 'queue' && !can(user, 'tickets.view_department') && !can(user, 'tickets.view_all'))
    throw403();
  return db.tickets.filter((rec) => {
    const t = rec.ticket;
    switch (scope) {
      case 'mine':
        return t.requester.id === user.id;
      case 'assigned':
        return (
          t.assignee?.id === user.id ||
          t.owner?.id === user.id ||
          t.collaborators.some((c) => c.id === user.id)
        );
      case 'queue':
        return user.spoke_departments.includes(t.department_id);
      default:
        return true;
    }
  });
}

/** Default list scope per role (spec 9.4 default tab). */
export function defaultScope(user: DbUser): string {
  if (can(user, 'tickets.view_all')) return 'all';
  if (user.spoke_departments.length > 0) return 'queue';
  if (user.roles.includes('resolver')) return 'assigned';
  return 'mine';
}

/** Default urgency sort: level desc, priority desc, oldest SLA start first (11.4). */
export function byUrgency(a: DbTicket, b: DbTicket): number {
  return compareUrgency(a.ticket, b.ticket);
}

export function isOpenStatus(status: Ticket['status']): boolean {
  return OPEN_STATUSES.includes(status);
}
