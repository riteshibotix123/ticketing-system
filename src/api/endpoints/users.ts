import { api, apiFetch } from '../client';
import type { Me, Paged, Role, SignupRequest, User } from '@/types/domain';

export interface UserListParams {
  q?: string;
  role?: string;
  state?: string;
  department_id?: string;
  page?: number;
  page_size?: number;
}

export interface RoleUpdatePayload {
  add?: Role[];
  remove?: Role[];
  department_ids?: string[];
  confidential_departments?: string[];
  reason: string;
}

export const usersApi = {
  list: (params: UserListParams) => api.get<Paged<User>>('/users', { ...params }),

  updateRoles: (id: string, payload: RoleUpdatePayload) =>
    api.patch<User>(`/users/${id}/roles`, payload),

  deactivate: (id: string, reason: string) => api.post<User>(`/users/${id}/deactivate`, { reason }),

  activate: (id: string, reason: string) => api.post<User>(`/users/${id}/activate`, { reason }),

  signupRequests: (status?: string) =>
    api.get<Paged<SignupRequest>>('/signup-requests', { status, page_size: 100 }),

  pendingCount: () =>
    api.get<{ count: number }>('/signup-requests', { status: 'pending', count_only: true }),

  approve: (id: string, payload: { approved_role: Role; approved_department: string }) =>
    api.post<SignupRequest>(`/signup-requests/${id}/approve`, payload),

  reject: (id: string, reason: string) =>
    api.post<SignupRequest>(`/signup-requests/${id}/reject`, { reason }),

  admins: () => api.get<Paged<User>>('/admins', { page_size: 100 }),

  createAdmin: (payload: { email: string; name: string }) => api.post<User>('/admins', payload),

  // Rule 10/14: account changes carry a reason and are audit logged server-side.
  deactivateAdmin: (id: string, reason?: string) =>
    api.post<User>(`/admins/${id}/deactivate`, { reason }),

  activateAdmin: (id: string, reason?: string) =>
    api.post<User>(`/admins/${id}/activate`, { reason }),

  removeAdmin: (id: string, reason?: string) =>
    apiFetch<{ status: string }>(`/admins/${id}`, { method: 'DELETE', body: { reason } }),
};

export type { Me };
