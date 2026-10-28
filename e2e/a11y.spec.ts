/**
 * Spec 17: axe (WCAG 2.1 A/AA) on every top-level page, in light and dark.
 * Runs as the Super Admin so every route is reachable.
 */
import { test, expect } from '@playwright/test';
import { PEOPLE, ensureTheme, expectAxeClean, login } from './helpers';

const ROUTES: { link: string | RegExp; heading: string | RegExp }[] = [
  { link: 'Dashboard', heading: /dashboard/i },
  { link: 'Tickets', heading: 'Tickets' },
  { link: 'New ticket', heading: /new ticket|create/i },
  { link: 'Notifications', heading: 'Notifications' },
  { link: 'Access requests', heading: /access requests/i },
  { link: 'Users', heading: 'Users' },
  { link: 'Configuration', heading: 'Departments' },
  { link: 'Audit log', heading: /audit/i },
  { link: 'Reports', heading: 'Reports' },
];

async function sweep(page: import('@playwright/test').Page) {
  for (const route of ROUTES) {
    await page.getByRole('link', { name: route.link }).first().click();
    await expect(page.getByRole('heading', { name: route.heading }).first()).toBeVisible();
    await expectAxeClean(page);
  }

  // Configuration sub-pages (shared ConfigTabs).
  await page.getByRole('link', { name: 'Configuration' }).first().click();
  await page.getByRole('link', { name: 'Policy' }).click();
  await expect(page.getByRole('heading', { name: /SLA and escalation policy/i })).toBeVisible();
  await expectAxeClean(page);

  await page.getByRole('link', { name: 'Admin accounts' }).click();
  await expect(page.getByRole('heading', { name: 'Admin accounts' })).toBeVisible();
  await expectAxeClean(page);

  // A real ticket detail page.
  await page.getByRole('link', { name: 'Tickets' }).first().click();
  await page.getByRole('row').nth(1).click();
  await expect(page.getByTestId('sla-banner')).toBeVisible();
  await expectAxeClean(page);
}

test.describe('accessibility (axe)', () => {
  test('every page is axe-clean in light mode', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === 'phone', 'Desktop sweep');
    await login(page, PEOPLE.superAdmin);
    await ensureTheme(page, 'light');
    await sweep(page);
  });

  test('every page is axe-clean in dark mode', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === 'phone', 'Desktop sweep');
    await login(page, PEOPLE.superAdmin);
    await ensureTheme(page, 'dark');
    await sweep(page);
  });
});
