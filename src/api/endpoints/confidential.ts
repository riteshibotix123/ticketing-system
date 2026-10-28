import { api } from '../client';
import type { ConfidentialGrant } from '@/types/domain';

export interface GrantListParams {
  category_id?: string;
  user_id?: string;
}

export interface GrantPayload {
  user_id: string;
  category_id: string;
}

export const confidentialGrantsApi = {
  list: (params: GrantListParams = {}) =>
    api.get<ConfidentialGrant[]>('/confidential-grants', { ...params }),

  grant: (payload: GrantPayload) => api.post<ConfidentialGrant>('/confidential-grants', payload),

  revoke: (id: string) => api.del<void>(`/confidential-grants/${id}`),
};
