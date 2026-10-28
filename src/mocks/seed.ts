/**
 * Seed data (spec section 14).
 * Password for EVERY seeded user: `IbotixDemo@2026` (see auth.DEMO_PASSWORD).
 * Emails follow firstname.lastname@ibotix.ai.
 *
 * Engineering is seeded ACTIVE with no Spoke on purpose so the UI can
 * demonstrate the "No active Spoke yet" rule (tickets cannot be raised there;
 * the 422 rule is enforced on department mutations, not on the seed itself).
 */
import type { Department, SignupRequest, User } from '@/types/domain';
import { clearDatabase, db, findUser, ref, type DbUser } from './db';
import { buildSeedTickets } from './seedTickets';
import { addAudit, notifyUsers } from './helpers';
import { DEMO_PASSWORD } from './auth';

const agoIso = (h: number): string => new Date(Date.now() - h * 3_600_000).toISOString();

interface SeedUser {
  id: string;
  name: string;
  title?: string;
  roles: User['roles'];
  department_id: string | null;
  spoke_departments?: string[];
  confidential_departments?: string[];
  state?: User['state'];
  createdH?: number;
}

const USERS: SeedUser[] = [
  {
    id: 'u-asha',
    name: 'Asha Verma',
    title: 'Software Engineer',
    roles: ['employee'],
    department_id: 'ENG',
    createdH: 900,
  },
  {
    id: 'u-meera',
    name: 'Meera Iyer',
    title: 'Finance Analyst',
    roles: ['employee'],
    department_id: 'FIN',
    createdH: 870,
  },
  {
    id: 'u-dev',
    name: 'Dev Patel',
    title: 'IT Support Engineer',
    roles: ['resolver'],
    department_id: 'IT',
    createdH: 700,
  },
  {
    id: 'u-rohan',
    name: 'Rohan Mehta',
    title: 'IT Lead',
    roles: ['spoke'],
    department_id: 'IT',
    spoke_departments: ['IT'],
    createdH: 1200,
  },
  {
    id: 'u-isha',
    name: 'Isha Gupta',
    title: 'Senior IT Analyst',
    roles: ['spoke'],
    department_id: 'IT',
    spoke_departments: ['IT'],
    createdH: 1150,
  },
  {
    id: 'u-neha',
    name: 'Neha Kapoor',
    title: 'HR Business Partner',
    roles: ['spoke'],
    department_id: 'HR',
    spoke_departments: ['HR'],
    confidential_departments: ['HR'],
    createdH: 1100,
  },
  {
    id: 'u-sanjay',
    name: 'Sanjay Rao',
    title: 'Finance Manager',
    roles: ['spoke'],
    department_id: 'FIN',
    spoke_departments: ['FIN'],
    createdH: 1050,
  },
  {
    id: 'u-tara',
    name: 'Tara Joshi',
    title: 'Facilities Manager',
    roles: ['spoke'],
    department_id: 'FAC',
    spoke_departments: ['FAC'],
    createdH: 1000,
  },
  {
    id: 'u-vikram',
    name: 'Vikram Singh',
    title: 'CISO',
    roles: ['spoke'],
    department_id: 'SEC',
    spoke_departments: ['SEC'],
    confidential_departments: ['SEC'],
    createdH: 980,
  },
  {
    id: 'u-aarav',
    name: 'Aarav Khanna',
    title: 'Legal Counsel',
    roles: ['spoke'],
    department_id: 'LGL',
    spoke_departments: ['LGL'],
    confidential_departments: ['LGL'],
    createdH: 960,
  },
  {
    id: 'u-priya',
    name: 'Priya Nair',
    title: 'Operations Admin',
    roles: ['admin'],
    department_id: null,
    createdH: 1300,
  },
  {
    id: 'u-karan',
    name: 'Karan Shah',
    title: 'CTO',
    roles: ['super_admin'],
    department_id: null,
    createdH: 1400,
  },
  // CEO sits in the L3 escalation group (spec 1.3.4 "Super Admin / CXO group").
  {
    id: 'u-aditya',
    name: 'Aditya Ranjan',
    title: 'CEO',
    roles: ['super_admin'],
    department_id: null,
    createdH: 1400,
  },
  // Pending signup requests (approved via the Approvals screen in the demo).
  {
    id: 'u-kabir',
    name: 'Kabir Sethi',
    roles: [],
    department_id: 'ENG',
    state: 'pending_approval',
    createdH: 30,
  },
  {
    id: 'u-ritu',
    name: 'Ritu Bansal',
    roles: [],
    department_id: 'HR',
    state: 'pending_approval',
    createdH: 20,
  },
  {
    id: 'u-farhan',
    name: 'Farhan Qureshi',
    roles: [],
    department_id: 'IT',
    state: 'pending_approval',
    createdH: 10,
  },
];

function emailFor(name: string): string {
  return `${name.toLowerCase().replace(/\s+/g, '.')}@ibotix.ai`;
}

function seedUsers(): void {
  for (const su of USERS) {
    const mfa = su.roles.some((r) => r === 'spoke' || r === 'admin' || r === 'super_admin');
    const user: DbUser = {
      id: su.id,
      name: su.name,
      email: emailFor(su.name),
      ...(su.title ? { title: su.title } : {}),
      roles: su.roles,
      department_id: su.department_id,
      state: su.state ?? 'active',
      spoke_departments: su.spoke_departments ?? [],
      confidential_departments: su.confidential_departments ?? [],
      mfa_enabled: mfa,
      created_at: agoIso(su.createdH ?? 500),
      password: DEMO_PASSWORD,
    };
    db.users.push(user);
  }
}

function seedDepartments(): void {
  const u = (id: string) => {
    const user = findUser(id);
    if (!user) throw new Error(`Seed error: unknown user ${id}`);
    return ref(user);
  };
  const departments: Department[] = [
    {
      id: 'IT',
      name: 'IT',
      spokes: [u('u-rohan'), u('u-isha')],
      escalation_primary: u('u-rohan'),
      escalation_backup: u('u-isha'),
      confidential: false,
      active: true,
      categories: [
        { id: 'c-it-1', name: 'Access & Accounts', department_id: 'IT' },
        { id: 'c-it-2', name: 'Hardware', department_id: 'IT' },
        { id: 'c-it-3', name: 'Software & Licenses', department_id: 'IT' },
        { id: 'c-it-4', name: 'Network & VPN', department_id: 'IT' },
      ],
    },
    {
      id: 'HR',
      name: 'HR',
      spokes: [u('u-neha')],
      escalation_primary: u('u-neha'),
      escalation_backup: u('u-priya'),
      confidential: true,
      active: true,
      categories: [
        { id: 'c-hr-1', name: 'Payroll & Benefits', department_id: 'HR' },
        { id: 'c-hr-2', name: 'Leave & Attendance', department_id: 'HR' },
        { id: 'c-hr-3', name: 'Workplace Concerns', department_id: 'HR' },
      ],
    },
    {
      id: 'FIN',
      name: 'Finance',
      spokes: [u('u-sanjay')],
      escalation_primary: u('u-sanjay'),
      escalation_backup: u('u-priya'),
      confidential: false,
      active: true,
      categories: [
        { id: 'c-fin-1', name: 'Expenses & Reimbursement', department_id: 'FIN' },
        { id: 'c-fin-2', name: 'Invoices & Payments', department_id: 'FIN' },
        { id: 'c-fin-3', name: 'Finance Systems Access', department_id: 'FIN' },
      ],
    },
    {
      id: 'FAC',
      name: 'Facilities',
      spokes: [u('u-tara')],
      escalation_primary: u('u-tara'),
      escalation_backup: u('u-priya'),
      confidential: false,
      active: true,
      categories: [
        { id: 'c-fac-1', name: 'Workspace & Seating', department_id: 'FAC' },
        { id: 'c-fac-2', name: 'Repairs & Maintenance', department_id: 'FAC' },
        { id: 'c-fac-3', name: 'Housekeeping', department_id: 'FAC' },
      ],
    },
    {
      id: 'SEC',
      name: 'Security',
      spokes: [u('u-vikram')],
      escalation_primary: u('u-vikram'),
      escalation_backup: u('u-karan'),
      confidential: true,
      active: true,
      categories: [
        { id: 'c-sec-1', name: 'Incident Response', department_id: 'SEC' },
        { id: 'c-sec-2', name: 'Suspicious Activity', department_id: 'SEC' },
        { id: 'c-sec-3', name: 'Access Reviews', department_id: 'SEC' },
      ],
    },
    {
      id: 'LGL',
      name: 'Legal',
      spokes: [u('u-aarav')],
      escalation_primary: u('u-aarav'),
      escalation_backup: u('u-priya'),
      confidential: true,
      active: true,
      categories: [
        { id: 'c-lgl-1', name: 'Contracts', department_id: 'LGL' },
        { id: 'c-lgl-2', name: 'Compliance & Policies', department_id: 'LGL' },
        { id: 'c-lgl-3', name: 'Data & Privacy', department_id: 'LGL' },
      ],
    },
    {
      // No active Spoke: the create-ticket form must disable it with
      // "No active Spoke yet" (spec 9.5 / requirement 15).
      id: 'ENG',
      name: 'Engineering',
      spokes: [],
      escalation_primary: null,
      escalation_backup: null,
      confidential: false,
      active: true,
      categories: [
        { id: 'c-eng-1', name: 'Developer Tooling', department_id: 'ENG' },
        { id: 'c-eng-2', name: 'Code & Reviews', department_id: 'ENG' },
      ],
    },
  ];
  db.departments.push(...departments);
}

function seedSignupRequests(): void {
  const rows: Array<Omit<SignupRequest, 'id' | 'created_at'> & { createdH: number }> = [
    {
      name: 'Kabir Sethi',
      email: emailFor('Kabir Sethi'),
      email_verified: true,
      requested_role: 'employee',
      requested_department: 'ENG',
      status: 'pending',
      createdH: 30,
    },
    {
      name: 'Ritu Bansal',
      email: emailFor('Ritu Bansal'),
      email_verified: true,
      requested_role: 'admin',
      requested_department: 'HR',
      status: 'pending',
      createdH: 20,
    },
    {
      name: 'Farhan Qureshi',
      email: emailFor('Farhan Qureshi'),
      email_verified: true,
      requested_role: 'super_admin',
      requested_department: 'IT',
      status: 'pending',
      createdH: 10,
    },
    // Decided history so the Approvals screen has a list below the pending one.
    {
      name: 'Dev Patel',
      email: emailFor('Dev Patel'),
      email_verified: true,
      requested_role: 'employee',
      requested_department: 'IT',
      approved_role: 'resolver',
      approved_department: 'IT',
      status: 'approved',
      decided_by: ref(findUser('u-priya')!),
      decided_at: agoIso(700),
      createdH: 720,
    },
  ];
  rows.forEach((row, index) => {
    const { createdH, ...rest } = row;
    db.signupRequests.push({ ...rest, id: `sr-seed-${index + 1}`, created_at: agoIso(createdH) });
  });

  // Approvers learn about the pending requests (spec 12).
  const pending = db.signupRequests.filter((r) => r.status === 'pending');
  for (const req of pending) {
    const recipients =
      req.requested_role === 'employee' ? ['u-priya', 'u-karan'] : ['u-karan', 'u-aditya'];
    notifyUsers(recipients, {
      text: `New access request from ${req.name} (${req.requested_role.replace('_', ' ')}) — ${req.requested_department}.`,
      kind: 'signup_request',
      at: req.created_at,
      read: Date.now() - Date.parse(req.created_at) > 12 * 3_600_000,
    });
  }
}

function seedStandaloneAudit(): void {
  const entries = [
    {
      at: agoIso(700),
      actor: ref(findUser('u-priya')!),
      action: 'user.roles_updated',
      object_type: 'user',
      object_id: 'u-dev',
      detail: 'Granted Resolver in IT',
      reason: 'Onboarding the IT support rota',
    },
    {
      at: agoIso(300),
      actor: ref(findUser('u-karan')!),
      action: 'department.spoke_added',
      object_type: 'department',
      object_id: 'IT',
      detail: 'Added Isha Gupta as Spoke',
    },
    {
      at: agoIso(290),
      actor: ref(findUser('u-priya')!),
      action: 'department.category_added',
      object_type: 'department',
      object_id: 'SEC',
      detail: 'Added category Access Reviews',
    },
    {
      at: agoIso(260),
      actor: ref(findUser('u-karan')!),
      action: 'policy.updated',
      object_type: 'policy',
      object_id: null,
      detail: 'Initial response 24h, L1 at 18h (Critical 12h), L3 at 48h',
    },
    {
      at: agoIso(200),
      actor: ref(findUser('u-priya')!),
      action: 'notification.settings',
      object_type: 'system',
      object_id: null,
      detail: 'Critical escalation emails remain mandatory for all users',
    },
  ];
  for (const e of entries) addAudit(e);
}

/** Idempotent: reseeding is a no-op until `clearDatabase()` runs. */
export function seedDatabase(): void {
  if (db.users.length > 0) return;
  seedUsers();
  seedDepartments();
  seedSignupRequests();
  seedStandaloneAudit(); // ticket history audit is appended by buildSeedTickets
  buildSeedTickets();
}

/** Wipe and rebuild (used by tests and the dev panel reset). */
export function resetDatabase(): void {
  clearDatabase();
  seedDatabase();
}
