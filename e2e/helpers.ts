/**
 * Shared E2E helpers (spec 15/17). The suite runs against the production build
 * served with the MSW mock API (VITE_USE_MOCKS=true), so the seeded demo
 * accounts and the demo-clock endpoint are available.
 */
import { expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

export const PASSWORD = 'IbotixDemo@2026';
export const MFA_CODE = '123456';
export const API_BASE = process.env.E2E_API_BASE_URL ?? 'http://localhost:8000/api/v1';

export const PEOPLE = {
  employee: 'asha.verma@ibotix.ai',
  spoke: 'rohan.mehta@ibotix.ai',
  assignee: 'dev.patel@ibotix.ai',
  admin: 'priya.nair@ibotix.ai',
  superAdmin: 'karan.shah@ibotix.ai',
} as const;

/** Sign in through the real form, walking the MFA step for staff roles. */
export async function login(page: Page, email: string): Promise<void> {
  // A full document load would re-seed the mock DB and drop tickets created
  // earlier in the same test, so only navigate when we are not already on the
  // login page (logout lands there without a reload).
  if (!/\/login(?:\?|$)/.test(page.url())) await page.goto('/login');
  await page.getByRole('textbox', { name: 'Company email' }).fill(email);
  await page.getByRole('textbox', { name: 'Password' }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();

  const verify = page.getByRole('button', { name: 'Verify code' });
  const nav = page.getByRole('link', { name: 'Dashboard' });
  await expect(verify.or(nav).first()).toBeVisible({ timeout: 20_000 });
  if (await verify.isVisible()) {
    await page.getByRole('textbox', { name: 'Verification code' }).fill(MFA_CODE);
    await verify.click();
  }
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
}

export async function logout(page: Page): Promise<void> {
  await page.getByRole('button', { name: /account menu/i }).click();
  await page.getByRole('menuitem', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login/);
}

/** Walk the demo clock via the mock endpoint (same origin as the app's API). */
export async function advanceClock(page: Page, hours: number): Promise<void> {
  const status = await page.evaluate(
    async ({ api, h }) => {
      const res = await fetch(`${api}/dev/clock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hours: h }),
      });
      return res.status;
    },
    { api: API_BASE, h: hours },
  );
  expect(status).toBe(200);
}

/** Future value for datetime-local inputs (3 days ahead, IST-friendly). */
export function futureLocalDateTime(days = 3): string {
  const d = new Date(Date.now() + days * 24 * 3600_000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Create a ticket through the UI and land on its detail page. */
export async function createTicket(page: Page, title: string): Promise<void> {
  await page.getByRole('link', { name: 'New ticket' }).click();
  await expect(page).toHaveURL(/\/tickets\/new/);

  await page.getByRole('button', { name: 'Department' }).click();
  await page.getByRole('option', { name: /^IT/ }).first().click();
  await page.getByRole('combobox', { name: 'Category' }).click();
  await page.getByRole('option').first().click();

  await page.getByRole('textbox', { name: 'Title' }).fill(title);
  await page
    .getByRole('textbox', { name: 'Description' })
    .fill('The laptop shows the vendor logo and then goes blank. Power cycling did not help.');
  await page.getByRole('button', { name: 'Create ticket' }).click();

  await expect(page).toHaveURL(/\/tickets\/IBX-/, { timeout: 20_000 });
  await expect(page.getByRole('heading', { name: title })).toBeVisible();
}

/** Escape a literal string for use inside a RegExp. */
export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Find a ticket by title in the current list view (the list paginates, so the
 * newly created ticket is usually not on page 1) and open its detail page.
 */
export async function openTicketFromList(page: Page, title: string): Promise<void> {
  await page.getByRole('searchbox', { name: 'Search tickets', exact: true }).fill(title);
  await page.getByRole('row').filter({ hasText: title }).first().click();
  await expect(page.getByRole('heading', { name: title })).toBeVisible();
}

/** Navigate inside the SPA without a document load (tokens are memory-only). */
export async function gotoInApp(page: Page, linkName: string | RegExp): Promise<void> {
  await page.getByRole('link', { name: linkName }).first().click();
}

export async function ensureTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  const html = page.locator('html');
  if ((await html.getAttribute('data-theme')) !== theme) {
    await page.getByRole('button', { name: /Switch to (light|dark) theme/ }).click();
  }
  await expect(html).toHaveAttribute('data-theme', theme);
}

/** axe (WCAG 2.1 A/AA) — fails with the violation summary for readable CI logs. */
export async function expectAxeClean(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(
    results.violations,
    JSON.stringify(
      results.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length })),
      null,
      2,
    ),
  ).toEqual([]);
}

/** No horizontal page scroll (spec 17: 400px). */
export async function expectNoHorizontalScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'page must not scroll horizontally').toBeLessThanOrEqual(1);
}
