/** Base URL helper so handlers match exactly what `client.ts` calls. */
import { API_BASE_URL } from '@/lib/constants';

/** Absolute MSW path, e.g. p('/tickets/:id') -> 'http://localhost:8000/api/v1/tickets/:id'. */
export function p(path: string): string {
  return `${API_BASE_URL}${path}`;
}
