import type { ReactNode } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { BrandMark } from '@/components/common/BrandMark';

interface AuthShellProps {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}

const HIGHLIGHTS = [
  'Raise and track requests for every department',
  'SLA timers and escalations keep work moving',
  'Confidential tickets stay with the right people',
];

/**
 * Branded split layout used by every auth screen, including the account-state
 * pages that live outside the app shell (spec 7/8: status pages never render the
 * shell). Brand panel on the left from 1024px; a compact gradient band above the
 * form on smaller screens. The form card stays max 420px.
 */
export function AuthShell({ title, subtitle, children, footer }: AuthShellProps) {
  return (
    <div className="flex min-h-dvh flex-col bg-bg lg:flex-row">
      <aside
        className="brand-gradient relative flex shrink-0 flex-col justify-between overflow-hidden px-6 py-6 text-ink-fg lg:w-[46%] lg:px-12 lg:py-10"
        aria-label="About the Ibotix ticketing portal"
      >
        <BrandMark tone="ink" />
        <div className="hidden max-w-[480px] lg:my-auto lg:block">
          <p className="mb-4 text-label-caps uppercase text-ink-fg">Internal helpdesk</p>
          <p className="text-hero text-ink-fg">Support that moves as fast as your team.</p>
          <p className="mt-4 text-[15px] leading-relaxed text-ink-fg">
            One place to raise, assign and resolve internal requests, with clear ownership and
            response times at every step.
          </p>
          <ul className="mt-8 space-y-3">
            {HIGHLIGHTS.map((item) => (
              <li key={item} className="flex items-start gap-2.5 text-body text-ink-fg">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </aside>

      <div className="flex flex-1 flex-col items-center justify-center px-4 py-10">
        <div className="w-full max-w-[420px]">
          <div className="card p-6 sm:p-8">
            <h1 className="text-page-title text-fg">{title}</h1>
            {subtitle ? <p className="mt-1 text-small text-muted">{subtitle}</p> : null}
            <div className="mt-6">{children}</div>
          </div>
          {footer ? <div className="mt-4 text-center text-small text-muted">{footer}</div> : null}
        </div>
      </div>
    </div>
  );
}
