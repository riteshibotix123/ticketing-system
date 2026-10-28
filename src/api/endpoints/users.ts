import { api } from '../client';
import type {
  AccountState,
  Paged,
  ProtectedAction,
  ProtectedActionKind,
  ProtectedActionStatus,
  Role,
  SignupRequest,
  SignupStatus,
  UserListItem,
  UserRef,
} from '@/types/domain';

export interface UserListParams {
  q?: string;
  role?: Role;
  state?: AccountState;
  department_id?: string;
  page?: number;
  page_size?: number;
}

export interface SignupRequestListParams {
  status?: SignupStatus;
  page?: number;
  page_size?: number;
}

export interface SpokeDepartmentsPayload {
  spoke_departments: string[];
  reason: string;
}

export interface DeactivateResult {
  result: 'deactivated' | 'protected_request_created';
  open_ticket_count: number;
  protected_action_id: string | null;
}

export interface ProtectedActionListParams {
  status?: ProtectedActionStatus;
  page?: number;
}

export interface CreateProtectedActionPayload {
  kind: ProtectedActionKind;
  target_user_id: string;
  reason: string;
}

export const usersApi = {
  list: (params: UserListParams) => api.get<Paged<UserListItem>>('/users', { ...params }),

  lookup: (q: string) => api.get<UserRef[]>('/users/lookup', { q }),

  updateRoles: (id: string, payload: SpokeDepartmentsPayload) =>
    api.patch<UserListItem>(`/users/${id}/roles`, payload),

  deactivate: (id: string, reason: string) =>
    api.post<DeactivateResult>(`/users/${id}/deactivate`, { reason }),

  activate: (id: string) => api.post<UserListItem>(`/users/${id}/activate`),

  signupRequests: (params: SignupRequestListParams = {}) =>
    api.get<Paged<SignupRequest>>('/signup-requests', { ...params }),

  pendingSignupCount: async () => {
    const page = await api.get<Paged<SignupRequest>>('/signup-requests', {
      status: 'pending',
      page_size: 1,
    });
    return page.total;
  },

  approve: (id: string, payload: { approved_role: Role; approved_department: string }) =>
    api.post<SignupRequest>(`/signup-requests/${id}/approve`, payload),

  reject: (id: string, reason: string) =>
    api.post<SignupRequest>(`/signup-requests/${id}/reject`, { reason }),

  admins: () => api.get<UserListItem[]>('/admins'),

  createAdmin: (user_id: string) => api.post<UserListItem>('/admins', { user_id }),

  removeAdmin: (user_id: string) => api.del<UserListItem>(`/admins/${user_id}`),

  protectedActions: (params: ProtectedActionListParams = {}) =>
    api.get<Paged<ProtectedAction>>('/protected-actions', { ...params }),

  createProtectedAction: (payload: CreateProtectedActionPayload) =>
    api.post<ProtectedAction>('/protected-actions', payload),

  approveProtectedAction: (id: string) =>
    api.post<ProtectedAction>(`/protected-actions/${id}/approve`),

  rejectProtectedAction: (id: string, reason: string) =>
    api.post<ProtectedAction>(`/protected-actions/${id}/reject`, { reason }),
};
