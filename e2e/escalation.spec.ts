/**
 * Spec 15/17: escalation scenario driven by the mock demo clock. A fresh
 * unacknowledged ticket is escalated by advancing time 48h; the staff timeline
 * must show the internal escalation entries and the SLA banner must go
 * warning/overdue — requesters never see any of it.
 */
import { test, expect } from '@playwright/test';
import { PEOPLE, advanceClock, createTicket, login, logout, openTicketFromList } from './helpers';

test.describe('demo clock escalations', () => {
  test('advancing the clock escalates an open ticket and notifies staff', async ({
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name === 'phone', 'Desktop flow');
    const title = `E2E escalation ${Date.now()}`;

    await login(page, PEOPLE.employee);
    await createTicket(page, title);
    await logout(page);

    await login(page, PEOPLE.spoke);
    await page.getByRole('link', { name: 'Tickets' }).first().click();
    await page.getByRole('tab', { name: 'Department queue' }).click();
    await openTicketFromList(page, title);

    // A brand-new ticket has no escalation history.
    await expect(page.getByText(/Escalation L[1-3]/)).toHaveCount(0);
    const banner = page.getByTestId('sla-banner');
    await expect(banner).toBeVisible();

    await advanceClock(page, 48);

    // Any mutation invalidates the ticket + timeline caches → fresh server state.
    await page
      .getByRole('textbox', { name: 'Comment', exact: true })
      .fill('Checking the current state.');
    await page.getByRole('button', { name: 'Post', exact: true }).click();

    // Staff see the internal escalation events and the overdue banner.
    await expect(page.getByText(/Escalation L[1-3]/).first()).toBeVisible({ timeout: 20_000 });
    await expect(banner).toContainText(/overdue|warning|breach/i);

    // Escalations reached the staff notification feed.
    await page.getByRole('button', { name: /Notifications, \d+ unread/ }).click();
    await expect(page.getByRole('button', { name: /L[1-3] .*on IBX-/ })).toBeVisible({
      timeout: 15_000,
    });
  });

  test('requesters never see escalation events', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === 'phone', 'Desktop flow');
    const title = `E2E escalation hidden ${Date.now()}`;
    await login(page, PEOPLE.employee);
    await createTicket(page, title);

    await advanceClock(page, 48);

    // A requester comment invalidates the timeline; the server still filters
    // internal escalation events out of their view.
    await page
      .getByRole('textbox', { name: 'Add a comment' })
      .fill('Still not working, any update?');
    await page.getByRole('button', { name: 'Post', exact: true }).click();

    await expect(page.getByText('Visible updates only')).toBeVisible();
    await expect(page.getByText(/Escalation L[1-3]/)).toHaveCount(0);
    await expect(page.getByText(/Escalated/i)).toHaveCount(0);
  });
});
