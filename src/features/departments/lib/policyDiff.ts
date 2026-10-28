import { PRIORITY_ORDER } from '@/lib/constants';
import type { PolicyConfig } from '@/types/domain';

function fmt(value: number | string | null): string {
  return value === null ? 'Off' : String(value);
}

/**
 * Human-readable diff lines for the save confirmation (spec 9.13):
 * "initial_response_hours: 24 → 18". Values always come from the API —
 * never hardcoded (spec 11.2).
 */
export function buildPolicyDiff(current: PolicyConfig, next: PolicyConfig): string[] {
  const lines: string[] = [];
  const push = (key: string, a: number | string | null, b: number | string | null) => {
    if (a !== b) lines.push(`${key}: ${fmt(a)} → ${fmt(b)}`);
  };

  push('initial_response_hours', current.initial_response_hours, next.initial_response_hours);
  push('update_cadence_hours', current.update_cadence_hours, next.update_cadence_hours);
  push('requester_reminder_hours', current.requester_reminder_hours, next.requester_reminder_hours);
  push('auto_close_business_days', current.auto_close_business_days, next.auto_close_business_days);
  push('sla_mode', current.sla_mode, next.sla_mode);

  for (const priority of PRIORITY_ORDER) {
    push(
      `warning_hours.${priority}`,
      current.warning_hours[priority],
      next.warning_hours[priority],
    );
    push(`l3_hours.${priority}`, current.l3_hours[priority], next.l3_hours[priority]);
  }
  return lines;
}
