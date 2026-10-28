import { Lock } from 'lucide-react';

/**
 * Shown when the viewer is an Admin but the Super Admin toggle
 * "Admins can manage departments" is off — the whole page is read-only (spec 1.3/9.13).
 */
export function ReadOnlyBanner() {
  return (
    <div
      role="status"
      className="border-warn/40 mb-4 flex items-start gap-2 rounded border bg-warn-soft px-4 py-3"
    >
      <Lock className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden="true" />
      <p className="text-small text-warn">
        <span className="font-semibold">Read-only.</span> Admins can manage departments is switched
        off. Contact a Super Admin.
      </p>
    </div>
  );
}
