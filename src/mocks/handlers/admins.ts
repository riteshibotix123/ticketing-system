/**
 * Admin account management (spec 6.1 "GET/POST/DELETE /admins — Super Admin
 * only", 9.13). Only Super Admins may list, add, activate, deactivate or
 * remove Admin accounts; Super Admin rows are protected.
 */
import { http } from 'msw';
import { db, findUser, type DbUser } from '../db';
import {
  actorRef,
  addAudit,
  noContent,
  ok,
  readJson,
  respond,
  str,
  throw403,
  throw404,
  throw422,
} from '../helpers';
import { serializeUser } from '../access';
import { invalidateUserTokens } from '../auth';
import { requireUser } from './guard';
import { p } from './paths';

function assertSuperAdmin(user: DbUser): void {
  if (!user.roles.includes('super_admin')) {
    throw403('Only a Super Admin can manage Admin accounts.');
  }
}

function adminRows(): DbUser[] {
  return db.users.filter((u) => u.roles.includes('admin') || u.roles.includes('super_admin'));
}

function loadAdmin(id: string): DbUser {
  const user = findUser(id);
  if (!user || !user.roles.includes('admin')) throw404();
  return user;
}

export const adminHandlers = [
  http.get(p('/admins'), ({ request }) =>
    respond(request, () => {
      const viewer = requireUser(request);
      assertSuperAdmin(viewer);
      return ok(adminRows().map(serializeUser), request);
    }),
  ),

  http.post(p('/admins'), ({ request }) =>
    respond(request, async () => {
      const viewer = requireUser(request);
      assertSuperAdmin(viewer);
      const body = await readJson<{ user_id?: string }>(request);
      const target = findUser(str(body.user_id));
      if (!target) throw422({ user_id: 'Pick an active user.' });
      if (target.state !== 'active') throw422({ user_id: 'That account is not active.' });
      if (target.roles.includes('admin') || target.roles.includes('super_admin')) {
        throw422({ user_id: 'That person is already an Admin.' });
      }
      target.roles = [...target.roles.filter((role) => role !== 'employee'), 'admin'];
      addAudit({
        actor: actorRef(viewer),
        action: 'admin.created',
        object_type: 'user',
        object_id: target.id,
        detail: `${target.name} added as Admin`,
      });
      return ok(serializeUser(target), request, 201);
    }),
  ),

  http.post(p('/admins/:id/deactivate'), ({ params, request }) =>
    respond(request, () => {
      const viewer = requireUser(request);
      assertSuperAdmin(viewer);
      const target = loadAdmin(String(params.id));
      if (target.id === viewer.id) throw403('You cannot deactivate your own account.');
      target.state = 'deactivated';
      invalidateUserTokens(target.id);
      addAudit({
        actor: actorRef(viewer),
        action: 'admin.deactivated',
        object_type: 'user',
        object_id: target.id,
        detail: `${target.name} deactivated`,
      });
      return ok(serializeUser(target), request);
    }),
  ),

  http.post(p('/admins/:id/activate'), ({ params, request }) =>
    respond(request, () => {
      const viewer = requireUser(request);
      assertSuperAdmin(viewer);
      const target = loadAdmin(String(params.id));
      target.state = 'active';
      addAudit({
        actor: actorRef(viewer),
        action: 'admin.activated',
        object_type: 'user',
        object_id: target.id,
        detail: `${target.name} activated`,
      });
      return ok(serializeUser(target), request);
    }),
  ),

  http.delete(p('/admins/:id'), ({ params, request }) =>
    respond(request, () => {
      const viewer = requireUser(request);
      assertSuperAdmin(viewer);
      const target = loadAdmin(String(params.id));
      if (target.roles.includes('super_admin')) throw403('Super Admin accounts are protected.');
      if (target.id === viewer.id) throw403('You cannot remove your own Admin account.');
      const index = db.users.findIndex((u) => u.id === target.id);
      db.users.splice(index, 1);
      invalidateUserTokens(target.id);
      addAudit({
        actor: actorRef(viewer),
        action: 'admin.removed',
        object_type: 'user',
        object_id: target.id,
        detail: `${target.name} removed from Admin accounts`,
      });
      return noContent(request);
    }),
  ),
];
