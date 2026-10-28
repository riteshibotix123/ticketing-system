import { cn } from '@/lib/cn';
import { passwordStrength } from '@/lib/zod-schemas';

const BAR_TONE: Record<number, string> = { 1: 'bg-crit', 2: 'bg-warn', 3: 'bg-accent', 4: 'bg-ok' };
const TEXT_TONE: Record<number, string> = {
  1: 'text-crit',
  2: 'text-warn',
  3: 'text-accent',
  4: 'text-ok',
};

/**
 * 4-bar strength meter with a text label from passwordStrength()
 * (spec 9.1). The label is the non-colour signal (spec 3.1).
 */
export function PasswordStrengthMeter({ value }: { value: string }) {
  const { score, label } = passwordStrength(value);

  return (
    <div aria-live="polite" className="mt-1.5">
      <div className="flex gap-1" aria-hidden="true">
        {[1, 2, 3, 4].map((bar) => (
          <div
            key={bar}
            className={cn(
              'h-1 flex-1 rounded-full',
              bar <= score ? BAR_TONE[score] : 'bg-surface-2',
            )}
          />
        ))}
      </div>
      {label ? (
        <p className={cn('mt-1 text-small', TEXT_TONE[score] ?? 'text-muted')}>
          Password strength: {label}
        </p>
      ) : (
        <p className="mt-1 text-small text-muted">Use at least 12 characters.</p>
      )}
    </div>
  );
}
