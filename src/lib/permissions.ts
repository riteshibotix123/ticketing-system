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
  | 'superadmins.protect'
  | 'confidential.manage'
  | 'departments.manage'
  | 'policy.manage'
  | 'audit.view_all'
  | 'reports.view_org';

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
  return flags.some((flag) => hasPermission(me, flag));
}

export function hasRole(me: Pick<Me, 'roles'> | null | undefined, ...roles: Role[]): boolean {
  if (!me) return false;
  return roles.some((role) => me.roles.includes(role));
}

const ROLE_ORDER: Role[] = ['super_admin', 'admin', 'spoke', 'employee'];

export function primaryRole(me: Pick<Me, 'roles'> | null | undefined): Role | null {
  if (!me || me.roles.length === 0) return null;
  for (const role of ROLE_ORDER) if (me.roles.includes(role)) return role;
  return null;
}

export function orderedRoles(roles: Role[]): Role[] {
  return [...roles].sort((a, b) => ROLE_ORDER.indexOf(a) - ROLE_ORDER.indexOf(b));
}

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

export function grantableRoles(
  me: Pick<Me, 'permissions'> | null | undefined,
): Array<'employee' | 'admin' | 'super_admin'> {
  const roles: Array<'employee' | 'admin' | 'super_admin'> = [];
  if (hasPermission(me, 'users.approve_employee')) roles.push('employee');
  if (hasPermission(me, 'users.approve_admin')) roles.push('admin');
  if (hasPermission(me, 'users.approve_super_admin')) roles.push('super_admin');
  return roles;
}

export function isStaff(me: Pick<Me, 'roles'> | null | undefined): boolean {
  return hasRole(me, 'super_admin', 'admin', 'spoke');
}

export function sidebarFlags(me: Pick<Me, 'permissions'> | null | undefined) {
  return {
    approvals: hasPermission(me, 'users.approve_employee'),
    users: hasPermission(me, 'users.manage_roles'),
    config: hasAnyPermission(me, ['departments.manage', 'policy.manage', 'admins.manage']),
    confidential: hasPermission(me, 'confidential.manage'),
    audit: hasPermission(me, 'audit.view_all'),
    reports: hasPermission(me, 'reports.view_org'),
  };
}
