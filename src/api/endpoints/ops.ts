import { api } from '../client';
import type {
  AuditEntry,
  EmployeeDashboard,
  AdminDashboard,
  Paged,
  Notification,
  SpokeDashboard,
} from '@/types/domain';

export type DashboardKind = 'admin' | 'spoke' | 'employee';

export interface NotificationListParams {
  unread?: boolean;
  page?: number;
  page_size?: number;
}

export interface AuditListParams {
  q?: string;
  actor_id?: string;
  action?: string;
  ticket_id?: string;
  from?: string;
  to?: string;
  page?: number;
  page_size?: number;
}

export const notificationsApi = {
  list: (params: NotificationListParams) =>
    api.get<Paged<Notification>>('/notifications', { ...params }),

  unreadCount: () =>
    api.get<{ count: number }>('/notifications', { unread: true, count_only: true }),

  markRead: (id: string) => api.post<Notification>(`/notifications/${id}/read`),

  markAllRead: () => api.post<{ updated: number }>('/notifications/read-all'),
};

export const auditApi = {
  list: (params: AuditListParams) => api.get<Paged<AuditEntry>>('/audit', { ...params }),
};

export const dashboardApi = {
  admin: () => api.get<AdminDashboard>('/dashboard/admin'),
  spoke: () => api.get<SpokeDashboard>('/dashboard/spoke'),
  employee: () => api.get<EmployeeDashboard>('/dashboard/employee'),
};
