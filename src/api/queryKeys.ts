/**
 * TanStack Query keys. Every mutation invalidates `['ticket', id]`,
 * `['tickets']` and `['dashboard']` (spec 6.3).
 */
export const queryKeys = {
  me: ['me'] as const,
  publicConfig: ['public-config'] as const,

  tickets: (params?: unknown) => ['tickets', params ?? {}] as const,
  ticket: (id: string) => ['ticket', id] as const,
  timeline: (id: string) => ['ticket', id, 'timeline'] as const,

  departments: ['departments'] as const,
  categories: ['categories'] as const,
  policy: ['policy'] as const,

  users: (params?: unknown) => ['users', params ?? {}] as const,
  signupRequests: (params?: unknown) => ['signup-requests', params ?? {}] as const,
  pendingSignupCount: ['signup-requests', 'pending-count'] as const,
  admins: ['admins'] as const,

  notifications: (params?: unknown) => ['notifications', params ?? {}] as const,
  unreadCount: ['notifications', 'unread-count'] as const,

  audit: (params?: unknown) => ['audit', params ?? {}] as const,

  dashboard: (role: string) => ['dashboard', role] as const,
} as const;
