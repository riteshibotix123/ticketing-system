import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export type ThemeChoice = 'system' | 'light' | 'dark';

const STORAGE_KEY = 'ibx-theme';

interface ThemeContextValue {
  theme: ThemeChoice;
  /** Resolved theme actually applied. */
  resolved: 'light' | 'dark';
  setTheme: (theme: ThemeChoice) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStored(): ThemeChoice {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === 'light' || value === 'dark' || value === 'system') return value;
  } catch {
    // localStorage unavailable (private mode) — fall back to system.
  }
  return 'system';
}

function apply(choice: ThemeChoice): 'light' | 'dark' {
  const prefersDark =
    typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const resolved = choice === 'system' ? (prefersDark ? 'dark' : 'light') : choice;
  document.documentElement.setAttribute('data-theme', resolved);
  return resolved;
}

/**
 * Theme choice (System / Light / Dark) persisted in localStorage, wrapped in
 * try/catch (spec 3.2). Index.html applies the stored value before first paint.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeChoice>(() => readStored());
  const [resolved, setResolved] = useState<'light' | 'dark'>(() => apply(readStored()));

  const setTheme = useCallback((choice: ThemeChoice) => {
    setThemeState(choice);
    try {
      localStorage.setItem(STORAGE_KEY, choice);
    } catch {
      // Ignore storage failures; theme still applies for this session.
    }
    setResolved(apply(choice));
  }, []);

  // Follow the OS when the choice is "system".
  useEffect(() => {
    if (theme !== 'system' || typeof window === 'undefined') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => setResolved(apply('system'));
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [theme]);

  const value = useMemo(() => ({ theme, resolved, setTheme }), [theme, resolved, setTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
  return ctx;
}
