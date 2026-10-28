/**
 * Department categories and the global SLA policy (spec 6.2, 10.2, 11.2).
 * Categories in use by tickets cannot be deleted; policy editing is Super
 * Admin only and recomputes every open ticket's SLA levels immediately.
 */
import { http } from 'msw';
import type { PolicyConfig } from '@/types/domain';
import { db } from '../db';
import {
  actorRef,
  addAudit,
  ok,
  readJson,
  respond,
  str,
  throw403,
  throw404,
  throw422,
} from '../helpers';
import { recomputeAll } from '../sla';
import { assertCanManageDepartments, assertPolicyManager, loadDepartment } from './deptShared';
import { requireUser } from './guard';
import { p } from './paths';

export const departmentExtrasHandlers = [
  /* ---------------------------------------------------------- categories */

  http.post(p('/departments/:id/categories'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      assertCanManageDepartments(user);
      const dept = loadDepartment(String(params.id));
      const body = await readJson<{ name?: string; confidential?: boolean }>(request);
      const name = str(body.name);
      if (name.length < 2) throw422({ name: 'Enter a category name.' });
      if (dept.categories.some((c) => c.name.toLowerCase() === name.toLowerCase())) {
        throw422({ name: 'A category with this name already exists.' });
      }
      dept.categories.push({
        id: `c-${dept.id.toLowerCase()}-${dept.categories.length + 1}`,
        name,
        department_id: dept.id,
        confidential: body.confidential === true,
        active: true,
      });
      addAudit({
        actor: actorRef(user),
        action: 'department.category_added',
        object_type: 'department',
        object_id: dept.id,
        detail: `Added category ${name} to ${dept.name}`,
      });
      return ok(dept, request);
    }),
  ),

  http.patch(p('/categories/:categoryId'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      assertCanManageDepartments(user);
      const category = db.departments
        .flatMap((d) => d.categories)
        .find((c) => c.id === String(params.categoryId));
      if (!category) throw404();
      const dept = loadDepartment(category.department_id);
      const body = await readJson<{ name?: string; confidential?: boolean }>(request);
      if (typeof body.name === 'string') {
        const name = str(body.name);
        if (name.length < 2) throw422({ name: 'Enter a category name.' });
        category.name = name;
      }
      if (typeof body.confidential === 'boolean') category.confidential = body.confidential;
      addAudit({
        actor: actorRef(user),
        action: 'department.category_updated',
        object_type: 'department',
        object_id: dept.id,
        detail: `Category ${category.name} updated in ${dept.name}`,
      });
      return ok(dept, request);
    }),
  ),

  http.delete(p('/categories/:categoryId'), ({ params, request }) =>
    respond(request, () => {
      const user = requireUser(request);
      assertCanManageDepartments(user);
      const dept = db.departments.find((d) =>
        d.categories.some((c) => c.id === String(params.categoryId)),
      );
      if (!dept) throw404();
      const category = dept.categories.find((c) => c.id === String(params.categoryId))!;
      // Spec 10.2: tickets keep their category, so in-use categories survive.
      if (db.tickets.some((rec) => rec.ticket.category_id === category.id)) {
        throw403('This category is used by existing tickets and cannot be removed.');
      }
      dept.categories = dept.categories.filter((c) => c.id !== category.id);
      addAudit({
        actor: actorRef(user),
        action: 'department.category_removed',
        object_type: 'department',
        object_id: dept.id,
        detail: `Removed category ${category.name} from ${dept.name}`,
      });
      return ok(dept, request);
    }),
  ),

  /* -------------------------------------------------------------- policy */

  http.get(p('/policy'), ({ request }) =>
    respond(request, () => {
      requireUser(request);
      return ok(db.policy, request);
    }),
  ),

  http.put(p('/policy'), ({ request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      assertPolicyManager(user);
      const body = await readJson<PolicyConfig>(request);
      const fields: Record<string, string> = {};
      const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : NaN);
      if (!(num(body.initial_response_hours) > 0))
        fields.initial_response_hours = 'Use a positive number of hours.';
      if (!(num(body.update_cadence_hours) > 0))
        fields.update_cadence_hours = 'Use a positive number of hours.';
      if (!(num(body.requester_reminder_hours) > 0))
        fields.requester_reminder_hours = 'Use a positive number of hours.';
      if (!(num(body.update_warning_hours) > 0))
        fields.update_warning_hours = 'Use a positive number of hours.';
      if (!(num(body.eta_warning_hours) > 0))
        fields.eta_warning_hours = 'Use a positive number of hours.';
      if (!(num(body.escalation_repeat_hours) > 0))
        fields.escalation_repeat_hours = 'Use a positive number of hours.';
      if (!(num(body.reopen_window_days) >= 0))
        fields.reopen_window_days = 'Use zero or more days.';
      if (!(num(body.max_reopens) >= 0)) fields.max_reopens = 'Use zero or more reopens.';
      for (const priority of ['low', 'medium', 'high', 'critical'] as const) {
        if (!(num(body.warning_hours?.[priority]) > 0))
          fields[`warning_hours.${priority}`] = 'Use a positive number of hours.';
        if (!(num(body.l3_hours?.[priority]) > 0))
          fields[`l3_hours.${priority}`] = 'Use a positive number of hours.';
      }
      if (body.sla_mode !== 'calendar') {
        fields.sla_mode = 'Calendar hours is the only mode available.';
      }
      if (Object.keys(fields).length > 0) throw422(fields);

      const before = { ...db.policy };
      db.policy = {
        initial_response_hours: body.initial_response_hours,
        warning_hours: { ...body.warning_hours },
        l3_hours: { ...body.l3_hours },
        update_warning_hours: body.update_warning_hours,
        update_cadence_hours: body.update_cadence_hours,
        eta_warning_hours: body.eta_warning_hours,
        escalation_repeat_hours: body.escalation_repeat_hours,
        sla_mode: body.sla_mode,
        admins_can_manage_departments: body.admins_can_manage_departments === true,
        requester_reminder_hours: body.requester_reminder_hours,
        auto_close_business_days:
          typeof body.auto_close_business_days === 'number' ? body.auto_close_business_days : null,
        reopen_window_days: body.reopen_window_days,
        max_reopens: body.max_reopens,
      };
      recomputeAll(); // every open ticket's levels may change
      addAudit({
        actor: actorRef(user),
        action: 'policy.updated',
        object_type: 'policy',
        object_id: null,
        old_value: before,
        new_value: { ...db.policy },
        detail: `Policy updated: response ${db.policy.initial_response_hours}h, cadence ${db.policy.update_cadence_hours}h, L3 ${db.policy.l3_hours.critical}h (critical)`,
      });
      return ok(db.policy, request);
    }),
  ),
];
