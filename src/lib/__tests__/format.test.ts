import { describe, expect, it } from 'vitest';
import {
  formatBytes,
  formatDuration,
  formatOverdue,
  formatRemaining,
  initials,
  isoToLocalInput,
  localInputToIso,
} from '../format';

describe('formatDuration (spec 11.3)', () => {
  it('formats sub-hour durations as minutes', () => {
    expect(formatDuration(45 * 60_000)).toBe('45m');
    expect(formatDuration(0)).toBe('0m');
  });

  it('formats under 48 hours as Xh Ym', () => {
    expect(formatDuration(5 * 3600_000 + 12 * 60_000)).toBe('5h 12m');
    expect(formatDuration(2 * 3600_000)).toBe('2h');
    expect(formatDuration(47 * 3600_000 + 59 * 60_000)).toBe('47h 59m');
  });

  it('formats 48 hours and over as Xd Yh', () => {
    expect(formatDuration(48 * 3600_000)).toBe('2d');
    expect(formatDuration(52 * 3600_000)).toBe('2d 4h');
    expect(formatDuration(24 * 3600_000 * 3 + 3600_000)).toBe('3d 1h');
  });

  it('never returns negative durations', () => {
    expect(formatDuration(-60_000)).toBe('0m');
  });
});

describe('countdown helpers', () => {
  const now = Date.parse('2026-10-27T12:00:00.000Z');

  it('formats remaining time until a deadline', () => {
    expect(formatRemaining('2026-10-27T17:12:00.000Z', now)).toBe('5h 12m');
  });

  it('formats overdue time past a deadline', () => {
    expect(formatOverdue('2026-10-27T09:50:00.000Z', now)).toBe('2h 10m');
  });
});

describe('initials', () => {
  it('uses first and last name letters', () => {
    expect(initials('Rohan Mehta')).toBe('RM');
    expect(initials('Asha')).toBe('AS');
    expect(initials('  ')).toBe('?');
  });
});

describe('datetime-local conversion', () => {
  it('round-trips an ISO string through a datetime-local value', () => {
    const iso = '2026-10-27T17:30:00.000Z';
    const value = isoToLocalInput(iso);
    expect(value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
    expect(localInputToIso(value)).toBe(new Date(value).toISOString());
  });

  it('returns null for empty input', () => {
    expect(localInputToIso('')).toBeNull();
    expect(isoToLocalInput(null)).toBe('');
  });
});

describe('formatBytes', () => {
  it('scales units', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2 KB');
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB');
  });
});
