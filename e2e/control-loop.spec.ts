/**
 * Spec 15/17: the BRD section-20 control loop end to end, through the UI only.
 * Employee raises → Spoke acknowledges and delegates → Resolver resolves →
 * Requester confirms the closure.
 */
import { test, expect } from '@playwright/test';
import {
  PEOPLE,
  createTicket,
  futureLocalDateTime,
  login,
  logout,
  openTicketFromList,
} from './helpers';

test.describe('BRD §20 control loop', () => {
  test('create → acknowledge → assign → resolve → confirm closure', async ({ page }, testInfo) => {
    test.skip(
      testInfo.project.name === 'phone',
      'Desktop flow; responsiveness is covered separately',
    );
    const title = `E2E laptop ${Date.now()}`;

    // 1. Requester raises the ticket.
    await login(page, PEOPLE.employee);
    await createTicket(page, title);

    // Requester view: no internal notes and no staff actions.
    await expect(page.getByText('Visible updates only')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Internal note' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Acknowledge' })).toHaveCount(0);

    // 2. The department Spoke acknowledges with an ETA and delegates.
    await logout(page);
    await login(page, PEOPLE.spoke);
    await page.getByRole('link', { name: 'Tickets' }).first().click();
    await page.getByRole('tab', { name: 'Department queue' }).click();
    await openTicketFromList(page, title);

    await page.getByRole('button', { name: 'Acknowledge', exact: true }).click();
    await page.getByLabel(/^ETA/).fill(futureLocalDateTime(3));
    await page.getByRole('button', { name: 'Acknowledge', exact: true }).last().click();
    await expect(page.getByText('Acknowledged', { exact: true }).first()).toBeVisible({
      timeout: 15_000,
    });

    await page.getByRole('button', { name: 'Assign / delegate' }).click();
    await page.getByRole('combobox', { name: 'Person' }).click();
    await page.getByRole('option', { name: /Dev Patel/ }).click();
    await page.getByRole('button', { name: 'Delegate', exact: true }).click();
    await expect(page.getByRole('main')).toContainText('Delegated to Dev Patel');

    // 3. The resolver resolves it.
    await logout(page);
    await login(page, PEOPLE.resolver);
    await page.getByRole('link', { name: 'Tickets' }).first().click();
    await page.getByRole('tab', { name: 'Assigned to me' }).click();
    await openTicketFromList(page, title);
    await page.getByRole('button', { name: 'Resolve', exact: true }).click();
    await page
      .getByLabel(/^Resolution summary/)
      .fill('Replaced the docking station cable and verified the display.');
    await page.getByRole('button', { name: 'Resolve', exact: true }).last().click();
    await expect(page.getByRole('main')).toContainText('Resolution summary');

    // 4. The requester confirms the closure.
    await logout(page);
    await login(page, PEOPLE.employee);
    await page.getByRole('link', { name: 'Tickets' }).first().click();
    await openTicketFromList(page, title);
    await page.getByRole('button', { name: 'Confirm closure' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Confirm closure' }).click();
    await expect(page.getByRole('main')).toContainText('Confirmed closed by Asha Verma');
  });
});
