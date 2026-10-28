import { lazy, Suspense } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import { queryClient } from './providers/QueryProvider';
import { AuthProvider } from './providers/AuthProvider';
import { ThemeProvider } from '@/hooks/useTheme';
import { ToastProvider } from '@/hooks/useToast';
import { TooltipProvider } from '@/components/ui/tooltip';
import { router } from './router';

const showDevPanel = import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === 'true';
/** Dev-only persona switcher + demo clock; stripped from production builds. */
const DevPanel = showDevPanel ? lazy(() => import('@/mocks/ui/DevPanel')) : null;

/**
 * Providers: QueryClient, Theme, Toaster, Tooltip, Auth, Router (spec 2.2).
 */
export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>
          <TooltipProvider delayDuration={250}>
            <AuthProvider>
              <RouterProvider router={router} />
              {DevPanel ? (
                <Suspense fallback={null}>
                  <DevPanel />
                </Suspense>
              ) : null}
            </AuthProvider>
          </TooltipProvider>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
