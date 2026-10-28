export type Role = 'super_admin' | 'admin' | 'spoke' | 'employee';

export type AccountState =
  | 'pending_verification'
  | 'pending_approval'
  | 'active'
  | 'rejected'
  | 'deactivated';

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
  permissions: string[];
  mfa_enabled: boolean;
  theme?: 'system' | 'light' | 'dark';
}

export interface Category {
  id: string;
  department_id: string;
  name: string;
  confidential: boolean;
  active: boolean;
}

export interface Department {
  id: string;
  name: string;
  active: boolean;
  accepts_tickets: boolean;
  spokes: UserRef[];
  escalation_contact: UserRef | null;
  categories: Category[];
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
  | 'resume'
  | 'resolve'
  | 'confirm_closure'
  | 'reopen'
  | 'cancel'
  | 'close_admin'
  | 'comment'
  | 'internal_note'
  | 'manage_collaborators';

export type ScanStatus = 'pending' | 'clean' | 'infected';

export interface Attachment {
  id: string;
  name: string;
  size: number;
  mime: string;
  scan_status: ScanStatus;
}

export interface Ticket {
  id: string;
  title: string;
  description: string;
  department_id: string;
  category_id: string | null;
  category_name: string | null;
  priority: Priority;
  requested_priority: Priority;
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
  next_checkpoint_at: string | null;
  last_team_update_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  reopen_count: number;
  hold: { reason: string; review_date: string } | null;
  resolution_summary: string | null;
  feedback: { rating: number | null; comment: string | null } | null;
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

export type SignupStatus = 'pending' | 'approved' | 'rejected';

export interface SignupRequest {
  id: string;
  name: string;
  email: string;
  email_verified: boolean;
  requested_role: 'employee' | 'admin' | 'super_admin';
  requested_department: string;
  approved_role?: Role;
  approved_department?: string;
  status: SignupStatus;
  decided_by?: UserRef;
  decided_at?: string;
  rejection_reason?: string;
  created_at: string;
  can_approve: boolean;
}

export interface UserListItem extends UserRef {
  roles: Role[];
  state: AccountState;
  department_id: string | null;
  spoke_departments: string[];
  last_login_at: string | null;
  created_at: string;
}

export type ProtectedActionKind = 'deactivate_super_admin' | 'demote_super_admin';

export type ProtectedActionStatus = 'pending' | 'approved' | 'rejected' | 'expired';

export interface ProtectedAction {
  id: string;
  kind: ProtectedActionKind;
  target: UserRef;
  requested_by: UserRef;
  reason: string;
  status: ProtectedActionStatus;
  decided_by?: UserRef;
  decision_reason?: string;
  created_at: string;
  expires_at: string;
  can_decide: boolean;
}

export interface ConfidentialGrant {
  id: string;
  user: UserRef;
  category: Category;
  granted_by: UserRef;
  granted_at: string;
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
  update_warning_hours: number;
  update_cadence_hours: number;
  eta_warning_hours: number;
  escalation_repeat_hours: number;
  requester_reminder_hours: number;
  auto_close_business_days: number | null;
  reopen_window_days: number;
  max_reopens: number;
  sla_mode: 'calendar' | 'business';
  admins_can_manage_departments: boolean;
}

export interface PublicConfig {
  allowed_email_domains: string[];
  departments: { id: string; name: string }[];
  attachment_limits: { max_bytes: number; max_files: number; allowed_mime_types: string[] };
  password_min_length: number;
  first_response_hours: number;
}

export interface EmployeeDashboard {
  open: number;
  awaiting_my_response: number;
  resolved_to_confirm: number;
  closed: number;
  assigned_to_me: number;
  recent_updates: TimelineEvent[];
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

export interface AdminDashboard {
  open_count: number;
  breached_count: number;
  l3_count: number;
  stale_count: number;
  pending_approvals: number;
  sla_met_pct: number | null;
  avg_initial_response_seconds: number | null;
  reopen_rate_pct: number | null;
  by_department: {
    department_id: string;
    name: string;
    on_track: number;
    warning: number;
    breached: number;
  }[] | null;
  attention: Ticket[];
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
