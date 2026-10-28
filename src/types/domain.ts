/**
 * Domain types — intended shapes from the spec (section 5).
 * Generated API types (`src/api/schema.d.ts`) are the source of truth when the
 * real backend is wired up; these are used by the mock layer and adapters.
 */

export type Role = 'super_admin' | 'admin' | 'spoke' | 'resolver' | 'employee';

export type AccountState =
  'pending_verification' | 'pending_approval' | 'active' | 'rejected' | 'deactivated';

export type Priority = 'low' | 'medium' | 'high' | 'critical';

export type TicketStatus =
  | 'new'
  | 'acknowledged'
  | 'assigned'
  | 'in_progress'
  | 'awaiting_requester'
  | 'on_hold'
  | 'resolved'
  | 'closed'
  | 'reopened'
  | 'cancelled';

export interface UserRef {
  id: string;
  name: string;
  email: string;
  title?: string;
}

export interface Me extends UserRef {
  roles: Role[];
  department_id: string | null;
  spoke_departments: string[];
  confidential_departments: string[];
  permissions: string[];
  mfa_enabled: boolean;
  theme?: 'system' | 'light' | 'dark';
}

/** Full user record as returned by `/users`. */
export interface User extends UserRef {
  roles: Role[];
  department_id: string | null;
  state: AccountState;
  spoke_departments: string[];
  confidential_departments: string[];
  mfa_enabled: boolean;
  created_at: string;
  title?: string;
}

export interface Category {
  id: string;
  name: string;
  department_id: string;
  escalation_override?: UserRef | null;
}

export interface Department {
  id: string;
  name: string;
  spokes: UserRef[];
  escalation_primary: UserRef | null;
  escalation_backup: UserRef | null;
  confidential: boolean;
  categories: Category[];
  active: boolean;
}

export type SlaKind = 'initial_response' | 'progress_update' | 'eta';

export interface SlaState {
  level: 0 | 1 | 2 | 3;
  kind: SlaKind | null;
  paused: boolean;
  stopped: boolean;
  due_at: string | null;
  label: string;
}

export type TicketAction =
  | 'acknowledge'
  | 'assign'
  | 'transfer'
  | 'change_priority'
  | 'revise_eta'
  | 'start_work'
  | 'ask_requester'
  | 'hold'
  | 'resolve'
  | 'confirm_closure'
  | 'reopen'
  | 'cancel'
  | 'comment'
  | 'internal_note';

export interface Attachment {
  id: string;
  name: string;
  size: number;
  mime: string;
  scan_status: 'pending' | 'clean' | 'infected';
  url?: string;
}

export interface HoldState {
  reason: string;
  review_date: string;
}

export interface Ticket {
  id: string;
  title: string;
  description: string;
  department_id: string;
  category_id: string;
  category_name: string;
  priority: Priority;
  status: TicketStatus;
  confidential: boolean;
  requester: UserRef;
  owner: UserRef | null;
  assignee: UserRef | null;
  collaborators: UserRef[];
  created_at: string;
  sla_started_at: string;
  acknowledged_at: string | null;
  eta: string | null;
  last_team_update_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  reopen_count: number;
  hold: HoldState | null;
  resolution_summary: string | null;
  sla: SlaState;
  allowed_actions: TicketAction[];
  attachments: Attachment[];
}

export interface Comment {
  id: string;
  ticket_id: string;
  author: UserRef;
  created_at: string;
  body: string;
  internal: boolean;
}

export interface TimelineEvent {
  id: string;
  at: string;
  actor: UserRef | { id: 'system'; name: 'System' };
  type: 'comment' | 'internal_note' | 'audit';
  action?: string;
  detail?: string;
  body?: string;
  public: boolean;
}

export interface SignupRequest {
  id: string;
  name: string;
  email: string;
  email_verified: boolean;
  requested_role: 'employee' | 'admin' | 'super_admin';
  requested_department: string;
  approved_role?: Role;
  approved_department?: string;
  status: 'pending' | 'approved' | 'rejected';
  decided_by?: UserRef;
  decided_at?: string;
  rejection_reason?: string;
  created_at: string;
}

export interface Notification {
  id: string;
  created_at: string;
  read: boolean;
  critical: boolean;
  text: string;
  ticket_id?: string;
  kind: string;
}

export interface AuditEntry {
  id: string;
  at: string;
  actor: UserRef | { id: 'system'; name: 'System' };
  action: string;
  object_type: string;
  object_id: string | null;
  old_value?: unknown;
  new_value?: unknown;
  reason?: string;
  detail?: string;
}

export interface PolicyConfig {
  initial_response_hours: number;
  warning_hours: Record<Priority, number>;
  l3_hours: Record<Priority, number>;
  update_cadence_hours: number;
  sla_mode: 'calendar' | 'business';
  admins_can_manage_departments: boolean;
  requester_reminder_hours: number;
  auto_close_business_days: number | null;
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminDashboard {
  open_count: number;
  sla_met_pct: number;
  avg_initial_response_seconds: number;
  breached_count: number;
  l3_count: number;
  stale_count: number;
  reopen_rate_pct: number;
  by_department: {
    department_id: string;
    name: string;
    on_track: number;
    warning: number;
    breached: number;
  }[];
  attention: Ticket[];
}

export interface SpokeDashboard {
  new_unacknowledged: number;
  approaching_sla: number;
  breached: number;
  stale_or_eta_overdue: number;
  awaiting_requester: number;
  on_hold: number;
  resolved_pending_closure: number;
  attention: Ticket[];
}

export interface EmployeeDashboard {
  open: number;
  awaiting_my_response: number;
  resolved_to_confirm: number;
  closed: number;
  recent_updates: TimelineEvent[];
  attention: Ticket[];
}

export type DashboardData = AdminDashboard | SpokeDashboard | EmployeeDashboard;

/** Public runtime config from `GET /public/config`. */
export interface PublicConfig {
  app_name: string;
  allowed_email_domains: string[];
  max_attachment_bytes: number;
  allowed_attachment_mimes: string[];
  personas_enabled: boolean;
  demo_clock_enabled: boolean;
}
