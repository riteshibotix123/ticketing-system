import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

export type FilterValues = Record<string, string | string[] | null | undefined>;

/**
 * List filter state synced to the URL query string so refresh and sharing work
 * (spec 8).
 */
export function useUrlFilters() {
  const [searchParams, setSearchParams] = useSearchParams();

  const get = useCallback((key: string): string => searchParams.get(key) ?? '', [searchParams]);

  const getAll = useCallback((key: string): string[] => searchParams.getAll(key), [searchParams]);

  const set = useCallback(
    (updates: FilterValues, options?: { replace?: boolean }) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const [key, value] of Object.entries(updates)) {
            next.delete(key);
            if (value === null || value === undefined || value === '') continue;
            if (Array.isArray(value)) value.filter(Boolean).forEach((v) => next.append(key, v));
            else next.set(key, value);
          }
          // Any filter change resets pagination unless page itself was passed.
          if (!('page' in updates)) next.delete('page');
          return next;
        },
        { replace: options?.replace ?? true },
      );
    },
    [setSearchParams],
  );

  const clear = useCallback(
    (keep: string[] = []) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams();
          keep.forEach((key) => {
            const v = prev.get(key);
            if (v) next.set(key, v);
          });
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const page = useMemo(() => {
    const p = Number(searchParams.get('page') ?? '1');
    return Number.isFinite(p) && p >= 1 ? p : 1;
  }, [searchParams]);

  const activeCount = useMemo(() => {
    let count = 0;
    searchParams.forEach((_v, key) => {
      if (key !== 'page' && key !== 'tab' && key !== 'sort') count += 1;
    });
    return count;
  }, [searchParams]);

  return { searchParams, get, getAll, set, clear, page, activeCount };
}
