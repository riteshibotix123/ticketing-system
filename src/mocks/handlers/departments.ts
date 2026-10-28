/**
 * Department administration (spec 6.2, 9.13): list/create/update plus Spoke
 * membership and escalation contacts. A department cannot be activated
 * without at least one active Spoke. Categories and policy live in
 * `departmentExtras.ts`; shared guards in `deptShared.ts`.
 */
import { http } from 'msw';
import type { Department } from '@/types/domain';
import { db, findUser, spokesOf, type DbUser } from '../db';
import { actorRef, addAudit, ok, readJson, respond, str, throw404, throw422 } from '../helpers';
import { serializeUser } from '../access';
import { assertCanManageDepartments, departmentDto, loadDepartment } from './deptShared';
import { requireUser } from './guard';
import { p } from './paths';

/** Spec 9.13 inline error, reused by create + activate. */
const NEED_SPOKE = 'A department needs at least one active Spoke before it can be activated.';

export const departmentHandlers = [
  http.get(p('/departments'), ({ request }) =>
    respond(request, () => {
      requireUser(request);
      return ok(db.departments, request);
    }),
  ),

  http.post(p('/departments'), ({ request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      assertCanManageDepartments(user);
      const body = await readJson<{ name?: string; active?: boolean; confidential?: boolean }>(
        request,
      );
      const name = str(body.name);
      if (name.length < 2) throw422({ name: 'Enter a department name.' });
      if (db.departments.some((d) => d.name.toLowerCase() === name.toLowerCase())) {
        throw422({ name: 'A department with this name already exists.' });
      }
      // New departments have no Spokes, so they must start inactive (spec 10.3).
      if (body.active === true) throw422({ active: NEED_SPOKE });
      const id =
        (name
          .toUpperCase()
          .replace(/[^A-Z]/g, '')
          .slice(0, 3) || 'DPT') + db.departments.length;
      const dept: Department = {
        id,
        name,
        spokes: [],
        escalation_primary: null,
        escalation_backup: null,
        confidential: body.confidential === true,
        categories: [],
        active: false,
      };
      db.departments.push(dept);
      addAudit({
        actor: actorRef(user),
        action: 'department.created',
        object_type: 'department',
        object_id: id,
        detail: `Department ${name} created (inactive until it has a Spoke)`,
      });
      return ok(dept, request, 201);
    }),
  ),

  http.patch(p('/departments/:id'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      assertCanManageDepartments(user);
      const dept = loadDepartment(String(params.id));
      const body = await readJson<{ name?: string; active?: boolean; confidential?: boolean }>(
        request,
      );
      if (typeof body.name === 'string') {
        const name = str(body.name);
        if (name.length < 2) throw422({ name: 'Enter a department name.' });
        dept.name = name;
      }
      if (typeof body.confidential === 'boolean') dept.confidential = body.confidential;
      if (typeof body.active === 'boolean') {
        if (body.active && spokesOf(dept.id).length === 0) throw422({ active: NEED_SPOKE });
        dept.active = body.active;
      }
      addAudit({
        actor: actorRef(user),
        action: 'department.updated',
        object_type: 'department',
        object_id: dept.id,
        detail: `Department ${dept.name} updated`,
      });
      return ok(departmentDto(dept.id), request);
    }),
  ),

  http.post(p('/departments/:id/spokes'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      assertCanManageDepartments(user);
      const dept = loadDepartment(String(params.id));
      const body = await readJson<{ user_id?: string }>(request);
      const target = findUser(str(body.user_id));
      if (!target) throw422({ user_id: 'Pick an active user.' });
      if (target.state !== 'active') throw422({ user_id: 'That account is not active.' });
      if (!target.spoke_departments.includes(dept.id)) target.spoke_departments.push(dept.id);
      if (!target.roles.includes('spoke')) target.roles.push('spoke');
      if (!target.confidential_departments.includes(dept.id) && dept.confidential) {
        target.confidential_departments.push(dept.id);
      }
      const dto = departmentDto(dept.id);
      addAudit({
        actor: actorRef(user),
        action: 'department.spoke_added',
        object_type: 'department',
        object_id: dept.id,
        detail: `Added ${target.name} as Spoke of ${dept.name}`,
      });
      return ok(dto, request);
    }),
  ),

  http.delete(p('/departments/:id/spokes/:userId'), ({ params, request }) =>
    respond(request, () => {
      const user = requireUser(request);
      assertCanManageDepartments(user);
      const dept = loadDepartment(String(params.id));
      const target = findUser(String(params.userId));
      if (!target) throw404();
      target.spoke_departments = target.spoke_departments.filter((d) => d !== dept.id);
      target.confidential_departments = target.confidential_departments.filter(
        (d) => d !== dept.id,
      );
      // Last department removed -> the Spoke role goes too.
      if (target.spoke_departments.length === 0) {
        target.roles = target.roles.filter((r) => r !== 'spoke');
      }
      const dto = departmentDto(dept.id);
      addAudit({
        actor: actorRef(user),
        action: 'department.spoke_removed',
        object_type: 'department',
        object_id: dept.id,
        detail: `Removed ${target.name} as Spoke of ${dept.name}`,
      });
      return ok(dto, request);
    }),
  ),

  http.put(p('/departments/:id/escalation'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      assertCanManageDepartments(user);
      const dept = loadDepartment(String(params.id));
      const body = await readJson<{ primary_id?: string | null; backup_id?: string | null }>(
        request,
      );
      const resolveContact = (raw: unknown, field: string) => {
        const id = str(raw);
        if (!id) return null;
        const contact: DbUser | null = findUser(id);
        if (!contact || contact.state !== 'active') throw422({ [field]: 'Pick an active user.' });
        return serializeUser(contact);
      };
      dept.escalation_primary = resolveContact(body.primary_id, 'primary_id');
      dept.escalation_backup = resolveContact(body.backup_id, 'backup_id');
      addAudit({
        actor: actorRef(user),
        action: 'department.escalation_updated',
        object_type: 'department',
        object_id: dept.id,
        detail: `Escalation contacts for ${dept.name}: ${dept.escalation_primary?.name ?? 'none'} / ${dept.escalation_backup?.name ?? 'none'}`,
      });
      return ok(dept, request);
    }),
  ),
];
