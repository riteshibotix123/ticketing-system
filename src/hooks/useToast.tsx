import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';
import { cn } from '@/lib/cn';

export type ToastVariant = 'success' | 'error' | 'info';

export interface ToastItem {
  id: number;
  title: string;
  description?: string;
  variant: ToastVariant;
  /** Errors stay until closed; others auto-dismiss after 4s (spec 9.2/13). */
  persistent: boolean;
}

/**
 * `toast({ title })` plus the idiomatic `toast.success('…')` /
 * `toast.error('…')` shorthands — both call styles are supported.
 */
export interface ToastCallable {
  (input: { title: string; description?: string; variant?: ToastVariant }): number;
  success: (title: string, description?: string) => number;
  error: (title: string, description?: string) => number;
}

interface ToastContextValue {
  toast: ToastCallable;
  success: (title: string, description?: string) => number;
  error: (title: string, description?: string) => number;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let nextId = 1;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef<Record<number, ReturnType<typeof setTimeout>>>({});

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current[id];
    if (timer) {
      clearTimeout(timer);
      delete timers.current[id];
    }
  }, []);

  const value = useMemo<ToastContextValue>(() => {
    const fire = (
      title: string,
      description: string | undefined,
      variant: ToastVariant,
    ): number => {
      const id = nextId++;
      const item: ToastItem = { id, title, description, variant, persistent: variant === 'error' };
      setItems((prev) => [...prev.slice(-3), item]);
      if (!item.persistent) {
        timers.current[id] = setTimeout(() => dismiss(id), 4000);
      }
      return id;
    };

    const fn = ((input: { title: string; description?: string; variant?: ToastVariant }) =>
      fire(input.title, input.description, input.variant ?? 'info')) as ToastCallable;
    fn.success = (title, description) => fire(title, description, 'success');
    fn.error = (title, description) => fire(title, description, 'error');

    return {
      toast: fn,
      success: (title, description) => fire(title, description, 'success'),
      error: (title, description) => fire(title, description, 'error'),
      dismiss,
    };
  }, [dismiss]);

  useEffect(() => {
    const active = timers.current;
    return () => {
      Object.values(active).forEach(clearTimeout);
    };
  }, []);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="safe-pb fixed bottom-4 right-4 z-[60] flex w-[min(380px,calc(100vw-32px))] flex-col gap-2"
        role="status"
        aria-live="polite"
        aria-label="Notifications"
      >
        {items.map((item) => (
          <ToastCard key={item.id} item={item} onClose={() => dismiss(item.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastCard({ item, onClose }: { item: ToastItem; onClose: () => void }) {
  const Icon =
    item.variant === 'success' ? CheckCircle2 : item.variant === 'error' ? AlertTriangle : Info;
  const tone =
    item.variant === 'success' ? 'text-ok' : item.variant === 'error' ? 'text-crit' : 'text-info';
  return (
    <div
      className={cn(
        'animate-fade-in rounded-md border bg-surface p-3 shadow-pop',
        item.variant === 'error' ? 'border-crit/50' : 'border-line',
      )}
    >
      <div className="flex items-start gap-2">
        <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', tone)} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="text-body font-medium text-fg">{item.title}</p>
          {item.description ? (
            <p className="mt-0.5 text-small text-muted">{item.description}</p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-muted hover:bg-surface-2 hover:text-fg"
          aria-label="Dismiss notification"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>');
  return ctx;
}
