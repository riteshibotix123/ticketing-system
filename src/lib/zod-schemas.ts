import { z } from 'zod';
import { MAX_DESCRIPTION_LENGTH, MAX_TITLE_LENGTH, MIN_PASSWORD_LENGTH } from './constants';

const requiredMessage = 'Required.';
const futureMessage = 'Pick a date and time in the future.';
const departmentCode = /^[A-Z]{2,6}$/;

const isFuture = (value?: string): boolean =>
  Boolean(value) && new Date(value as string).getTime() > Date.now();

const optionalReason = z.preprocess(
  (value) => (value === '' ? undefined : value),
  z.string().trim().min(5, 'Use at least 5 characters.').max(1000, 'Too long.').optional(),
);

export const reasonSchema = z.object({
  reason: z.string().trim().min(5, 'Use at least 5 characters.').max(1000, 'Too long.'),
});
export type ReasonInput = z.infer<typeof reasonSchema>;

export const passwordSchema = z
  .string()
  .min(MIN_PASSWORD_LENGTH, `Use at least ${MIN_PASSWORD_LENGTH} characters.`)
  .max(128, 'Use at most 128 characters.')
  .regex(/[a-z]/, 'Add a lowercase letter.')
  .regex(/[A-Z]/, 'Add an uppercase letter.')
  .regex(/\d/, 'Add a digit.');

export const emailSchema = z
  .string()
  .trim()
  .toLowerCase()
  .min(1, requiredMessage)
  .email('Enter a valid email address.');

export const nameSchema = z
  .string()
  .trim()
  .min(2, 'Enter your full name.')
  .max(100, 'Use at most 100 characters.');

export const lookupQuerySchema = z.string().trim().min(2, 'Type at least 2 characters.');

export const signupSchema = z.object({
  name: nameSchema,
  email: emailSchema,
  password: passwordSchema,
  requested_role: z.enum(['employee', 'admin', 'super_admin']),
  requested_department: z.string().trim().regex(departmentCode, 'Pick a department.'),
});
export type SignupInput = z.infer<typeof signupSchema>;

export function signupSchemaFor(allowedDomains: string[]) {
  const domains = allowedDomains.map((domain) => domain.toLowerCase());
  return signupSchema.refine(
    (value) => domains.some((domain) => value.email.endsWith(`@${domain}`)),
    {
      message: `Use a company email (${domains.map((domain) => `@${domain}`).join(', ')}).`,
      path: ['email'],
    },
  );
}

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, requiredMessage),
});
export type LoginInput = z.infer<typeof loginSchema>;

export const mfaSchema = z.object({
  code: z
    .string()
    .trim()
    .regex(/^\d{6}$/, 'Enter the 6-digit code.'),
});
export type MfaInput = z.infer<typeof mfaSchema>;

export const forgotPasswordSchema = z.object({ email: emailSchema });
export type ForgotPasswordInput = z.infer<typeof forgotPasswordSchema>;

export const resetPasswordSchema = z
  .object({
    token: z.string().min(1, requiredMessage),
    password: passwordSchema,
    confirm: z.string(),
  })
  .refine((value) => value.password === value.confirm, {
    message: 'Passwords do not match.',
    path: ['confirm'],
  });
export type ResetPasswordInput = z.infer<typeof resetPasswordSchema>;

export const verifyEmailSchema = z.object({ token: z.string().min(1, requiredMessage) });

export const createTicketSchema = z.object({
  department_id: z.string().trim().regex(departmentCode, 'Pick a department.'),
  category_id: z.string().min(1).nullable(),
  title: z
    .string()
    .trim()
    .min(1, requiredMessage)
    .max(MAX_TITLE_LENGTH, `Max ${MAX_TITLE_LENGTH} characters.`),
  description: z
    .string()
    .trim()
    .min(1, requiredMessage)
    .max(MAX_DESCRIPTION_LENGTH, `Max ${MAX_DESCRIPTION_LENGTH} characters.`),
  priority: z.enum(['low', 'medium', 'high', 'critical']),
  confidential: z.boolean(),
});
export type CreateTicketInput = z.infer<typeof createTicketSchema>;

export const acknowledgeSchema = z
  .object({
    eta: z.string().optional(),
    no_eta_reason: z.string().trim().optional(),
    next_checkpoint_at: z.string().optional(),
  })
  .superRefine((value, ctx) => {
    if (value.eta) {
      if (!isFuture(value.eta)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: futureMessage, path: ['eta'] });
      }
      return;
    }
    if (!value.no_eta_reason || value.no_eta_reason.length < 5) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Give a reason (at least 5 characters).',
        path: ['no_eta_reason'],
      });
    }
    if (!isFuture(value.next_checkpoint_at)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: futureMessage,
        path: ['next_checkpoint_at'],
      });
    }
  });
export type AcknowledgeInput = z.infer<typeof acknowledgeSchema>;

export const assignSchema = z.object({
  assignee_id: z.string().min(1, 'Pick a person.'),
  reason: optionalReason,
});
export type AssignInput = z.infer<typeof assignSchema>;

export function assignSchemaFor(requireReason: boolean) {
  if (!requireReason) return assignSchema;
  return assignSchema.extend({ reason: reasonSchema.shape.reason });
}

export const transferSchema = z
  .object({
    department_id: z.string().trim().regex(departmentCode, 'Pick a department.'),
    category_id: z.string().optional(),
    reason: reasonSchema.shape.reason,
    current_department_id: z.string().optional(),
  })
  .refine(
    (value) =>
      !value.current_department_id || value.department_id !== value.current_department_id,
    { message: 'Pick a different department.', path: ['department_id'] },
  );
export type TransferInput = z.infer<typeof transferSchema>;

export const changePrioritySchema = z.object({
  priority: z.enum(['low', 'medium', 'high', 'critical']),
  reason: reasonSchema.shape.reason,
});
export type ChangePriorityInput = z.infer<typeof changePrioritySchema>;

export const reviseEtaSchema = z
  .object({
    eta: z.string().min(1, requiredMessage),
    reason: reasonSchema.shape.reason,
    current_eta: z.string().optional(),
  })
  .refine((value) => isFuture(value.eta), { message: futureMessage, path: ['eta'] })
  .refine((value) => !value.current_eta || new Date(value.eta).getTime() !== new Date(value.current_eta).getTime(), {
    message: 'Pick a different ETA.',
    path: ['eta'],
  });
export type ReviseEtaInput = z.infer<typeof reviseEtaSchema>;

export const askRequesterSchema = z.object({
  message: z.string().trim().min(5, 'Use at least 5 characters.').max(1000, 'Too long.'),
});
export type AskRequesterInput = z.infer<typeof askRequesterSchema>;

export const holdSchema = z
  .object({
    reason: reasonSchema.shape.reason,
    review_date: z.string().min(1, requiredMessage),
  })
  .refine((value) => isFuture(value.review_date), {
    message: futureMessage,
    path: ['review_date'],
  });
export type HoldInput = z.infer<typeof holdSchema>;

export const resolveSchema = z.object({
  summary: z.string().trim().min(10, 'Add at least 10 characters.').max(2000, 'Too long.'),
});
export type ResolveInput = z.infer<typeof resolveSchema>;

export const reopenSchema = z.object({ reason: reasonSchema.shape.reason });
export type ReopenInput = z.infer<typeof reopenSchema>;

export const cancelSchema = reopenSchema;
export type CancelInput = z.infer<typeof cancelSchema>;

export const closeSchema = reopenSchema;
export type CloseInput = z.infer<typeof closeSchema>;

export const confirmClosureSchema = z.object({
  rating: z.preprocess(
    (value) => (value === '' || value === undefined ? undefined : value),
    z.coerce.number().int().min(1).max(5).optional(),
  ),
  comment: z.string().trim().max(1000, 'Too long.').optional(),
});
export type ConfirmClosureInput = z.infer<typeof confirmClosureSchema>;

export const commentSchema = z.object({
  body: z.string().trim().min(1, 'Write a message first.').max(5000, 'Too long.'),
  internal: z.boolean(),
});
export type CommentInput = z.infer<typeof commentSchema>;

export const approveSignupSchema = z.object({
  approved_role: z.enum(['employee', 'admin', 'super_admin']),
  approved_department: z.string().trim().regex(departmentCode, 'Confirm a department.'),
});
export type ApproveSignupInput = z.infer<typeof approveSignupSchema>;

export const rejectSignupSchema = z.object({ reason: reasonSchema.shape.reason });
export type RejectSignupInput = z.infer<typeof rejectSignupSchema>;

export const departmentCreateSchema = z.object({
  id: z.string().trim().regex(departmentCode, 'Use 2 to 6 uppercase letters.'),
  name: z.string().trim().min(2, 'Enter a name.').max(80, 'Use at most 80 characters.'),
});
export type DepartmentCreateInput = z.infer<typeof departmentCreateSchema>;

export const departmentFormSchema = z.object({
  id: z.preprocess(
    (value) => (value === '' || value === undefined ? undefined : value),
    z.string().trim().regex(departmentCode, 'Use 2 to 6 uppercase letters.').optional(),
  ),
  name: z.string().trim().min(2, 'Enter a name.').max(80, 'Use at most 80 characters.'),
  active: z.boolean(),
});
export type DepartmentFormInput = z.infer<typeof departmentFormSchema>;

export const categoryFormSchema = z.object({
  name: z.string().trim().min(2, 'Enter a name.').max(80, 'Use at most 80 characters.'),
  confidential: z.boolean(),
});
export type CategoryFormInput = z.infer<typeof categoryFormSchema>;

const hours = z.coerce.number().min(1, 'At least 1 hour.').max(168, 'At most 168 hours.');
const priorityHours = z.object({
  low: hours,
  medium: hours,
  high: hours,
  critical: hours,
});

export const policyFormSchema = z
  .object({
    initial_response_hours: hours,
    warning_hours: priorityHours,
    l3_hours: priorityHours,
    update_warning_hours: hours,
    update_cadence_hours: hours,
    eta_warning_hours: z.coerce.number().min(1).max(48),
    escalation_repeat_hours: hours,
    requester_reminder_hours: hours,
    auto_close_business_days: z.preprocess(
      (value) => (value === '' || value === undefined ? null : value),
      z.coerce.number().min(1).max(30).nullable(),
    ),
    reopen_window_days: z.coerce.number().min(1).max(90),
    max_reopens: z.coerce.number().min(0).max(10),
    sla_mode: z.enum(['calendar', 'business']),
    admins_can_manage_departments: z.boolean(),
  })
  .superRefine((value, ctx) => {
    const priorities = ['low', 'medium', 'high', 'critical'] as const;
    for (const priority of priorities) {
      if (value.warning_hours[priority] >= value.initial_response_hours) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Must be below the initial response hours.',
          path: ['warning_hours', priority],
        });
      }
      if (value.l3_hours[priority] <= value.initial_response_hours) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Must be above the initial response hours.',
          path: ['l3_hours', priority],
        });
      }
    }
    if (value.update_warning_hours >= value.update_cadence_hours) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Must be below the update cadence.',
        path: ['update_warning_hours'],
      });
    }
    if (value.sla_mode !== 'calendar') {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Available in a later release.',
        path: ['sla_mode'],
      });
    }
  });
export type PolicyFormInput = z.infer<typeof policyFormSchema>;

export function passwordStrength(value: string): { score: 0 | 1 | 2 | 3 | 4; label: string } {
  let score = 0;
  if (value.length >= 8) score += 1;
  if (value.length >= MIN_PASSWORD_LENGTH) score += 1;
  if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score += 1;
  if (/\d/.test(value) && /[^A-Za-z0-9]/.test(value)) score += 1;
  const labels = ['Too short', 'Weak', 'Fair', 'Good', 'Strong'];
  const capped = Math.min(4, score) as 0 | 1 | 2 | 3 | 4;
  return { score: capped, label: value.length === 0 ? '' : labels[capped]! };
}
