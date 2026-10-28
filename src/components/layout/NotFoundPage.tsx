import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';

/** 404 — reveals nothing, offers a way home. */
export default function NotFoundPage() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-bg px-4 text-center">
      <Compass className="h-8 w-8 text-muted" aria-hidden="true" />
      <h1 className="text-page-title text-fg">Page not found</h1>
      <p className="max-w-[46ch] text-small text-muted">
        The address may be wrong, or the page has moved.
      </p>
      <Link
        to="/dashboard"
        className="mt-2 rounded bg-accent px-4 py-2 text-body font-medium text-accent-fg"
      >
        Back to dashboard
      </Link>
    </main>
  );
}
