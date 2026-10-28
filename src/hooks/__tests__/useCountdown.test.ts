import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useCountdown } from '../useCountdown';

describe('useCountdown (spec 11.3 — ticks every 30s)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-27T12:00:00.000Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('counts down to the server deadline', () => {
    const dueAt = '2026-10-27T17:00:00.000Z';
    const { result } = renderHook(() => useCountdown(dueAt));
    expect(result.current.expired).toBe(false);
    expect(result.current.remainingMs).toBe(5 * 3600_000);
    expect(result.current.dueAt).toBe(dueAt);
  });

  it('fires onExpired exactly once when the deadline passes', () => {
    const onExpired = vi.fn();
    const dueAt = '2026-10-27T12:00:10.000Z';
    renderHook(() => useCountdown(dueAt, onExpired));

    act(() => {
      vi.advanceTimersByTime(30_000);
    });

    expect(onExpired).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(onExpired).toHaveBeenCalledTimes(1);
  });

  it('handles a missing deadline', () => {
    const { result } = renderHook(() => useCountdown(null));
    expect(result.current.expired).toBe(false);
    expect(result.current.remainingMs).toBe(Number.POSITIVE_INFINITY);
  });

  it('re-evaluates when the deadline changes (new ETA)', () => {
    const { result, rerender } = renderHook(({ due }) => useCountdown(due, undefined, 0), {
      initialProps: { due: '2026-10-27T13:00:00.000Z' },
    });
    expect(result.current.remainingMs).toBe(3600_000);

    rerender({ due: '2026-10-27T15:00:00.000Z' });
    expect(result.current.remainingMs).toBe(3 * 3600_000);
  });
});
