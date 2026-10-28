import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AuthShell } from '@/features/auth/components/AuthShell';
import { SignupForm } from '@/features/auth/components/SignupForm';
import { SignupNotice } from '@/features/auth/components/SignupNotice';

/**
 * Signup (spec 9.1 + 1.3): self-signup with company email, department and
 * requested role; after submit the page becomes the verify-email notice with
 * a resend button (60s cooldown).
 */
export default function SignupPage() {
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null);

  if (submittedEmail) {
    return (
      <AuthShell
        title="Verify your email"
        subtitle="Almost done — one step before your request is sent."
      >
        <SignupNotice email={submittedEmail} />
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Request access"
      subtitle="Sign up with your company email. After you verify, an approver reviews your request."
      footer={
        <span>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-accent underline-offset-4 hover:underline">
            Sign in
          </Link>
        </span>
      }
    >
      <SignupForm onSuccess={setSubmittedEmail} />
    </AuthShell>
  );
}
