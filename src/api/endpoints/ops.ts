import { api } from '../client';
import type {
  AdminDashboard,
  AuditEntry,
  EmployeeDashboard,
  Notification,
  Paged,
  SpokeDashboard,
} from '@/types/domain';

export type DashboardKind = 'admin' | 'spoke' | 'employee';

export type DashboardData = AdminDashboard | SpokeDashboard | EmployeeDashboard;

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

  unreadCount: () => api.get<{ count: number }>('/notifications/unread-count'),

  markRead: (id: string) => api.post<void>(`/notifications/${id}/read`),

  markAllRead: () => api.post<void>('/notifications/read-all'),
};

export const auditApi = {
  list: (params: AuditListParams) => api.get<Paged<AuditEntry>>('/audit', { ...params }),
};

export const dashboardApi = {
  admin: () => api.get<AdminDashboard>('/dashboard/admin'),
  spoke: () => api.get<SpokeDashboard>('/dashboard/spoke'),
  employee: () => api.get<EmployeeDashboard>('/dashboard/employee'),
};

export const reportsApi = {
  export: (type: string, format: string) =>
    api.blob('/reports/export', { type, format }),
};
