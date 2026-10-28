import { useEffect, useRef, useState } from 'react';

export interface CountdownState {
  /** Server deadline, ISO UTC. */
  dueAt: string | null;
  /** Current tick time (ms since epoch). */
  now: number;
  /** Milliseconds remaining (negative when overdue). */
  remainingMs: number;
  /** True once the deadline has passed. */
  expired: boolean;
}

/**
 * Ticks every 30s from `sla.due_at` (spec 11.3). The client never computes SLA
 * levels — it only counts down to the server deadline. `onExpired` fires once
 * per crossing so callers can refetch the ticket.
 *
 * Because the tick is 30s, `now` updates on the half-minute; tests can pass an
 * explicit interval of 0 to disable ticking.
 */
export function useCountdown(
  dueAt: string | null | undefined,
  onExpired?: () => void,
  intervalMs = 30_000,
): CountdownState {
  const [now, setNow] = useState(() => Date.now());
  const expired = Boolean(dueAt) && new Date(dueAt as string).getTime() <= now;
  const wasExpired = useRef(false);
  const onExpiredRef = useRef(onExpired);
  onExpiredRef.current = onExpired;

  useEffect(() => {
    if (!dueAt || intervalMs <= 0) return;
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [dueAt, intervalMs]);

  // Recompute `now` when the deadline itself changes (new ETA, refetch).
  useEffect(() => {
    setNow(Date.now());
  }, [dueAt]);

  useEffect(() => {
    if (expired && !wasExpired.current) {
      wasExpired.current = true;
      onExpiredRef.current?.();
    }
    if (!expired) wasExpired.current = false;
  }, [expired]);

  return {
    dueAt: dueAt ?? null,
    now,
    remainingMs: dueAt ? new Date(dueAt).getTime() - now : Number.POSITIVE_INFINITY,
    expired,
  };
}
