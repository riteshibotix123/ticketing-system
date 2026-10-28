/**
 * MSW server for non-browser contexts (vitest, scripts). The browser entry
 * point is `browser.ts`; this file exists so tests can do
 * `import { server } from '@/mocks/server'; server.listen()`.
 */
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
