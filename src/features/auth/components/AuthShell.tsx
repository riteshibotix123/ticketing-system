import type { ReactNode } from 'react';
import { Ticket } from 'lucide-react';
import { APP_NAME } from '@/lib/constants';

interface AuthShellProps {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}

/**
 * Centered branded card layout (max 420px) used by every auth screen,
 * including the account-state pages that live outside the app shell
 * (spec 7/8: status pages never render the shell).
 */
export function AuthShell({ title, subtitle, children, footer }: AuthShellProps) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-bg px-4 py-10">
      <div className="w-full max-w-[420px]">
        <div className="mb-6 flex flex-col items-center gap-1.5 text-center">
          <span
            className="flex h-10 w-10 items-center justify-center rounded-md bg-accent text-accent-fg"
            aria-hidden="true"
          >
            <Ticket className="h-5 w-5" />
          </span>
          <p className="text-section-title text-fg">{APP_NAME}</p>
          <p className="label-caps">Internal portal</p>
        </div>
        <div className="card p-6">
          <h1 className="text-page-title text-fg">{title}</h1>
          {subtitle ? <p className="mt-1 text-small text-muted">{subtitle}</p> : null}
          <div className="mt-5">{children}</div>
        </div>
        {footer ? <div className="mt-4 text-center text-small text-muted">{footer}</div> : null}
      </div>
    </div>
  );
}
