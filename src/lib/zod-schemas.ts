import { z } from 'zod';
import { MAX_DESCRIPTION_LENGTH, MAX_TITLE_LENGTH, MIN_PASSWORD_LENGTH } from './constants';

/**
 * Client-side validation mirroring the business rules in spec section 10.
 * The server is authoritative; the client prevents obvious mistakes.
 */

const requiredMessage = 'Required.';

export const passwordSchema = z
  .string()
  .min(MIN_PASSWORD_LENGTH, `Use at least ${MIN_PASSWORD_LENGTH} characters.`);

export const emailSchema = z
  .string()
  .trim()
  .min(1, requiredMessage)
  .email('Enter a valid email address.');

export const signupSchema = z.object({
  name: z.string().trim().min(2, 'Enter your full name.').max(120, 'Too long.'),
  email: emailSchema,
  password: passwordSchema,
  requested_role: z.enum(['employee', 'admin', 'super_admin']),
  requested_department: z.string().min(1, 'Pick a department.'),
});
export type SignupInput = z.infer<typeof signupSchema>;

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
  .refine((v) => v.password === v.confirm, {
    message: 'Passwords do not match.',
    path: ['confirm'],
  });
export type ResetPasswordInput = z.infer<typeof resetPasswordSchema>;

export const verifyEmailSchema = z.object({ token: z.string().min(1, requiredMessage) });

export const createTicketSchema = z.object({
  department_id: z.string().min(1, 'Pick a department.'),
  category_id: z.string().min(1, 'Pick a category.'),
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

/** Acknowledge: ETA OR "no ETA yet" reason + next checkpoint (rule 4). */
export const acknowledgeSchema = z
  .object({
    use_eta: z.boolean(),
    eta: z.string().optional(),
    no_eta_reason: z.string().optional(),
    checkpoint: z.string().optional(),
  })
  .refine((v) => (v.use_eta ? Boolean(v.eta) : Boolean(v.no_eta_reason && v.checkpoint)), {
    message: 'Provide an ETA, or a reason and the next checkpoint.',
    path: ['eta'],
  })
  .refine((v) => !v.use_eta || !v.eta || new Date(v.eta).getTime() > Date.now(), {
    message: 'ETA must be in the future.',
    path: ['eta'],
  });
export type AcknowledgeInput = z.infer<typeof acknowledgeSchema>;

export const assignSchema = z.object({
  assignee_id: z.string().min(1, 'Pick a person.'),
  reason: z.string().trim().max(500, 'Too long.').optional(),
});
export type AssignInput = z.infer<typeof assignSchema>;

export const transferSchema = z.object({
  department_id: z.string().min(1, 'Pick a department.'),
  category_id: z.string().optional(),
  reason: z.string().trim().min(1, requiredMessage).max(500, 'Too long.'),
});
export type TransferInput = z.infer<typeof transferSchema>;

export const changePrioritySchema = z.object({
  priority: z.enum(['low', 'medium', 'high', 'critical']),
  reason: z.string().trim().min(1, requiredMessage).max(500, 'Too long.'),
});
export type ChangePriorityInput = z.infer<typeof changePrioritySchema>;

export const reviseEtaSchema = z.object({
  eta: z.string().min(1, requiredMessage),
  reason: z.string().trim().min(1, requiredMessage).max(500, 'Too long.'),
});
export type ReviseEtaInput = z.infer<typeof reviseEtaSchema>;

export const askRequesterSchema = z.object({
  message: z.string().trim().max(1000, 'Too long.').optional(),
});
export type AskRequesterInput = z.infer<typeof askRequesterSchema>;

export const holdSchema = z.object({
  reason: z.string().trim().min(1, requiredMessage).max(500, 'Too long.'),
  review_date: z.string().min(1, requiredMessage),
});
export type HoldInput = z.infer<typeof holdSchema>;

export const resolveSchema = z.object({
  summary: z.string().trim().min(1, requiredMessage).max(5000, 'Too long.'),
});
export type ResolveInput = z.infer<typeof resolveSchema>;

export const reopenSchema = z.object({
  reason: z.string().trim().min(1, requiredMessage).max(500, 'Too long.'),
});
export type ReopenInput = z.infer<typeof reopenSchema>;

export const cancelSchema = reopenSchema;
export type CancelInput = z.infer<typeof cancelSchema>;

export const commentSchema = z.object({
  body: z.string().trim().min(1, 'Write a message first.').max(5000, 'Too long.'),
  internal: z.boolean(),
});
export type CommentInput = z.infer<typeof commentSchema>;

export const approveSignupSchema = z.object({
  approved_role: z.enum(['employee', 'spoke', 'resolver', 'admin', 'super_admin']),
  approved_department: z.string().min(1, 'Confirm a department.'),
});
export type ApproveSignupInput = z.infer<typeof approveSignupSchema>;

export const rejectSignupSchema = z.object({
  reason: z.string().trim().min(1, requiredMessage).max(500, 'Too long.'),
});
export type RejectSignupInput = z.infer<typeof rejectSignupSchema>;

export const reasonSchema = z.object({
  reason: z.string().trim().min(1, requiredMessage).max(500, 'Too long.'),
});
export type ReasonInput = z.infer<typeof reasonSchema>;

export const departmentFormSchema = z.object({
  name: z.string().trim().min(2, 'Enter a name.').max(80, 'Too long.'),
  active: z.boolean(),
  confidential: z.boolean(),
});
export type DepartmentFormInput = z.infer<typeof departmentFormSchema>;

export const categoryFormSchema = z.object({
  name: z.string().trim().min(2, 'Enter a name.').max(80, 'Too long.'),
});
export type CategoryFormInput = z.infer<typeof categoryFormSchema>;

export const policyFormSchema = z.object({
  initial_response_hours: z.coerce.number().min(1).max(720),
  update_cadence_hours: z.coerce.number().min(1).max(720),
  requester_reminder_hours: z.coerce.number().min(1).max(720),
  auto_close_business_days: z.preprocess(
    (value) => (value === '' || value === undefined ? null : value),
    z.coerce.number().min(1).max(90).nullable(),
  ),
  sla_mode: z.enum(['calendar', 'business']),
  warning_hours: z.object({
    low: z.coerce.number().min(1),
    medium: z.coerce.number().min(1),
    high: z.coerce.number().min(1),
    critical: z.coerce.number().min(1),
  }),
  l3_hours: z.object({
    low: z.coerce.number().min(1),
    medium: z.coerce.number().min(1),
    high: z.coerce.number().min(1),
    critical: z.coerce.number().min(1),
  }),
});
export type PolicyFormInput = z.infer<typeof policyFormSchema>;

/** Password strength 0..4 for the signup meter. */
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
