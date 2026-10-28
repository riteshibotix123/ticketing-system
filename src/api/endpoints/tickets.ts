import { api } from '../client';
import type {
  Attachment,
  Comment,
  Paged,
  Priority,
  Ticket,
  TicketAction,
  TicketStatus,
  TimelineEvent,
} from '@/types/domain';

export type TicketScope = 'mine' | 'assigned' | 'queue' | 'all';

export interface TicketListParams {
  scope?: TicketScope;
  q?: string;
  status?: string[];
  priority?: string[];
  department_id?: string;
  category_id?: string;
  sla_state?: string;
  escalation_level?: number;
  requester_id?: string;
  assignee_id?: string;
  confidential?: boolean;
  overdue_eta?: boolean;
  created_from?: string;
  created_to?: string;
  sort?: string;
  page?: number;
  page_size?: number;
}

export interface CreateTicketPayload {
  department_id: string;
  category_id: string;
  title: string;
  description: string;
  priority: Priority;
  confidential: boolean;
  attachment_ids?: string[];
}

/** Server decides which buttons the UI renders (spec 9.7). */
export type TicketActionBody = Partial<{
  eta: string | null;
  no_eta_reason: string;
  checkpoint: string;
  assignee_id: string;
  department_id: string;
  category_id: string;
  priority: Priority;
  reason: string;
  status: Extract<TicketStatus, 'in_progress' | 'awaiting_requester'>;
  review_date: string;
  summary: string;
  message: string;
}>;

export const ticketsApi = {
  list: (params: TicketListParams) => api.get<Paged<Ticket>>('/tickets', { ...params }),

  get: (id: string) => api.get<Ticket>(`/tickets/${id}`),

  timeline: (id: string) => api.get<TimelineEvent[]>(`/tickets/${id}/timeline`),

  create: (payload: CreateTicketPayload) => api.post<Ticket>('/tickets', payload),

  comment: (id: string, body: string, internal: boolean) =>
    api.post<Comment>(`/tickets/${id}/comments`, { body, internal }),

  act: (id: string, action: TicketAction, body: TicketActionBody = {}) =>
    api.post<Ticket>(`/tickets/${id}/${endpointFor(action)}`, body),

  uploadAttachment: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api.upload<Attachment>('/attachments', form);
  },
};

function endpointFor(action: TicketAction): string {
  switch (action) {
    case 'acknowledge':
      return 'acknowledge';
    case 'assign':
      return 'assign';
    case 'transfer':
      return 'transfer';
    case 'change_priority':
      return 'priority';
    case 'revise_eta':
      return 'eta';
    case 'start_work':
    case 'ask_requester':
      return 'status';
    case 'hold':
      return 'hold';
    case 'resolve':
      return 'resolve';
    case 'confirm_closure':
      return 'confirm-closure';
    case 'reopen':
      return 'reopen';
    case 'cancel':
      return 'cancel';
    case 'comment':
    case 'internal_note':
      throw new Error('Use ticketsApi.comment for comments');
  }
}
