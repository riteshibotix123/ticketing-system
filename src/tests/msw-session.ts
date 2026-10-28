/**
 * Shared helpers for the MSW integration suites (spec 15): demo credentials
 * from the seed, a login helper that walks the MFA step, and unique signup
 * emails so tests never collide with seeded accounts.
 */
import { setAccessToken } from '@/api/client';
import { authApi } from '@/api/endpoints/auth';
import type { Paged, Ticket } from '@/types/domain';

export const PASSWORD = 'IbotixDemo@2026';
export const MFA_CODE = '123456';

/** Seeded personas (see src/mocks/seed.ts). */
export const ASHA = 'asha.verma@ibotix.ai'; // employee (no MFA)
export const MEERA = 'meera.iyer@ibotix.ai'; // employee (no MFA)
export const ROHAN = 'rohan.mehta@ibotix.ai'; // Spoke, IT
export const NEHA = 'neha.kapoor@ibotix.ai'; // Spoke, HR (confidential)
export const SANJAY = 'sanjay.rao@ibotix.ai'; // Spoke, FIN (no confidential)
export const PRIYA = 'priya.nair@ibotix.ai'; // Admin
export const KARAN = 'karan.shah@ibotix.ai'; // Super Admin

/** Sign in (walking the MFA step when required) and install the token. */
export async function loginAs(email: string): Promise<void> {
  const res = await authApi.login(email, PASSWORD);
  if (res.mfa_required && res.mfa_token) {
    const mfa = await authApi.mfaVerify(res.mfa_token, MFA_CODE);
    setAccessToken(mfa.access_token ?? null);
    return;
  }
  setAccessToken(res.access_token ?? null);
}

let uniq = 0;
export function uniqueEmail(): string {
  uniq += 1;
  return `integration.tester${uniq}.${Date.now()}@ibotix.ai`;
}

/** A fresh IT ticket raised by the currently signed-in user. */
export async function createItTicket(): Promise<Ticket> {
  const { ticketsApi } = await import('@/api/endpoints/tickets');
  return ticketsApi.create({
    department_id: 'IT',
    category_id: 'c-it-1',
    title: 'Laptop will not boot past the splash screen',
    description:
      'The laptop shows the vendor logo and then goes blank. Power cycling did not help.',
    priority: 'medium',
    confidential: false,
  });
}

/** Future ISO timestamps for ETA / hold review fields. */
export const inHours = (h: number) => new Date(Date.now() + h * 3_600_000).toISOString();

export const pagedItems = <T>(page: Paged<T>): T[] => page.items;
