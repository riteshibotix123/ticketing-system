import { describe, expect, it } from 'vitest';
import {
  canApproveSignup,
  grantableRoles,
  hasAnyPermission,
  hasPermission,
  hasRole,
  isStaff,
  orderedRoles,
  primaryRole,
  sidebarFlags,
} from '../permissions';
import type { Role } from '@/types/domain';

interface Fixture {
  permissions: string[];
  roles: Role[];
}

const superAdmin: Fixture = {
  permissions: [
    'tickets.create',
    'tickets.view_all',
    'users.approve_employee',
    'users.approve_admin',
    'users.approve_super_admin',
    'users.manage_roles',
    'admins.manage',
    'departments.manage',
    'policy.manage',
    'audit.view_all',
    'reports.view_org',
  ],
  roles: ['super_admin'],
};

const admin: Fixture = {
  permissions: [
    'tickets.create',
    'tickets.view_all',
    'users.approve_employee',
    'users.manage_roles',
    'departments.manage',
    'audit.view_all',
  ],
  roles: ['admin'],
};

const spoke: Fixture = {
  permissions: [
    'tickets.create',
    'tickets.view_department',
    'tickets.acknowledge',
    'tickets.assign',
  ],
  roles: ['spoke'],
};

describe('permission flags (spec 4)', () => {
  it('reads flags, never role names', () => {
    expect(hasPermission(superAdmin, 'policy.manage')).toBe(true);
    expect(hasPermission(admin, 'policy.manage')).toBe(false);
    expect(hasPermission(spoke, 'tickets.view_all')).toBe(false);
    expect(hasPermission(null, 'tickets.create')).toBe(false);
  });

  it('supports any-of checks', () => {
    expect(hasAnyPermission(admin, ['policy.manage', 'departments.manage'])).toBe(true);
    expect(hasAnyPermission(spoke, ['policy.manage', 'admins.manage'])).toBe(false);
  });
});

describe('approval rules (spec 1.3 / 10.12)', () => {
  it('admins may approve employees but not admins', () => {
    expect(canApproveSignup(admin, 'employee', false)).toBe(true);
    expect(canApproveSignup(admin, 'admin', false)).toBe(false);
    expect(canApproveSignup(admin, 'super_admin', false)).toBe(false);
  });

  it('super admins approve admins and super admins but never themselves', () => {
    expect(canApproveSignup(superAdmin, 'admin', false)).toBe(true);
    expect(canApproveSignup(superAdmin, 'super_admin', false)).toBe(true);
    expect(canApproveSignup(superAdmin, 'super_admin', true)).toBe(false);
    expect(canApproveSignup(superAdmin, 'employee', true)).toBe(false);
  });

  it('spokes cannot approve anything', () => {
    expect(canApproveSignup(spoke, 'employee', false)).toBe(false);
  });

  it('lists only grantable roles', () => {
    expect(grantableRoles(admin)).toEqual(['employee']);
    expect(grantableRoles(superAdmin)).toContain('super_admin');
    expect(grantableRoles(spoke)).toEqual([]);
  });
});

describe('role helpers', () => {
  it('orders roles by privilege', () => {
    expect(orderedRoles(['employee', 'admin', 'spoke'])).toEqual(['admin', 'spoke', 'employee']);
    expect(primaryRole({ roles: ['employee', 'spoke'] })).toBe('spoke');
    expect(primaryRole({ roles: [] })).toBeNull();
  });

  it('identifies staff', () => {
    expect(isStaff(spoke)).toBe(true);
    expect(isStaff({ roles: ['employee'] })).toBe(false);
  });
});

describe('sidebar flags', () => {
  it('shows admin sections only with the right flags', () => {
    expect(sidebarFlags(admin)).toMatchObject({ approvals: true, users: true, audit: true });
    expect(sidebarFlags(spoke)).toMatchObject({ approvals: false, users: false, audit: false });
    expect(hasRole(spoke, 'spoke')).toBe(true);
  });
});
