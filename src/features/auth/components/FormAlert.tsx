import { AlertTriangle } from 'lucide-react';

/**
 * Form-level error banner. Uses role="alert" (spec 3.6) and the crit tokens
 * only — colour is never the only signal (the icon and text carry it too).
 */
export function FormAlert({ message }: { message?: string | null }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="border-crit/40 flex items-start gap-2 rounded border bg-crit-soft px-3 py-2"
    >
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-crit" aria-hidden="true" />
      <p className="text-small text-crit">{message}</p>
    </div>
  );
}
