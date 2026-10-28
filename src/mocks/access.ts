import type { Me, Ticket, TicketAction, TimelineEvent, UserListItem } from '@/types/domain';
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
  'superadmins.protect',
  'confidential.manage',
  'departments.manage',
  'policy.manage',
  'audit.view_all',
  'reports.view_org',
];

const ADMIN_TICKET_FLAGS = [
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
];

const EMPLOYEE_WORK_FLAGS = [
  'tickets.create',
  'tickets.acknowledge',
  'tickets.revise_eta',
  'tickets.hold',
  'tickets.resolve',
];

const SPOKE_FLAGS = [
  'tickets.create',
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
];

export function permissionsFor(user: DbUser): string[] {
  const set = new Set<string>();
  if (user.roles.includes('super_admin')) return [...ALL_FLAGS];
  if (user.roles.includes('admin')) {
    ADMIN_TICKET_FLAGS.forEach((flag) => set.add(flag));
    set.add('users.approve_employee');
    set.add('audit.view_all');
    set.add('reports.view_org');
    if (db.policy.admins_can_manage_departments) {
      set.add('users.manage_roles');
      set.add('departments.manage');
    }
  }
  if (user.roles.includes('spoke')) SPOKE_FLAGS.forEach((flag) => set.add(flag));
  if (user.roles.includes('employee')) EMPLOYEE_WORK_FLAGS.forEach((flag) => set.add(flag));
  return [...set];
  return [...set];
}

export function can(user: DbUser, flag: string): boolean {
  return permissionsFor(user).includes(flag);
}

export function meFor(user: DbUser): Me {
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    ...(user.title ? { title: user.title } : {}),
    roles: user.roles,
    department_id: user.department_id,
    spoke_departments: user.spoke_departments,
    permissions: permissionsFor(user),
    mfa_enabled: user.mfa_enabled,
    theme: user.theme ?? 'system',
  };
}

export function serializeUser(user: DbUser): UserListItem {
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    ...(user.title ? { title: user.title } : {}),
    roles: user.roles,
    state: user.state,
    department_id: user.department_id,
    spoke_departments: user.spoke_departments,
    last_login_at: user.last_login_at,
    created_at: user.created_at,
  };
}

/* ------------------------------------------------------------- visibility */

export function canSeeTicket(user: DbUser, t: Ticket): boolean {
  const isRequester = t.requester.id === user.id;
  const isOwnerOrAssignee = t.owner?.id === user.id || t.assignee?.id === user.id;
  const isCollaborator = t.collaborators.some((c) => c.id === user.id);
  const viewAll = can(user, 'tickets.view_all');
  if (t.confidential) {
    return (
      user.roles.includes('super_admin') ||
      isRequester ||
      isOwnerOrAssignee ||
      isCollaborator
    );
  }
  if (isRequester || isOwnerOrAssignee || isCollaborator || viewAll) return true;
  return user.spoke_departments.includes(t.department_id);
}

export function loadVisibleTicket(id: string, user: DbUser): DbTicket {
  const rec = findTicket(id);
  if (!rec || !canSeeTicket(user, rec.ticket)) throw404();
  return rec;
}

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

const ACKNOWLEDGED_OR_LATER = new Set([
  'acknowledged',
  'assigned',
  'in_progress',
  'awaiting_requester',
  'on_hold',
  'reopened',
]);

export function allowedActionsFor(user: DbUser, t: Ticket): TicketAction[] {
  const flags = (flag: string) => can(user, flag);
  const isRequester = t.requester.id === user.id;
  const isOwner = t.owner?.id === user.id;
  const isAssignee = t.assignee?.id === user.id;
  const viewAll = flags('tickets.view_all');
  const spokeHere =
    flags('tickets.view_department') && user.spoke_departments.includes(t.department_id);
  const elevated = viewAll || spokeHere;
  const working = elevated || isOwner || isAssignee;
  const status = t.status;
  const open = OPEN.has(status);
  const acted = ACKNOWLEDGED_OR_LATER.has(status);
  const out: TicketAction[] = [];

  if (open) {
    if (status === 'new' && !isRequester && working && flags('tickets.acknowledge')) {
      out.push('acknowledge');
    }
    if (status !== 'new' && elevated && flags('tickets.assign')) out.push('assign');
    if (elevated && flags('tickets.transfer')) out.push('transfer');
    if (elevated && flags('tickets.change_priority')) out.push('change_priority');
    if (acted && working && flags('tickets.revise_eta')) out.push('revise_eta');
    if (['acknowledged', 'assigned', 'reopened'].includes(status) && working && flags('tickets.acknowledge')) {
      out.push('start_work');
    }
    if (acted && status !== 'awaiting_requester' && working) out.push('ask_requester');
    if (acted && status !== 'on_hold' && working && flags('tickets.hold')) out.push('hold');
    if (['on_hold', 'awaiting_requester'].includes(status) && working) out.push('resume');
    if (working && flags('tickets.resolve')) out.push('resolve');
    if (elevated && flags('tickets.close_admin')) out.push('close_admin');
    if (elevated) out.push('manage_collaborators');
    if (isRequester && status === 'new') out.push('cancel');
  }
  if (status === 'resolved' && isRequester) out.push('confirm_closure');
  if ((status === 'resolved' || status === 'closed') && isRequester) out.push('reopen');
  if (status !== 'closed' && status !== 'cancelled') out.push('comment');
  if (status !== 'closed' && status !== 'cancelled' && flags('tickets.internal_notes') && !isRequester) {
    out.push('internal_note');
  }
  return out;
}

export function assertAction(rec: DbTicket, user: DbUser, action: TicketAction): void {
  if (!allowedActionsFor(user, rec.ticket).includes(action)) throw403();
}

/* -------------------------------------------------------------- serializing */

export function ticketDto(rec: DbTicket, user: DbUser): Ticket {
  const requesterPosition = isRequesterPosition(user, rec.ticket);
  return {
    ...rec.ticket,
    sla: slaForViewer(rec, requesterPosition),
    allowed_actions: allowedActionsFor(user, rec.ticket),
  };
}

export function timelineFor(rec: DbTicket, user: DbUser): TimelineEvent[] {
  const requesterPosition = isRequesterPosition(user, rec.ticket);
  const staff = can(user, 'tickets.internal_notes');
  const visible = rec.events.filter((event) => {
    if (event.type === 'internal_note') return !requesterPosition && staff;
    if (requesterPosition) return event.public;
    if (staff) return true;
    return event.public;
  });
  return [...visible].sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));
}

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

export function defaultScope(user: DbUser): string {
  if (can(user, 'tickets.view_all')) return 'all';
  if (user.spoke_departments.length > 0) return 'queue';
  return 'mine';
}

export function byUrgency(a: DbTicket, b: DbTicket): number {
  return compareUrgency(a.ticket, b.ticket);
}

export function isOpenStatus(status: Ticket['status']): boolean {
  return OPEN_STATUSES.includes(status);
}
