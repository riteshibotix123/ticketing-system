import { describe, expect, it } from 'vitest';
import {
  acknowledgeSchema,
  approveSignupSchema,
  cancelSchema,
  changePrioritySchema,
  commentSchema,
  createTicketSchema,
  holdSchema,
  passwordStrength,
  policyFormSchema,
  reopenSchema,
  resolveSchema,
  reviseEtaSchema,
  signupSchema,
  transferSchema,
} from '../zod-schemas';

describe('rule 1: ticket fields', () => {
  const valid = {
    department_id: 'IT',
    category_id: 'c1',
    title: 'Laptop broken',
    description: 'It does not boot.',
    priority: 'medium',
    confidential: false,
  };

  it('accepts a complete ticket', () => {
    expect(createTicketSchema.safeParse(valid).success).toBe(true);
  });

  it('requires department, category, title and description', () => {
    expect(createTicketSchema.safeParse({ ...valid, department_id: '' }).success).toBe(false);
    expect(createTicketSchema.safeParse({ ...valid, category_id: '' }).success).toBe(false);
    expect(createTicketSchema.safeParse({ ...valid, title: ' ' }).success).toBe(false);
    expect(createTicketSchema.safeParse({ ...valid, description: '' }).success).toBe(false);
  });

  it('limits title to 120 and description to 5000 characters', () => {
    expect(createTicketSchema.safeParse({ ...valid, title: 'x'.repeat(121) }).success).toBe(false);
    expect(createTicketSchema.safeParse({ ...valid, description: 'x'.repeat(5001) }).success).toBe(
      false,
    );
    expect(createTicketSchema.safeParse({ ...valid, title: 'x'.repeat(120) }).success).toBe(true);
  });
});

describe('rule 4: acknowledgement needs an ETA or a reason + checkpoint', () => {
  const future = new Date(Date.now() + 3600_000).toISOString();

  it('accepts an ETA', () => {
    expect(acknowledgeSchema.safeParse({ eta: future }).success).toBe(true);
  });

  it('rejects an ETA in the past', () => {
    const past = new Date(Date.now() - 3600_000).toISOString();
    const result = acknowledgeSchema.safeParse({ eta: past });
    expect(result.success).toBe(false);
    if (!result.success) expect(result.error.issues[0]?.message).toMatch(/future/i);
  });

  it('accepts a reason + checkpoint without an ETA', () => {
    expect(
      acknowledgeSchema.safeParse({
        no_eta_reason: 'Waiting for the vendor',
        next_checkpoint_at: future,
      }).success,
    ).toBe(true);
  });

  it('rejects neither being provided', () => {
    expect(acknowledgeSchema.safeParse({}).success).toBe(false);
  });
});

describe('rules 5–10: required reasons and summaries', () => {
  it('5 — resolving needs a summary', () => {
    expect(resolveSchema.safeParse({ summary: 'Replaced the battery.' }).success).toBe(true);
    expect(resolveSchema.safeParse({ summary: '   ' }).success).toBe(false);
  });

  it('6 — hold needs a reason and a review date', () => {
    expect(
      holdSchema.safeParse({ reason: 'Awaiting parts', review_date: '2026-11-01' }).success,
    ).toBe(true);
    expect(holdSchema.safeParse({ reason: '', review_date: '2026-11-01' }).success).toBe(false);
    expect(holdSchema.safeParse({ reason: 'Awaiting parts', review_date: '' }).success).toBe(false);
  });

  it('7 — every ETA change needs a reason', () => {
    const eta = new Date(Date.now() + 7200_000).toISOString();
    expect(reviseEtaSchema.safeParse({ eta, reason: 'Vendor delay' }).success).toBe(true);
    expect(reviseEtaSchema.safeParse({ eta, reason: '' }).success).toBe(false);
    expect(reviseEtaSchema.safeParse({ eta: '', reason: 'x' }).success).toBe(false);
  });

  it('8 — transfers need a reason', () => {
    expect(
      transferSchema.safeParse({ department_id: 'HR', reason: 'Wrong queue', category_id: '' })
        .success,
    ).toBe(true);
    expect(transferSchema.safeParse({ department_id: 'HR', reason: '' }).success).toBe(false);
    expect(transferSchema.safeParse({ department_id: '', reason: 'x' }).success).toBe(false);
  });

  it('9 — priority changes need a reason', () => {
    expect(
      changePrioritySchema.safeParse({ priority: 'high', reason: 'Blocked team' }).success,
    ).toBe(true);
    expect(changePrioritySchema.safeParse({ priority: 'high', reason: '' }).success).toBe(false);
  });

  it('10 — cancelling and reopening need a reason', () => {
    expect(reopenSchema.safeParse({ reason: 'Still broken' }).success).toBe(true);
    expect(reopenSchema.safeParse({ reason: '' }).success).toBe(false);
    expect(cancelSchema.safeParse({ reason: 'Duplicate' }).success).toBe(true);
    expect(cancelSchema.safeParse({ reason: '' }).success).toBe(false);
  });

  it('12 — approval requires a role and department', () => {
    expect(
      approveSignupSchema.safeParse({ approved_role: 'employee', approved_department: 'IT' })
        .success,
    ).toBe(true);
    expect(
      approveSignupSchema.safeParse({ approved_role: 'admin', approved_department: '' }).success,
    ).toBe(false);
    expect(
      approveSignupSchema.safeParse({ approved_role: 'boss', approved_department: 'IT' } as never)
        .success,
    ).toBe(false);
    expect(
      approveSignupSchema.safeParse({ approved_role: 'spoke', approved_department: 'IT' } as never)
        .success,
    ).toBe(false);
  });
});

describe('rule 15: password and signup validation', () => {
  it('requires at least 12 characters', () => {
    const base = {
      name: 'Asha Verma',
      email: 'asha.verma@ibotix.ai',
      requested_role: 'employee',
      requested_department: 'ENG',
    };
    expect(signupSchema.safeParse({ ...base, password: 'short' }).success).toBe(false);
    expect(signupSchema.safeParse({ ...base, password: 'IbotixDemo@2026' }).success).toBe(true);
    expect(signupSchema.safeParse({ ...base, email: 'not-an-email' }).success).toBe(false);
    expect(signupSchema.safeParse({ ...base, requested_role: 'spoke' }).success).toBe(false);
  });

  it('scores password strength', () => {
    expect(passwordStrength('abcd').score).toBeLessThan(2);
    expect(passwordStrength('IbotixDemo@2026').score).toBe(4);
    expect(passwordStrength('').label).toBe('');
  });
});

describe('comment validation (rule 11 shape)', () => {
  it('requires a message', () => {
    expect(commentSchema.safeParse({ body: '', internal: false }).success).toBe(false);
    expect(commentSchema.safeParse({ body: 'Thanks', internal: true }).success).toBe(true);
  });
});

describe('policy form', () => {
  it('accepts numeric hours coerced from strings', () => {
    const result = policyFormSchema.safeParse({
      initial_response_hours: '24',
      update_warning_hours: '20',
      update_cadence_hours: '24',
      eta_warning_hours: '2',
      escalation_repeat_hours: '24',
      requester_reminder_hours: '48',
      auto_close_business_days: '',
      reopen_window_days: '7',
      max_reopens: '3',
      sla_mode: 'calendar',
      admins_can_manage_departments: true,
      warning_hours: { low: 18, medium: 18, high: 18, critical: 12 },
      l3_hours: { low: 48, medium: 48, high: 36, critical: 30 },
    });
    expect(result.success).toBe(true);
  });
});
