/**
 * Spec 17: phone width (400px) — no horizontal page scroll on any top-level
 * page, including a ticket detail. Runs on the `phone` project only.
 */
import { test } from '@playwright/test';
import { PEOPLE, expectNoHorizontalScroll, login } from './helpers';

const LINKS = [
  'Dashboard',
  'Tickets',
  'New ticket',
  'Notifications',
  'Access requests',
  'Users',
  'Configuration',
  'Audit log',
  'Reports',
] as const;

test.describe('phone width (400px)', () => {
  test('no horizontal page scroll anywhere', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'phone', 'Phone project only');
    await login(page, PEOPLE.superAdmin);

    for (const name of LINKS) {
      await page.getByRole('link', { name }).first().click();
      await page.getByRole('main').waitFor();
      await expectNoHorizontalScroll(page);
    }

    // Configuration sub-pages.
    await page.getByRole('link', { name: 'Configuration' }).first().click();
    await page.getByRole('link', { name: 'Policy' }).click();
    await page.getByRole('main').waitFor();
    await expectNoHorizontalScroll(page);

    await page.getByRole('link', { name: 'Admin accounts' }).click();
    await page.getByRole('main').waitFor();
    await expectNoHorizontalScroll(page);

    // Ticket detail (widest content: banner, action forms, timeline).
    await page.getByRole('link', { name: 'Tickets' }).first().click();
    await page.getByRole('row').nth(1).click();
    await page.getByTestId('sla-banner').waitFor();
    await expectNoHorizontalScroll(page);
  });
});
