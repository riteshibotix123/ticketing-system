/**
 * Spec 15 integration tests (MSW): the BRD section-20 control loop
 * (create → acknowledge → assign → resolve → confirm), reopen, transfer, hold,
 * confidential-ticket scoping, internal-note invisibility and the
 * notification read flow.
 */
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { server } from '@/mocks/server';
import { isApiError, setAccessToken } from '@/api/client';
import { ticketsApi } from '@/api/endpoints/tickets';
import { notificationsApi } from '@/api/endpoints/ops';
import { ASHA, MEERA, NEHA, ROHAN, SANJAY, createItTicket, inHours, loginAs } from './msw-session';
import type { Ticket } from '@/types/domain';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => setAccessToken(null));
afterAll(() => server.close());

const CONFIDENTIAL_TITLE = 'Workplace concern — escalation review';

/** Find the seeded confidential HR ticket as its requester (Meera). */
async function confidentialTicketId(): Promise<string> {
  await loginAs(MEERA);
  const page = await ticketsApi.list({ scope: 'mine' });
  const hit = page.items.find((t) => t.title === CONFIDENTIAL_TITLE);
  if (!hit) throw new Error('Seeded confidential ticket not found');
  return hit.id;
}

describe('ticket control loop (BRD 20 / spec 15)', () => {
  it('runs create → acknowledge → assign → resolve → confirm closure', async () => {
    await loginAs(ASHA);
    const created = await createItTicket();
    expect(created.status).toBe('new');
    expect(created.requester.id).toBe('u-asha');
    // Requesters never get staff actions or internal notes (requirement 5).
    expect(created.allowed_actions).not.toContain('acknowledge');
    expect(created.allowed_actions).not.toContain('internal_note');

    await loginAs(ROHAN);
    const acked = await ticketsApi.act(created.id, 'acknowledge', { eta: inHours(4) });
    expect(acked.status).toBe('acknowledged');
    expect(acked.owner?.id).toBe('u-rohan');
    expect(acked.eta).toBeTruthy();

    const assigned = await ticketsApi.act(created.id, 'assign', { assignee_id: 'u-dev' });
    expect(assigned.status).toBe('assigned');
    expect(assigned.assignee?.id).toBe('u-dev');

    setAccessToken(null);
    await loginAs('dev.patel@ibotix.ai');
    const resolved = await ticketsApi.act(created.id, 'resolve', {
      summary: 'Re-imaged the machine and restored the user profile from backup.',
    });
    expect(resolved.status).toBe('resolved');

    await loginAs(ASHA);
    const closed = await ticketsApi.act(created.id, 'confirm_closure');
    expect(closed.status).toBe('closed');
  });

  it('reopens a closed ticket, requiring a reason first', async () => {
    await loginAs(ASHA);
    const ticket = await createItTicket();
    await loginAs(ROHAN);
    await ticketsApi.act(ticket.id, 'acknowledge', { eta: inHours(4) });
    await ticketsApi.act(ticket.id, 'resolve', { summary: 'Fixed by restarting the router.' });

    await loginAs(ASHA);
    await expect(ticketsApi.act(ticket.id, 'reopen')).rejects.toMatchObject({
      status: 422,
      fields: { reason: expect.any(String) },
    });
    const reopened = await ticketsApi.act(ticket.id, 'reopen', {
      reason: 'The issue came back overnight after the same reboot.',
    });
    expect(reopened.status).toBe('reopened');
    expect(reopened.reopen_count).toBe(1);
  });

  it('transfers a ticket to another department with a reason', async () => {
    await loginAs(ASHA);
    const ticket = await createItTicket();
    await loginAs(ROHAN);

    await expect(
      ticketsApi.act(ticket.id, 'transfer', { department_id: 'HR' }),
    ).rejects.toMatchObject({ status: 422, fields: { reason: expect.any(String) } });

    const moved = await ticketsApi.act(ticket.id, 'transfer', {
      department_id: 'HR',
      reason: 'This is an HR policy question rather than an IT fault.',
    });
    expect(moved.department_id).toBe('HR');
    expect(moved.assignee).toBeNull();
  });

  it('holds a ticket, pausing the SLA timer until the review date', async () => {
    await loginAs(ASHA);
    const ticket = await createItTicket();
    await loginAs(ROHAN);
    await ticketsApi.act(ticket.id, 'acknowledge', { eta: inHours(4) });

    await expect(ticketsApi.act(ticket.id, 'hold', {})).rejects.toMatchObject({ status: 422 });
    const held = await ticketsApi.act(ticket.id, 'hold', {
      reason: 'Waiting for the vendor replacement part to arrive.',
      review_date: inHours(72),
    });
    expect(held.status).toBe('on_hold');
    expect(held.sla.paused).toBe(true);
    expect(held.hold?.review_date).toBeTruthy();
  });
});

describe('confidentiality (requirement 3–5 / spec 15)', () => {
  it('404s a confidential ticket for an unauthorised Spoke and unrelated employee', async () => {
    const id = await confidentialTicketId();

    await loginAs(SANJAY); // FIN Spoke, no confidential access
    const deniedSpoke: unknown = await ticketsApi.get(id).catch((e) => e);
    expect(isApiError(deniedSpoke) && deniedSpoke.status).toBe(404);

    await loginAs(ASHA); // unrelated employee
    const deniedEmployee: unknown = await ticketsApi.get(id).catch((e) => e);
    expect(isApiError(deniedEmployee) && deniedEmployee.status).toBe(404);

    await loginAs(NEHA); // HR Spoke with confidential authorisation
    const visible = await ticketsApi.get(id);
    expect(visible.confidential).toBe(true);
    expect(visible.allowed_actions).toContain('internal_note');
  });

  it('never lets the requester see internal notes or escalation internals', async () => {
    const id = await confidentialTicketId();
    const noteBody = 'HR integration note — legal reviewed the on-call rotation.';

    await loginAs(NEHA);
    await ticketsApi.comment(id, noteBody, true);
    const staffTimeline = await ticketsApi.timeline(id);
    expect(staffTimeline.some((e) => e.body === noteBody)).toBe(true);
    expect(staffTimeline.some((e) => e.type === 'internal_note' && e.public === false)).toBe(true);

    await loginAs(MEERA);
    const requesterTimeline = await ticketsApi.timeline(id);
    expect(requesterTimeline.some((e) => e.body === noteBody)).toBe(false);
    expect(requesterTimeline.every((e) => e.public !== false)).toBe(true);
    const ticket: Ticket = await ticketsApi.get(id);
    expect(ticket.allowed_actions).not.toContain('internal_note');
  });
});

describe('notifications (spec 9.10/15)', () => {
  it('counts, marks read and clears the unread badge', async () => {
    await loginAs(ASHA);
    const ticket = await createItTicket(); // ack below notifies the requester
    await loginAs(ROHAN);
    await ticketsApi.act(ticket.id, 'acknowledge', { eta: inHours(4) });

    await loginAs(ASHA);
    const before = await notificationsApi.unreadCount();
    expect(before.count).toBeGreaterThanOrEqual(1);

    const list = await notificationsApi.list({ unread: true });
    const first = list.items[0];
    await notificationsApi.markRead(first.id);
    const afterSingle = await notificationsApi.unreadCount();
    expect(afterSingle.count).toBe(before.count - 1);

    await notificationsApi.markAllRead();
    const cleared = await notificationsApi.unreadCount();
    expect(cleared.count).toBe(0);
  });
});
