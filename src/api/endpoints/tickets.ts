import { api } from '../client';
import type {
  Attachment,
  Paged,
  Priority,
  Ticket,
  TicketAction,
  TicketStatus,
  TimelineEvent,
} from '@/types/domain';

export type TicketScope = 'mine' | 'assigned' | 'queue' | 'all';

export type SlaStateFilter = 'unacknowledged' | 'warning' | 'breached' | 'stale';

export interface TicketListParams {
  scope?: TicketScope;
  q?: string;
  status?: (TicketStatus | 'open')[];
  priority?: Priority[];
  department_id?: string;
  category_id?: string;
  sla_state?: SlaStateFilter;
  escalation_level?: 0 | 1 | 2 | 3;
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
  category_id: string | null;
  title: string;
  description: string;
  priority: Priority;
  confidential: boolean;
  attachment_ids?: string[];
}

export interface AcknowledgePayload {
  eta?: string;
  no_eta_reason?: string;
  next_checkpoint_at?: string;
}

export interface AssignPayload {
  assignee_id: string;
  reason?: string;
}

export interface TransferPayload {
  department_id: string;
  category_id?: string;
  reason: string;
}

export interface PriorityPayload {
  priority: Priority;
  reason: string;
}

export interface EtaPayload {
  eta: string;
  reason: string;
}

export interface StatusPayload {
  status: 'in_progress' | 'awaiting_requester';
  message?: string;
}

export interface HoldPayload {
  reason: string;
  review_date: string;
}

export interface ResolvePayload {
  summary: string;
}

export interface ConfirmClosurePayload {
  rating?: number;
  comment?: string;
}

export interface ReasonPayload {
  reason: string;
}

export type CommentResult = TimelineEvent;

export type TicketActionBody = Record<string, unknown>;

export const ticketsApi = {
  list: (params: TicketListParams) => api.get<Paged<Ticket>>('/tickets', { ...params }),

  get: (id: string) => api.get<Ticket>(`/tickets/${id}`),

  timeline: (id: string) => api.get<TimelineEvent[]>(`/tickets/${id}/timeline`),

  create: (payload: CreateTicketPayload) => api.post<Ticket>('/tickets', payload),

  comment: (id: string, body: string, internal: boolean) =>
    api.post<CommentResult>(`/tickets/${id}/comments`, { body, internal }),

  acknowledge: (id: string, payload: AcknowledgePayload) =>
    api.post<Ticket>(`/tickets/${id}/acknowledge`, payload),

  assign: (id: string, payload: AssignPayload) =>
    api.post<Ticket>(`/tickets/${id}/assign`, payload),

  transfer: (id: string, payload: TransferPayload) =>
    api.post<Ticket>(`/tickets/${id}/transfer`, payload),

  changePriority: (id: string, payload: PriorityPayload) =>
    api.post<Ticket>(`/tickets/${id}/priority`, payload),

  reviseEta: (id: string, payload: EtaPayload) =>
    api.post<Ticket>(`/tickets/${id}/eta`, payload),

  setStatus: (id: string, payload: StatusPayload) =>
    api.post<Ticket>(`/tickets/${id}/status`, payload),

  hold: (id: string, payload: HoldPayload) =>
    api.post<Ticket>(`/tickets/${id}/hold`, payload),

  resolve: (id: string, payload: ResolvePayload) =>
    api.post<Ticket>(`/tickets/${id}/resolve`, payload),

  confirmClosure: (id: string, payload: ConfirmClosurePayload) =>
    api.post<Ticket>(`/tickets/${id}/confirm-closure`, payload),

  reopen: (id: string, payload: ReasonPayload) =>
    api.post<Ticket>(`/tickets/${id}/reopen`, payload),

  cancel: (id: string, payload: ReasonPayload) =>
    api.post<Ticket>(`/tickets/${id}/cancel`, payload),

  close: (id: string, payload: ReasonPayload) =>
    api.post<Ticket>(`/tickets/${id}/close`, payload),

  addCollaborator: (id: string, user_id: string) =>
    api.post<Ticket>(`/tickets/${id}/collaborators`, { user_id }),

  removeCollaborator: (id: string, userId: string) =>
    api.del<Ticket>(`/tickets/${id}/collaborators/${userId}`),

  act: (id: string, action: TicketAction, body: Record<string, unknown> = {}) =>
    api.post<Ticket>(`/tickets/${id}/${endpointFor(action)}`, body),

  uploadAttachment: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api.upload<Attachment>('/attachments', form);
  },

  downloadAttachment: (id: string) => api.blob(`/attachments/${id}/download`),
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
    case 'resume':
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
    case 'close_admin':
      return 'close';
    case 'comment':
    case 'internal_note':
      throw new Error('Use ticketsApi.comment for comments');
    case 'manage_collaborators':
      throw new Error('Use ticketsApi.addCollaborator or removeCollaborator');
  }
}
