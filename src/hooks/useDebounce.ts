import { useEffect, useState } from 'react';

/** Debounced value (search inputs: 300ms per spec 9.4). */
export function useDebounce<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);

  return debounced;
}

/** Online/offline banner state (spec 13). */
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(() =>
    typeof navigator === 'undefined' ? true : navigator.onLine,
  );

  useEffect(() => {
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, []);

  return online;
}

/** Poll every 60s while the tab is visible (spec 9.3/9.10). */
export function useVisiblePoll(intervalMs: number, enabled = true): number | false {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!enabled || intervalMs <= 0) return;
    const id = setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
      setTick((t) => t + 1);
    }, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, enabled]);

  return enabled ? tick : false;
}
