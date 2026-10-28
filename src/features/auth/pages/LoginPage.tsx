import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AuthShell } from '@/features/auth/components/AuthShell';
import { LoginForm } from '@/features/auth/components/LoginForm';
import { MfaForm } from '@/features/auth/components/MfaForm';

/**
 * Login (spec 7/9.1): email + password, then an optional MFA step. Success
 * never navigates here — the PublicOnly guard redirects once `me` appears
 * (?next= stays intact because the URL is never touched) and sends
 * non-active accounts to /status/:state.
 */
export default function LoginPage() {
  const [lastEmail, setLastEmail] = useState('');
  const [mfa, setMfa] = useState<{ mfaToken: string; email: string } | null>(null);

  if (mfa) {
    return (
      <AuthShell
        title="Two-factor authentication"
        subtitle="For extra security, enter the code we sent you."
      >
        <MfaForm
          email={mfa.email}
          mfaToken={mfa.mfaToken}
          onBack={() => {
            setMfa(null);
            setLastEmail(mfa.email);
          }}
        />
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Sign in"
      subtitle="Sign in to raise and track tickets."
      footer={
        <span>
          Need an account?{' '}
          <Link to="/signup" className="font-medium text-accent underline-offset-4 hover:underline">
            Request access
          </Link>
        </span>
      }
    >
      <LoginForm
        email={lastEmail}
        onMfaRequired={(mfaToken, email) => {
          setLastEmail(email);
          setMfa({ mfaToken, email });
        }}
      />
    </AuthShell>
  );
}
