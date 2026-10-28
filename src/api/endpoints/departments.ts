import { api } from '../client';
import type { Category, Department, PolicyConfig, UserRef } from '@/types/domain';

export interface DepartmentCreatePayload {
  id: string;
  name: string;
}

export interface DepartmentUpdatePayload {
  name?: string;
  active?: boolean;
}

export interface CategoryCreatePayload {
  name: string;
  confidential: boolean;
}

export interface CategoryUpdatePayload {
  name?: string;
  active?: boolean;
  confidential?: boolean;
}

export const departmentsApi = {
  list: () => api.get<Department[]>('/departments'),

  create: (payload: DepartmentCreatePayload) =>
    api.post<Department>('/departments', payload),

  update: (id: string, payload: DepartmentUpdatePayload) =>
    api.patch<Department>(`/departments/${id}`, payload),

  members: (id: string) => api.get<UserRef[]>(`/departments/${id}/members`),

  addSpoke: (id: string, user_id: string) =>
    api.post<Department>(`/departments/${id}/spokes`, { user_id }),

  removeSpoke: (id: string, userId: string) =>
    api.del<Department>(`/departments/${id}/spokes/${userId}`),

  setEscalation: (id: string, contact_id: string | null) =>
    api.put<Department>(`/departments/${id}/escalation`, { contact_id }),

  addCategory: (id: string, payload: CategoryCreatePayload) =>
    api.post<Category>(`/departments/${id}/categories`, payload),

  updateCategory: (categoryId: string, payload: CategoryUpdatePayload) =>
    api.patch<Category>(`/categories/${categoryId}`, payload),

  deleteCategory: (categoryId: string) => api.del<void>(`/categories/${categoryId}`),

  policy: () => api.get<PolicyConfig>('/policy'),

  updatePolicy: (payload: PolicyConfig) => api.put<PolicyConfig>('/policy', payload),
};
