/**
 * Access-request review endpoints (spec 6, 1.3.1, 9.8): the pending/decided
 * signup list, approval and rejection. Review rules live server-side:
 * employee requests need users.approve_employee, Admin requests
 * users.approve_admin (Super Admin only), Super Admin requests
 * users.approve_super_admin, and nobody reviews their own request.
 */
import { http } from 'msw';
import type { Role, SignupRequest } from '@/types/domain';
import { db, findDepartment, findUserByEmail, paginate, syncSpokes, type DbUser } from '../db';
import {
  actorRef,
  addAudit,
  notifyUsers,
  nowIso,
  ok,
  qs,
  readJson,
  respond,
  str,
  throw403,
  throw404,
  throw422,
} from '../helpers';
import { can } from '../access';
import { requireUser } from './guard';
import { grantableRoles } from './users';
import { p } from './paths';

const APPROVE_FLAGS: Record<SignupRequest['requested_role'], string> = {
  employee: 'users.approve_employee',
  admin: 'users.approve_admin',
  super_admin: 'users.approve_super_admin',
};

const DENIAL: Record<SignupRequest['requested_role'], string> = {
  employee: 'You do not have access to approve Employee requests.',
  admin: 'Only a Super Admin can approve Admin requests.',
  super_admin: 'Only a Super Admin can approve Super Admin requests.',
};

/** The pending account row behind a request, when signup already created one. */
function applicantOf(req: SignupRequest): DbUser | null {
  return findUserByEmail(req.email);
}

function loadRequest(id: string): SignupRequest {
  const req = db.signupRequests.find((r) => r.id === id);
  if (!req) throw404();
  return req;
}

/** Spec 9.8: only roles the viewer may grant can be chosen on approval. */
function assertApprovable(viewer: DbUser, req: SignupRequest): void {
  if (req.email.toLowerCase() === viewer.email.toLowerCase()) {
    throw403('You cannot review your own request.');
  }
  if (req.status !== 'pending') throw403('This request has already been decided.');
  if (!can(viewer, APPROVE_FLAGS[req.requested_role])) throw403(DENIAL[req.requested_role]);
}

export const signupRequestHandlers = [
  http.get(p('/signup-requests'), ({ request }) =>
    respond(request, () => {
      const viewer = requireUser(request);
      if (!Object.values(APPROVE_FLAGS).some((f) => can(viewer, f))) throw403();
      const params = qs(request);
      const status = str(params.get('status'));
      const rows = db.signupRequests
        .filter((r) => !status || r.status === status)
        // Newest requests first, matching the Pending list in spec 9.8.
        .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
      if (params.get('count_only') === 'true') return ok({ count: rows.length }, request);
      return ok(paginate(rows, params.get('page'), params.get('page_size'), 100), request);
    }),
  ),

  http.post(p('/signup-requests/:id/approve'), ({ params, request }) =>
    respond(request, async () => {
      const viewer = requireUser(request);
      const req = loadRequest(String(params.id));
      assertApprovable(viewer, req);

      const body = await readJson<{ approved_role?: string; approved_department?: string }>(
        request,
      );
      const role = str(body.approved_role) as Role;
      const department = str(body.approved_department);
      if (!grantableRoles(viewer).includes(role)) throw403(`You cannot grant the ${role} role.`);
      if (!department || !findDepartment(department)) {
        throw422({ approved_department: 'Pick a department for this account.' });
      }

      req.approved_role = role;
      req.approved_department = department;
      req.status = 'approved';
      req.decided_by = actorRef(viewer);
      req.decided_at = nowIso();

      // Signup created a pending account row; approval activates it (spec 1.3).
      const applicant = applicantOf(req);
      if (applicant) {
        applicant.roles = [role];
        applicant.department_id = department;
        applicant.spoke_departments = role === 'spoke' ? [department] : [];
        applicant.state = 'active';
        syncSpokes();
      }

      addAudit({
        actor: actorRef(viewer),
        action: 'signup.approved',
        object_type: 'signup_request',
        object_id: req.id,
        old_value: {
          requested_role: req.requested_role,
          requested_department: req.requested_department,
        },
        new_value: { approved_role: role, approved_department: department },
        detail: `${req.name} approved as ${role} (${department}).`,
      });
      return ok(req, request);
    }),
  ),

  http.post(p('/signup-requests/:id/reject'), ({ params, request }) =>
    respond(request, async () => {
      const viewer = requireUser(request);
      const req = loadRequest(String(params.id));
      assertApprovable(viewer, req);

      const body = await readJson<{ reason?: string }>(request);
      const reason = str(body.reason);
      if (!reason) throw422({ reason: 'A rejection needs a reason — the applicant is told why.' });

      req.status = 'rejected';
      req.rejection_reason = reason;
      req.decided_by = actorRef(viewer);
      req.decided_at = nowIso();

      // The account stays parked; it can be reviewed again only via Users.
      const applicant = applicantOf(req);
      if (applicant) applicant.state = 'rejected';

      addAudit({
        actor: actorRef(viewer),
        action: 'signup.rejected',
        object_type: 'signup_request',
        object_id: req.id,
        detail: `${req.name}'s ${req.requested_role} request rejected.`,
        reason,
      });
      // The applicant hears the outcome by email (spec 12); the mock logs an
      // in-portal note so the demo shows something happened.
      if (applicant) {
        notifyUsers([applicant.id], {
          text: `Your request was not approved. Reason: ${reason}.`,
          kind: 'signup_decision',
        });
      }
      return ok(req, request);
    }),
  ),
];
