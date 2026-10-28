/**
 * User administration endpoints (spec 6.1, 9.12): the directory with
 * role/state filters, role assignment (reason required, audit logged) and
 * account activation/deactivation. Admin and Super Admin rows are read-only
 * here — they live under Configuration → Admin accounts.
 */
import { http } from 'msw';
import type { Role, UserListItem } from '@/types/domain';
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

/** Roles the viewer may grant on a signup (mirrors lib/permissions grantableRoles). */
export function grantableRoles(user: DbUser): Array<'employee' | 'admin' | 'super_admin'> {
  const out: Array<'employee' | 'admin' | 'super_admin'> = [];
  if (can(user, 'users.approve_employee')) out.push('employee');
  if (can(user, 'users.approve_admin')) out.push('admin');
  if (can(user, 'users.approve_super_admin')) out.push('super_admin');
  return out;
}

/** Spec 9.12: Admin/Super Admin rows are managed in Admin accounts, not here. */
export function isAdminRow(user: DbUser): boolean {
  return user.roles.includes('admin') || user.roles.includes('super_admin');
}

function maskFor(user: DbUser): UserListItem {
  return serializeUser(user);
}

export const userHandlers = [
  http.get(p('/users'), ({ request }) =>
    respond(request, () => {
      const viewer = requireUser(request);
      // Spokes delegate tickets (spec 9.7: eligible members of the department),
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
        spoke_departments?: string[];
        reason?: string;
      }>(request);
      const reason = str(body.reason);
      if (!reason) throw422({ reason: 'Every role change needs a reason.' });
      const spokeDepartments = Array.isArray(body.spoke_departments)
        ? [...new Set(body.spoke_departments)]
        : null;
      if (spokeDepartments) {
        for (const id of spokeDepartments) {
          if (!db.departments.some((d) => d.id === id)) {
            throw422({ spoke_departments: `Unknown department ${id}.` });
          }
        }
      }

      const before = [...target.spoke_departments];
      if (spokeDepartments) {
        target.spoke_departments = spokeDepartments;
        if (spokeDepartments.length > 0 && !target.roles.includes('spoke')) {
          target.roles.push('spoke');
        }
        if (spokeDepartments.length === 0) {
          target.roles = target.roles.filter((r) => r !== 'spoke');
        }
      }
      syncSpokes();

      addAudit({
        actor: actorRef(viewer),
        action: 'user.roles_updated',
        object_type: 'user',
        object_id: target.id,
        old_value: before,
        new_value: [...target.spoke_departments],
        detail: `Spoke departments for ${target.name}: ${before.join(', ') || 'none'} → ${target.spoke_departments.join(', ') || 'none'}`,
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
      const openTicketCount = db.tickets.filter(
        (rec) =>
          rec.ticket.requester.id === target.id &&
          rec.ticket.status !== 'closed' &&
          rec.ticket.status !== 'cancelled',
      ).length;
      return ok(
        { result: 'deactivated', open_ticket_count: openTicketCount, protected_action_id: null },
        request,
      );
    }),
  ),

  http.post(p('/users/:id/activate'), ({ params, request }) =>
    respond(request, () => {
      const viewer = requireUser(request);
      if (!can(viewer, 'users.manage_roles')) throw403();
      const target = findUser(String(params.id));
      if (!target) throw404();
      target.state = 'active';
      syncSpokes();
      addAudit({
        actor: actorRef(viewer),
        action: 'user.activated',
        object_type: 'user',
        object_id: target.id,
        detail: `${target.name} activated`,
      });
      return ok(maskFor(target), request);
    }),
  ),
];
