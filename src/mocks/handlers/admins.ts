/**
 * Admin account management (spec 6.1 "GET/POST/DELETE /admins — Super Admin
 * only", 9.13). Only Super Admins may list, add, activate, deactivate or
 * remove Admin accounts; Super Admin rows are protected.
 */
import { http } from 'msw';
import { db, findUser, findUserByEmail, paginate, uid, type DbUser } from '../db';
import {
  actorRef,
  addAudit,
  noContent,
  nowIso,
  ok,
  readJson,
  respond,
  str,
  throw403,
  throw404,
  throw422,
} from '../helpers';
import { serializeUser } from '../access';
import { DEMO_PASSWORD, invalidateUserTokens } from '../auth';
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
      const rows = adminRows().map(serializeUser);
      return ok(paginate(rows, new URL(request.url).searchParams.get('page'), 100), request);
    }),
  ),

  http.post(p('/admins'), ({ request }) =>
    respond(request, async () => {
      const viewer = requireUser(request);
      assertSuperAdmin(viewer);
      const body = await readJson<{ email?: string; name?: string }>(request);
      const email = str(body.email);
      const name = str(body.name);
      const fields: Record<string, string> = {};
      if (name.length < 2) fields.name = 'Enter the full name.';
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) fields.email = 'Enter a valid email address.';
      else if (findUserByEmail(email)) fields.email = 'An account with this email already exists.';
      if (Object.keys(fields).length > 0) throw422(fields);

      const user: DbUser = {
        id: uid('u'),
        name,
        email,
        roles: ['admin'],
        department_id: null,
        state: 'active',
        spoke_departments: [],
        confidential_departments: [],
        mfa_enabled: true,
        created_at: nowIso(),
        password: DEMO_PASSWORD,
      };
      db.users.push(user);
      addAudit({
        actor: actorRef(viewer),
        action: 'admin.created',
        object_type: 'user',
        object_id: user.id,
        detail: `${name} added as Admin`,
      });
      return ok(serializeUser(user), request, 201);
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
