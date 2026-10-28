/**
 * Shared guards/lookups for the department + policy configuration handlers
 * (spec 6.2, 9.13): Admins manage departments only while the Super Admin
 * toggle allows it; policy editing is Super Admin only.
 */
import type { Department } from '@/types/domain';
import { findDepartment, syncSpokes, type DbUser } from '../db';
import { throw403, throw404 } from '../helpers';
import { can } from '../access';

export function assertCanManageDepartments(user: DbUser): void {
  if (!can(user, 'departments.manage')) {
    throw403('Admins can manage departments only when a Super Admin allows it.');
  }
}

export function assertPolicyManager(user: DbUser): void {
  if (!can(user, 'policy.manage')) throw403('Only a Super Admin can change the global policy.');
}

export function loadDepartment(id: string): Department {
  const dept = findDepartment(id);
  if (!dept) throw404();
  return dept;
}

/** Re-derive spokes and return the department for the response. */
export function departmentDto(id: string): Department {
  syncSpokes();
  const dept = findDepartment(id);
  if (!dept) throw404();
  return dept;
}
