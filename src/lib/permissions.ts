import type { Me, Role } from '@/types/domain';

export type PermissionFlag =
  | 'tickets.create'
  | 'tickets.view_all'
  | 'tickets.view_department'
  | 'tickets.acknowledge'
  | 'tickets.assign'
  | 'tickets.transfer'
  | 'tickets.change_priority'
  | 'tickets.revise_eta'
  | 'tickets.hold'
  | 'tickets.resolve'
  | 'tickets.close_admin'
  | 'tickets.reopen'
  | 'tickets.internal_notes'
  | 'users.approve_employee'
  | 'users.approve_admin'
  | 'users.approve_super_admin'
  | 'users.manage_roles'
  | 'admins.manage'
  | 'departments.manage'
  | 'policy.manage'
  | 'audit.view_all'
  | 'reports.view_org';

/**
 * Check a permission flag from `/auth/me`. Never derive from role names where a
 * flag exists (spec section 4).
 */
export function hasPermission(
  me: Pick<Me, 'permissions'> | null | undefined,
  flag: string,
): boolean {
  if (!me) return false;
  return me.permissions.includes(flag);
}

export function hasAnyPermission(
  me: Pick<Me, 'permissions'> | null | undefined,
  flags: string[],
): boolean {
  return flags.some((f) => hasPermission(me, f));
}

export function hasRole(me: Pick<Me, 'roles'> | null | undefined, ...roles: Role[]): boolean {
  if (!me) return false;
  return roles.some((r) => me.roles.includes(r));
}

/** Effective role shown in the UI: highest privilege first. */
export function primaryRole(me: Pick<Me, 'roles'> | null | undefined): Role | null {
  if (!me || me.roles.length === 0) return null;
  const order: Role[] = ['super_admin', 'admin', 'spoke', 'resolver', 'employee'];
  for (const r of order) if (me.roles.includes(r)) return r;
  return null;
}

/** Role badge list in display order. */
export function orderedRoles(roles: Role[]): Role[] {
  const order: Role[] = ['super_admin', 'admin', 'spoke', 'resolver', 'employee'];
  return [...roles].sort((a, b) => order.indexOf(a) - order.indexOf(b));
}

/**
 * May this viewer approve a signup request for `requestedRole`?
 * No one approves their own request (enforced by the caller passing `isSelf`).
 */
export function canApproveSignup(
  me: Pick<Me, 'permissions'> | null | undefined,
  requestedRole: 'employee' | 'admin' | 'super_admin',
  isSelf: boolean,
): boolean {
  if (isSelf) return false;
  if (requestedRole === 'employee') return hasPermission(me, 'users.approve_employee');
  if (requestedRole === 'admin') return hasPermission(me, 'users.approve_admin');
  return hasPermission(me, 'users.approve_super_admin');
}

/** Roles the viewer is allowed to grant when approving. */
export function grantableRoles(me: Pick<Me, 'permissions'> | null | undefined): Role[] {
  const roles: Role[] = [];
  if (hasPermission(me, 'users.approve_employee')) roles.push('employee');
  if (hasPermission(me, 'users.manage_roles')) roles.push('spoke', 'resolver');
  if (hasPermission(me, 'users.approve_admin')) roles.push('admin');
  if (hasPermission(me, 'users.approve_super_admin')) roles.push('super_admin');
  return roles;
}

/** Is the viewer a "staff" member on tickets (sees SLA levels, notes, escalations)? */
export function isStaff(me: Pick<Me, 'roles'> | null | undefined): boolean {
  return hasRole(me, 'super_admin', 'admin', 'spoke', 'resolver');
}

/** May the viewer see confidential tickets in this department? */
export function canSeeConfidential(
  me: Pick<Me, 'confidential_departments' | 'permissions'> | null | undefined,
  departmentId: string,
): boolean {
  if (!me) return false;
  if (hasPermission(me, 'tickets.view_all')) return true;
  return me.confidential_departments.includes(departmentId);
}

/** Sidebar visibility helper. */
export function sidebarFlags(me: Pick<Me, 'permissions'> | null | undefined) {
  return {
    approvals: hasPermission(me, 'users.approve_employee'),
    users: hasPermission(me, 'users.manage_roles'),
    config: hasAnyPermission(me, ['departments.manage', 'policy.manage', 'admins.manage']),
    audit: hasPermission(me, 'audit.view_all'),
    reports: hasPermission(me, 'reports.view_org'),
  };
}
