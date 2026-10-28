/**
 * Browser entry point for the MSW mock API (spec 14). `main.tsx` calls
 * `startMocks()` before rendering when VITE_USE_MOCKS=true; the worker
 * intercepts every request to the mock API origin and answers from the
 * in-memory database (handlers/index.ts seeds it on import).
 */
import { setupWorker, type SetupWorker } from 'msw/browser';
import { handlers } from './handlers';

let worker: SetupWorker | null = null;

export async function startMocks(): Promise<void> {
  if (import.meta.env.VITE_USE_MOCKS !== 'true') return;
  if (worker) return; // StrictMode double-invoke safe
  worker = setupWorker(...handlers);
  await worker.start({
    serviceWorker: { url: '/mockServiceWorker.js' },
    onUnhandledRequest: 'bypass', // let Vite's own assets through untouched
  });
}

/** Test/demo helper: stop the worker (used by e2e teardown if needed). */
export function stopMocks(): void {
  worker?.stop();
  worker = null;
}
