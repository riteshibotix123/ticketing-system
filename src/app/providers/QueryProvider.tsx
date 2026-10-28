import { QueryClient } from '@tanstack/react-query';
import { isApiError } from '@/api/client';

/**
 * Query client: no refetch on focus, short stale time, and never retry
 * client-side errors (4xx) — only transient 5xx/network failures, once.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        if (isApiError(error)) return error.status >= 500 && failureCount < 1;
        return failureCount < 1;
      },
    },
    mutations: {
      retry: false,
    },
  },
});

export function QueryProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
