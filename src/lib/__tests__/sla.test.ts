import { describe, expect, it } from 'vitest';
import { compareUrgency, requesterSlaText, slaDisplay, SLA_LEVEL_META } from '../sla';
import type { SlaState, Ticket } from '@/types/domain';

const base: SlaState = {
  level: 0,
  kind: 'initial_response',
  paused: false,
  stopped: false,
  due_at: '2026-10-27T17:12:00.000Z',
  label: 'Initial response due',
};

const now = Date.parse('2026-10-27T12:00:00.000Z');

describe('slaDisplay (spec 11.3 — display only, never compute levels)', () => {
  it('shows the level labels and icons from the spec table', () => {
    expect(SLA_LEVEL_META[0]).toMatchObject({ label: 'On track', icon: '●' });
    expect(SLA_LEVEL_META[1]).toMatchObject({ label: 'Warning', icon: '▲' });
    expect(SLA_LEVEL_META[2]).toMatchObject({ label: 'Breached', icon: '■' });
    expect(SLA_LEVEL_META[3]).toMatchObject({ label: 'Escalated L3', icon: '■' });
  });

  it('formats the initial-response countdown', () => {
    expect(slaDisplay(base, now)).toMatchObject({
      text: 'Response due in 5h 12m',
      tone: 'ok',
      overdue: false,
    });
  });

  it('formats an overdue response', () => {
    const overdue = slaDisplay({ ...base, due_at: '2026-10-27T09:50:00.000Z' }, now);
    expect(overdue.text).toBe('Response overdue 2h 10m');
    expect(overdue.overdue).toBe(true);
  });

  it('uses the right wording per SLA kind', () => {
    expect(slaDisplay({ ...base, kind: 'progress_update' }, now).text).toBe(
      'Next update in 5h 12m',
    );
    expect(slaDisplay({ ...base, kind: 'eta', due_at: '2026-10-27T09:00:00.000Z' }, now).text).toBe(
      'ETA overdue 3h',
    );
  });

  it('renders paused and stopped states as neutral', () => {
    const paused = slaDisplay({ ...base, paused: true, label: 'Timer paused' }, now);
    expect(paused).toMatchObject({ icon: '◷', tone: 'muted', text: '' });

    const stopped = slaDisplay({ ...base, stopped: true, label: 'Closed' }, now);
    expect(stopped).toMatchObject({ icon: '◷', tone: 'muted', stopped: true });
  });

  it('keeps the escalation level from the server', () => {
    expect(slaDisplay({ ...base, level: 3, label: 'Escalated L3' }, now).label).toBe(
      'Escalated L3',
    );
    expect(slaDisplay({ ...base, level: 3 }, now).tone).toBe('crit');
  });
});

describe('requester view never leaks levels (spec 11.3)', () => {
  it('shows only first-response / progress wording', () => {
    expect(requesterSlaText({ status: 'new', acknowledged_at: null, eta: null })).toBe(
      'Awaiting first response',
    );
    expect(
      requesterSlaText({
        status: 'in_progress',
        acknowledged_at: '2026-10-27T10:00:00.000Z',
        eta: null,
      }),
    ).toBe('In progress');
  });

  it('includes the ETA when present', () => {
    const text = requesterSlaText({
      status: 'assigned',
      acknowledged_at: '2026-10-27T10:00:00.000Z',
      eta: '2026-10-28T10:00:00.000Z',
    });
    expect(text).toContain('ETA');
    expect(text).not.toMatch(/L[0-3]|breach/i);
  });
});

describe('urgency sort (spec 11.4)', () => {
  const ticket = (over: Partial<Ticket>): Ticket =>
    ({
      id: 'IBX-ITX-2026-000001',
      sla: {
        level: 0,
        kind: 'initial_response',
        paused: false,
        stopped: false,
        due_at: null,
        label: '',
      },
      priority: 'medium',
      sla_started_at: '2026-10-27T08:00:00.000Z',
      ...over,
    }) as Ticket;

  it('sorts by escalation level, then priority, then oldest first', () => {
    const l3 = ticket({ sla: { ...ticket({}).sla, level: 3 }, priority: 'low' });
    const l1critical = ticket({
      sla: { ...ticket({}).sla, level: 1 },
      priority: 'critical',
      sla_started_at: '2026-10-27T09:00:00.000Z',
    });
    const l1medium = ticket({ sla: { ...ticket({}).sla, level: 1 }, priority: 'medium' });

    const sorted = [l1medium, l1critical, l3].sort(compareUrgency);
    expect(sorted.map((t) => t.sla.level)).toEqual([3, 1, 1]);
    expect(sorted[1]!.priority).toBe('critical');
  });
});
