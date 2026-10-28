import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom';
import { AppShell, SessionExpiredDialog } from '@/components/layout/AppShell';
import { PublicOnly, RequireAuth, RequirePermission } from './guards';

/** Root element: everything below plus the global session-expired dialog. */
function RootLayout() {
  return (
    <>
      <Outlet />
      <SessionExpiredDialog />
    </>
  );
}

type LazyPage = () => Promise<{ default: React.ComponentType }>;

function lazyPage(load: LazyPage) {
  return async () => ({ Component: (await load()).default });
}

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      // ---- public (anonymous) ------------------------------------------------
      {
        element: <PublicOnly />,
        children: [
          {
            path: '/login',
            lazy: lazyPage(() => import('@/features/auth/pages/LoginPage')),
          },
          {
            path: '/signup',
            lazy: lazyPage(() => import('@/features/auth/pages/SignupPage')),
          },
          {
            path: '/verify-email',
            lazy: lazyPage(() => import('@/features/auth/pages/VerifyEmailPage')),
          },
          {
            path: '/forgot-password',
            lazy: lazyPage(() => import('@/features/auth/pages/ForgotPasswordPage')),
          },
          {
            path: '/reset-password',
            lazy: lazyPage(() => import('@/features/auth/pages/ResetPasswordPage')),
          },
        ],
      },
      // Account-state pages are reachable while signed in as pending/rejected.
      {
        path: '/status/:state',
        lazy: lazyPage(() => import('@/features/auth/pages/StatusPage')),
      },
      { path: '/', element: <Navigate to="/dashboard" replace /> },

      // ---- authenticated app -------------------------------------------------
      {
        element: <RequireAuth />,
        children: [
          {
            element: <AppShell />,
            children: [
              {
                path: '/dashboard',
                lazy: lazyPage(() => import('@/features/dashboard/pages/DashboardPage')),
              },
              {
                path: '/tickets',
                children: [
                  {
                    index: true,
                    lazy: lazyPage(() => import('@/features/tickets/pages/TicketListPage')),
                  },
                  {
                    element: <RequirePermission flag="tickets.create" />,
                    children: [
                      {
                        path: 'new',
                        lazy: lazyPage(() => import('@/features/tickets/pages/TicketCreatePage')),
                      },
                    ],
                  },
                  {
                    path: ':id',
                    lazy: lazyPage(() => import('@/features/tickets/pages/TicketDetailPage')),
                  },
                ],
              },
              {
                path: '/notifications',
                lazy: lazyPage(() => import('@/features/notifications/pages/NotificationsPage')),
              },
              {
                element: <RequirePermission flag="users.approve_employee" />,
                children: [
                  {
                    path: '/approvals',
                    lazy: lazyPage(() => import('@/features/approvals/pages/ApprovalsPage')),
                  },
                ],
              },
              {
                element: <RequirePermission flag="users.manage_roles" />,
                children: [
                  {
                    path: '/users',
                    lazy: lazyPage(() => import('@/features/users/pages/UsersPage')),
                  },
                ],
              },
              {
                element: (
                  <RequirePermission
                    anyOf={['departments.manage', 'policy.manage', 'admins.manage']}
                  />
                ),
                children: [
                  {
                    path: '/config/departments',
                    lazy: lazyPage(() => import('@/features/departments/pages/DepartmentsPage')),
                  },
                  {
                    path: '/config/policy',
                    lazy: lazyPage(() => import('@/features/departments/pages/PolicyPage')),
                  },
                ],
              },
              {
                element: <RequirePermission flag="admins.manage" />,
                children: [
                  {
                    path: '/config/admins',
                    lazy: lazyPage(() => import('@/features/departments/pages/AdminsPage')),
                  },
                ],
              },
              {
                element: <RequirePermission flag="audit.view_all" />,
                children: [
                  {
                    path: '/audit',
                    lazy: lazyPage(() => import('@/features/audit/pages/AuditPage')),
                  },
                ],
              },
              {
                element: <RequirePermission flag="reports.view_org" />,
                children: [
                  {
                    path: '/reports',
                    lazy: lazyPage(() => import('@/features/reports/pages/ReportsPage')),
                  },
                ],
              },
            ],
          },
        ],
      },

      // ---- catch-all ---------------------------------------------------------
      {
        path: '*',
        lazy: lazyPage(() => import('@/components/layout/NotFoundPage')),
      },
    ],
  },
]);
