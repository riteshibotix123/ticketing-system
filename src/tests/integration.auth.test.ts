/**
 * Spec 15 integration tests (MSW): login + session refresh, and the signup →
 * approval matrix for each approver role, including the two hard rules —
 * self-approval blocked and Admin cannot approve an Admin.
 */
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { server } from '@/mocks/server';
import { getAccessToken, isApiError, setAccessToken, setSessionExpiredHandler } from '@/api/client';
import { authApi } from '@/api/endpoints/auth';
import { usersApi } from '@/api/endpoints/users';
import { ticketsApi } from '@/api/endpoints/tickets';
import { ASHA, KARAN, MFA_CODE, PASSWORD, PRIYA, ROHAN, loginAs, uniqueEmail } from './msw-session';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  setAccessToken(null);
  setSessionExpiredHandler(null);
});
afterAll(() => server.close());

describe('auth and session (spec 7/15)', () => {
  it('logs in an employee without MFA and returns /auth/me', async () => {
    await loginAs(ASHA);
    const me = await authApi.me();
    expect(me.email).toBe(ASHA);
    expect(me.roles).toContain('employee');
    expect(me.permissions).not.toContain('tickets.internal_notes');
  });

  it('walks the MFA step for staff accounts', async () => {
    const res = await authApi.login(ROHAN, PASSWORD);
    if (!('mfa_required' in res)) throw new Error('Expected the MFA step.');
    expect(res.mfa_required).toBe(true);
    expect(res.mfa_token).toBeTruthy();

    await expect(authApi.mfaVerify(res.mfa_token, '000000')).rejects.toMatchObject({
      status: 422,
      fields: { code: expect.any(String) },
    });

    const mfa = await authApi.mfaVerify(res.mfa_token, MFA_CODE);
    setAccessToken(mfa.access_token);
    const me = await authApi.me();
    expect(me.roles).toContain('spoke');
    expect(me.permissions).toContain('tickets.internal_notes');
  });

  it('refreshes an expired access token once and retries the call', async () => {
    await loginAs(ASHA);
    setAccessToken('bogus-expired-token');
    const page = await ticketsApi.list({ scope: 'mine' });
    expect(Array.isArray(page.items)).toBe(true);
    expect(getAccessToken()).not.toBe('bogus-expired-token');
    expect(getAccessToken()).toBeTruthy();
  });

  it('invokes the session-expired handler when refresh fails', async () => {
    await loginAs(ASHA);
    await authApi.logout(); // kills this user's refresh token too
    setAccessToken('bogus-expired-token');
    const expired = vi.fn();
    setSessionExpiredHandler(expired);

    await expect(ticketsApi.list({ scope: 'mine' })).rejects.toSatisfy((err: unknown) => {
      return isApiError(err) && err.code === 'session_expired';
    });
    expect(expired).toHaveBeenCalledTimes(1);
  });
});

/** Find a pending signup request by email (Admin view). */
async function pendingIdFor(email: string): Promise<string> {
  const page = await usersApi.signupRequests({ status: 'pending' });
  const found = page.items.find((r) => r.email.toLowerCase() === email.toLowerCase());
  if (!found) throw new Error(`No pending signup request for ${email}`);
  return found.id;
}

async function signup(requestedRole: 'employee' | 'admin' | 'super_admin'): Promise<string> {
  const email = uniqueEmail();
  await authApi.signup({
    name: 'Integration Tester',
    email,
    password: PASSWORD,
    requested_role: requestedRole,
    requested_department: 'IT',
  });
  await authApi.verifyEmail('mock-verify-token');
  return email;
}

describe('signup and approval (spec 1.3.1/15)', () => {
  beforeEach(() => setAccessToken(null));

  it('signs up, verifies the email and has no roles yet', async () => {
    const email = await signup('employee');
    await loginAs(email);
    const me = await authApi.me();
    expect(me.roles).toEqual([]);
  });

  it('blocks self-approval of your own request', async () => {
    const email = await signup('employee');
    await loginAs(PRIYA);
    const requestId = await pendingIdFor(email);

    await loginAs(email); // the requester themself, still pending
    await expect(
      usersApi.approve(requestId, { approved_role: 'employee', approved_department: 'IT' }),
    ).rejects.toMatchObject({ status: 403 });
  });

  it('lets an Admin approve employees but not other Admins', async () => {
    const employeeEmail = await signup('employee');
    const adminEmail = await signup('admin');
    await loginAs(PRIYA);
    const employeeId = await pendingIdFor(employeeEmail);
    const adminId = await pendingIdFor(adminEmail);

    const approved = await usersApi.approve(employeeId, {
      approved_role: 'employee',
      approved_department: 'IT',
    });
    expect(approved.status).toBe('approved');

    await expect(
      usersApi.approve(adminId, { approved_role: 'admin', approved_department: 'IT' }),
    ).rejects.toMatchObject({ status: 403 });

    // A Super Admin completes the Admin approval.
    await loginAs(KARAN);
    await usersApi.approve(adminId, { approved_role: 'admin', approved_department: 'IT' });
    await loginAs(adminEmail);
    const me = await authApi.me();
    expect(me.roles).toContain('admin');
    expect(me.permissions).toContain('users.approve_employee');
  });

  it('lets a Super Admin approve a Super Admin request', async () => {
    const superEmail = await signup('super_admin');
    await loginAs(KARAN);
    const requestId = await pendingIdFor(superEmail);
    await usersApi.approve(requestId, { approved_role: 'super_admin', approved_department: 'IT' });

    await loginAs(superEmail);
    const me = await authApi.me();
    expect(me.roles).toContain('super_admin');
    expect(me.permissions).toContain('users.approve_super_admin');
  });

  it('requires a reason to reject and shows the decided tab afterwards', async () => {
    const email = await signup('employee');
    await loginAs(KARAN);
    const requestId = await pendingIdFor(email);

    await expect(usersApi.reject(requestId, '')).rejects.toMatchObject({ status: 422 });
    const decided = await usersApi.reject(requestId, 'Role not needed for this team setup.');
    expect(decided.status).toBe('rejected');
    expect(decided.decided_by?.id).toBeTruthy();
  });
});
