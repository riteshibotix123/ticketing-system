import { api } from '../client';
import type { Department, PolicyConfig, UserRef } from '@/types/domain';

export interface DepartmentPayload {
  name: string;
  active: boolean;
  confidential: boolean;
}

export const departmentsApi = {
  list: () => api.get<Department[]>('/departments'),

  create: (payload: DepartmentPayload) => api.post<Department>('/departments', payload),

  update: (id: string, payload: Partial<DepartmentPayload>) =>
    api.patch<Department>(`/departments/${id}`, payload),

  addSpoke: (id: string, user_id: string) =>
    api.post<Department>(`/departments/${id}/spokes`, { user_id }),

  removeSpoke: (id: string, userId: string) =>
    api.del<Department>(`/departments/${id}/spokes/${userId}`),

  setEscalation: (id: string, primary_id: string | null, backup_id: string | null) =>
    api.put<Department>(`/departments/${id}/escalation`, { primary_id, backup_id }),

  addCategory: (id: string, name: string) =>
    api.post<Department>(`/departments/${id}/categories`, { name }),

  updateCategory: (
    categoryId: string,
    payload: { name?: string; escalation_override_id?: string | null },
  ) => api.patch<Department>(`/categories/${categoryId}`, payload),

  deleteCategory: (categoryId: string) => api.del<Department>(`/categories/${categoryId}`),

  policy: () => api.get<PolicyConfig>('/policy'),

  updatePolicy: (payload: PolicyConfig) => api.put<PolicyConfig>('/policy', payload),
};

export type { UserRef };
