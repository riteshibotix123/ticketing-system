/**
 * Spec 15/17: keyboard-only run — no pointer events from the moment the form
 * is reached. Every control is focused and activated with the keyboard.
 */
import { test, expect } from '@playwright/test';
import { PEOPLE, PASSWORD, futureLocalDateTime, login } from './helpers';

test.describe('keyboard-only flow', () => {
  test('creates a ticket and acknowledges it without a mouse', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === 'phone', 'Desktop flow');
    const title = `E2E keyboard ${Date.now()}`;

    // Login through the form using only the keyboard.
    await page.goto('/login');
    await page.getByRole('textbox', { name: 'Company email' }).focus();
    await page.keyboard.type(PEOPLE.employee);
    await page.getByRole('textbox', { name: 'Password' }).focus();
    await page.keyboard.type(PASSWORD);
    await page.getByRole('button', { name: 'Sign in' }).focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });

    // Open "New ticket" with Enter on the focused link.
    await page.getByRole('link', { name: 'New ticket' }).focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/tickets\/new/);

    // Fill the text fields first: Radix restores focus to its trigger after a
    // select closes, which would otherwise steal focus mid-typing.
    await page.getByRole('textbox', { name: 'Title' }).focus();
    await expect(page.getByRole('textbox', { name: 'Title' })).toBeFocused();
    await page.keyboard.type(title);
    await page.getByRole('textbox', { name: 'Description' }).focus();
    await expect(page.getByRole('textbox', { name: 'Description' })).toBeFocused();
    await page.keyboard.type('Keyboard-only run: the screen flickers on battery power.');

    // Department popover → option.
    await page.getByRole('button', { name: 'Department' }).focus();
    await page.keyboard.press('Enter');
    await page.getByRole('option', { name: /^IT/ }).first().focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('listbox')).toHaveCount(0);

    // Radix category select (enabled once a department is chosen).
    await expect(page.getByRole('combobox', { name: 'Category' })).toBeEnabled();
    await page.getByRole('combobox', { name: 'Category' }).focus();
    await page.keyboard.press('Enter');
    await page.getByRole('option').first().focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('combobox', { name: 'Category' })).toBeFocused();
    await expect(page.getByRole('combobox', { name: 'Category' })).toHaveAttribute(
      'aria-expanded',
      'false',
    );

    await page.getByRole('button', { name: 'Create ticket' }).focus();
    await expect(page.getByRole('button', { name: 'Create ticket' })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/tickets\/IBX-/, { timeout: 20_000 });

    // Switch to the Spoke and acknowledge with the keyboard as well.
    await page.getByRole('button', { name: /account menu/i }).focus();
    await page.keyboard.press('Enter');
    await page.getByRole('menuitem', { name: 'Sign out' }).focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/login/);

    await login(page, PEOPLE.spoke); // login already keyboard-equivalent (fills + submits)
    const ticketsLink = page.getByRole('link', { name: 'Tickets' }).first();
    await ticketsLink.focus();
    await page.keyboard.press('Enter');
    const queue = page.getByRole('tab', { name: 'Department queue' });
    await queue.focus();
    await page.keyboard.press('Enter');
    const search = page.getByRole('searchbox', { name: 'Search tickets', exact: true });
    await search.focus();
    await page.keyboard.type(title);
    const row = page.getByRole('row').filter({ hasText: title }).first();
    await expect(row).toBeVisible();
    await row.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: title })).toBeVisible();

    const ack = page.getByRole('button', { name: 'Acknowledge', exact: true });
    await ack.focus();
    await page.keyboard.press('Enter');
    await page.getByLabel(/^ETA/).focus();
    await page.keyboard.type(futureLocalDateTime(3));
    await page.getByRole('button', { name: 'Acknowledge', exact: true }).last().focus();
    await page.keyboard.press('Enter');
    await expect(page.getByText('Acknowledged', { exact: true }).first()).toBeVisible({
      timeout: 15_000,
    });
  });
});
