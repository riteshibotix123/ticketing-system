import type { Priority, Role, TicketStatus } from '@/types/domain';

export const APP_NAME = import.meta.env.VITE_APP_NAME || 'Ibotix Tickets';
export const DISPLAY_TZ = import.meta.env.VITE_DISPLAY_TZ || 'Asia/Kolkata';
// Mocks default to on in the dev server and off in production builds: a fresh
// clone needs no .env, while `vite build` only bundles MSW when explicitly asked.
const mocksEnv = import.meta.env.VITE_USE_MOCKS;
export const USE_MOCKS =
  mocksEnv === undefined || mocksEnv === '' ? import.meta.env.DEV : mocksEnv === 'true';
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export const PAGE_SIZE = 25;

/** Exact copy from spec section 11.1 — fixed copy, not server provided. */
export const PRIORITY_MEANING: Record<Priority, string> = {
  low: 'No work blocked, no deadline.',
  medium: 'Work affected, a workaround exists.',
  high: 'A person or team is blocked, no workaround.',
  critical: 'Many people blocked, or a security, legal or business-stopping issue.',
};

export const PRIORITY_LABEL: Record<Priority, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
};

export const PRIORITY_ORDER: Priority[] = ['low', 'medium', 'high', 'critical'];

export const STATUS_LABEL: Record<TicketStatus, string> = {
  new: 'New',
  acknowledged: 'Acknowledged',
  assigned: 'Assigned',
  in_progress: 'In Progress',
  awaiting_requester: 'Awaiting Requester',
  on_hold: 'On Hold',
  resolved: 'Resolved',
  closed: 'Closed',
  reopened: 'Reopened',
  cancelled: 'Cancelled',
};

export const OPEN_STATUSES: TicketStatus[] = [
  'new',
  'acknowledged',
  'assigned',
  'in_progress',
  'awaiting_requester',
  'on_hold',
  'reopened',
];

export const ROLE_LABEL: Record<Role, string> = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  spoke: 'Spoke',
  employee: 'Employee',
};

export const ACCOUNT_STATE_LABEL: Record<string, string> = {
  pending_verification: 'Pending verification',
  pending_approval: 'Pending approval',
  active: 'Active',
  rejected: 'Rejected',
  deactivated: 'Deactivated',
};

/** Ticket tabs keyed by id, filtered per role at render time. */
export const TICKET_TABS = [
  { id: 'mine', label: 'Raised by me', scope: 'mine' },
  { id: 'assigned', label: 'Assigned to me', scope: 'assigned' },
  { id: 'queue', label: 'Department queue', scope: 'queue' },
  { id: 'all', label: 'All tickets', scope: 'all' },
] as const;

export type TicketTabId = (typeof TICKET_TABS)[number]['id'];

export const MIN_PASSWORD_LENGTH = 12;
export const MAX_TITLE_LENGTH = 120;
export const MAX_DESCRIPTION_LENGTH = 5000;

/** Idle session warning before refresh failure is not needed: refresh drives it. */
export const SESSION_EXPIRED_MESSAGE = 'Session expired. Please sign in again.';
