import { Link } from 'react-router-dom';
import { MailCheck } from 'lucide-react';
import { USE_MOCKS } from '@/lib/constants';
import { ResendButton } from './ResendButton';

/** Verify-email notice shown after a successful signup (spec 9.1). */
export function SignupNotice({ email }: { email: string }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="border-accent/40 flex items-start gap-2 rounded border bg-accent-soft px-3 py-2.5">
        <MailCheck className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
        <div>
          <p className="text-body font-medium text-fg">Check your email to verify your address.</p>
          <p className="mt-0.5 text-small text-muted">We sent a verification link to {email}.</p>
        </div>
      </div>
      <ResendButton email={email} />
      {USE_MOCKS ? (
        <p className="text-small text-muted">
          Mock shortcut:{' '}
          <Link
            to="/verify-email?token=mock-verify-token"
            className="font-medium text-accent underline-offset-4 hover:underline"
          >
            open the mock verification link
          </Link>
        </p>
      ) : null}
      <p className="text-small text-muted">
        Already verified?{' '}
        <Link to="/login" className="font-medium text-accent underline-offset-4 hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
