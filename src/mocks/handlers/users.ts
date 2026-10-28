/**
 * User administration endpoints (spec 6.1, 9.12): the directory with
 * role/state filters, role assignment (reason required, audit logged) and
 * account activation/deactivation. Admin and Super Admin rows are read-only
 * here — they live under Configuration → Admin accounts.
 */
import { http } from 'msw';
import type { Role, User } from '@/types/domain';
import { db, findUser, paginate, syncSpokes, type DbUser } from '../db';
import {
  actorRef,
  addAudit,
  ok,
  qs,
  readJson,
  respond,
  str,
  throw403,
  throw404,
  throw422,
} from '../helpers';
import { can, serializeUser } from '../access';
import { invalidateUserTokens } from '../auth';
import { requireUser } from './guard';
import { p } from './paths';

const ALL_ROLES: Role[] = ['super_admin', 'admin', 'spoke', 'resolver', 'employee'];

/** Roles the viewer may grant directly (mirrors lib/permissions grantableRoles). */
export function grantableRoles(user: DbUser): Role[] {
  const out: Role[] = [];
  if (can(user, 'users.approve_employee')) out.push('employee');
  if (can(user, 'users.manage_roles')) out.push('spoke', 'resolver');
  if (can(user, 'users.approve_admin')) out.push('admin');
  if (can(user, 'users.approve_super_admin')) out.push('super_admin');
  return out;
}

/** Spec 9.12: Admin/Super Admin rows are managed in Admin accounts, not here. */
export function isAdminRow(user: DbUser): boolean {
  return user.roles.includes('admin') || user.roles.includes('super_admin');
}

function maskFor(user: DbUser): User {
  return serializeUser(user);
}

export const userHandlers = [
  http.get(p('/users'), ({ request }) =>
    respond(request, () => {
      const viewer = requireUser(request);
      // Spokes delegate tickets (spec 9.7: eligible resolvers of the department),
      // so they need read access to the directory; role changes stay gated below.
      if (
        !can(viewer, 'users.manage_roles') &&
        !can(viewer, 'admins.manage') &&
        !can(viewer, 'tickets.assign')
      )
        throw403();
      const params = qs(request);
      const q = str(params.get('q')).toLowerCase();
      const role = str(params.get('role'));
      const state = str(params.get('state'));
      const dept = str(params.get('department_id'));
      const rows = db.users
        .filter((u) => {
          if (q && !`${u.name} ${u.email}`.toLowerCase().includes(q)) return false;
          if (role && !u.roles.includes(role as Role)) return false;
          if (state && u.state !== state) return false;
          if (dept && u.department_id !== dept && !u.spoke_departments.includes(dept)) return false;
          return true;
        })
        .map(maskFor);
      return ok(paginate(rows, params.get('page'), params.get('page_size')), request);
    }),
  ),

  http.patch(p('/users/:id/roles'), ({ params, request }) =>
    respond(request, async () => {
      const viewer = requireUser(request);
      if (!can(viewer, 'users.manage_roles')) throw403();
      const target = findUser(String(params.id));
      if (!target) throw404();
      if (isAdminRow(target))
        throw403('Admin accounts are managed under Configuration → Admin accounts.');
      if (target.id === viewer.id) throw403('You cannot change your own roles.');

      const body = await readJson<{
        add?: string[];
        remove?: string[];
        department_ids?: string[];
        confidential_departments?: string[];
        reason?: string;
      }>(request);
      const reason = str(body.reason);
      if (!reason) throw422({ reason: 'Every role change needs a reason.' });
      const grants = grantableRoles(viewer);
      const add = (Array.isArray(body.add) ? body.add : []).filter((r): r is Role =>
        ALL_ROLES.includes(r as Role),
      );
      const remove = (Array.isArray(body.remove) ? body.remove : []).filter((r): r is Role =>
        ALL_ROLES.includes(r as Role),
      );
      for (const role of add) {
        if (!grants.includes(role)) throw403(`You cannot grant the ${role} role.`);
      }

      const before = [...target.roles];
      target.roles = [...new Set([...target.roles.filter((r) => !remove.includes(r)), ...add])];
      if (Array.isArray(body.department_ids)) {
        for (const id of body.department_ids) {
          if (!db.departments.some((d) => d.id === id))
            throw422({ department_ids: `Unknown department ${id}.` });
        }
        target.spoke_departments = body.department_ids;
      }
      if (Array.isArray(body.confidential_departments)) {
        for (const id of body.confidential_departments) {
          if (!target.spoke_departments.includes(id)) {
            throw422({
              confidential_departments:
                'Confidential access requires Spoke access to that department.',
            });
          }
        }
        target.confidential_departments = body.confidential_departments;
      }
      // A Spoke without departments is no longer a Spoke.
      if (target.roles.includes('spoke') && target.spoke_departments.length === 0) {
        target.roles = target.roles.filter((r) => r !== 'spoke');
      }
      if (target.state === 'pending_approval' && target.roles.length > 0) target.state = 'active';
      syncSpokes();

      addAudit({
        actor: actorRef(viewer),
        action: 'user.roles_updated',
        object_type: 'user',
        object_id: target.id,
        old_value: before,
        new_value: [...target.roles],
        detail: `Roles for ${target.name}: ${before.join(', ') || 'none'} → ${target.roles.join(', ') || 'none'}`,
        reason,
      });
      return ok(maskFor(target), request);
    }),
  ),

  http.post(p('/users/:id/deactivate'), ({ params, request }) =>
    respond(request, async () => {
      const viewer = requireUser(request);
      if (!can(viewer, 'users.manage_roles')) throw403();
      const target = findUser(String(params.id));
      if (!target) throw404();
      if (target.id === viewer.id) throw403('You cannot deactivate your own account.');
      if (isAdminRow(target))
        throw403('Admin accounts are managed under Configuration → Admin accounts.');
      const body = await readJson<{ reason?: string }>(request);
      const reason = str(body.reason);
      if (!reason) throw422({ reason: 'Give a reason for deactivating this account.' });
      target.state = 'deactivated';
      invalidateUserTokens(target.id);
      syncSpokes();
      addAudit({
        actor: actorRef(viewer),
        action: 'user.deactivated',
        object_type: 'user',
        object_id: target.id,
        detail: `${target.name} deactivated`,
        reason,
      });
      return ok(maskFor(target), request);
    }),
  ),

  http.post(p('/users/:id/activate'), ({ params, request }) =>
    respond(request, async () => {
      const viewer = requireUser(request);
      if (!can(viewer, 'users.manage_roles')) throw403();
      const target = findUser(String(params.id));
      if (!target) throw404();
      const body = await readJson<{ reason?: string }>(request);
      const reason = str(body.reason);
      if (!reason) throw422({ reason: 'Give a reason for activating this account.' });
      target.state = 'active';
      syncSpokes();
      addAudit({
        actor: actorRef(viewer),
        action: 'user.activated',
        object_type: 'user',
        object_id: target.id,
        detail: `${target.name} activated`,
        reason,
      });
      return ok(maskFor(target), request);
    }),
  ),
];
