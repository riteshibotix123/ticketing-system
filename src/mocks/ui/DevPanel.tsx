/**
 * Dev-only control panel (spec 14): switch personas without knowing passwords
 * and drive the demo clock (+6h/+12h/+24h/Reset) to trigger escalations.
 * Rendered by App.tsx only when DEV && VITE_USE_MOCKS=true; stripped from
 * production builds. Uses design tokens only — no bespoke colours.
 */
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, setAccessToken } from '@/api/client';
import { useAuth } from '@/app/providers/AuthProvider';
import { ROLE_LABEL } from '@/lib/constants';
import type { Role } from '@/types/domain';

interface Persona {
  id: string;
  name: string;
  email: string;
  title?: string;
  roles: Role[];
  state: string;
}

interface PersonaListResponse {
  items: Persona[];
  clock_offset_ms: number;
  demo_password_hint: string;
}

function formatOffset(ms: number): string {
  if (ms <= 0) return 'real time';
  const hours = Math.round(ms / 3_600_000);
  return `+${hours}h`;
}

function roleLine(p: Persona): string {
  return p.roles.length > 0 ? p.roles.map((r) => ROLE_LABEL[r]).join(', ') : 'No roles yet';
}

export default function DevPanel() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const queryClient = useQueryClient();
  const { refreshMe } = useAuth();

  const { data } = useQuery({
    queryKey: ['dev-personas'],
    queryFn: () => api.get<PersonaListResponse>('/dev/personas'),
    staleTime: 30_000,
  });

  async function switchPersona(email: string): Promise<void> {
    setBusy(true);
    try {
      const session = await api.post<{ access_token: string }>('/auth/dev/persona', { email });
      setAccessToken(session.access_token);
      // Fresh identity: drop every cached response, reload /auth/me.
      queryClient.clear();
      await refreshMe();
      setStatus(`Viewing as ${email}`);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Persona switch failed.');
    } finally {
      setBusy(false);
    }
  }

  async function moveClock(hours: number | 'reset'): Promise<void> {
    setBusy(true);
    try {
      const body = hours === 'reset' ? { reset: true } : { hours };
      const res = await api.post<{ clock_offset_ms: number }>('/dev/clock', body);
      // Deadlines moved server-side: every ticket/dashboard query is stale.
      queryClient.invalidateQueries();
      setStatus(
        hours === 'reset'
          ? 'Demo clock reset.'
          : `Demo clock advanced to ${formatOffset(res.clock_offset_ms)}.`,
      );
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Clock move failed.');
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-4 left-4 z-50 rounded border border-line bg-surface px-3 py-1.5 text-small font-semibold text-muted shadow-card hover:text-fg"
      >
        Demo controls
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 left-4 z-50 w-72 rounded-lg border border-line bg-surface p-3 text-body shadow-pop">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-label-caps uppercase text-muted">Demo controls</span>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Close demo controls"
          className="rounded px-1.5 text-muted hover:text-fg"
        >
          ×
        </button>
      </div>

      <label htmlFor="dev-persona" className="mb-1 block font-semibold text-fg">
        Persona
      </label>
      <select
        id="dev-persona"
        className="mb-2 w-full rounded border border-line bg-surface-2 px-2 py-1.5 text-body text-fg"
        value=""
        disabled={busy}
        onChange={(e) => {
          if (e.target.value) void switchPersona(e.target.value);
        }}
      >
        <option value="">Switch persona…</option>
        {data?.items.map((p) => (
          <option key={p.id} value={p.email}>
            {p.name} — {roleLine(p)}
          </option>
        ))}
      </select>

      <div className="mb-1 flex items-center justify-between">
        <span className="font-semibold text-fg">Demo clock</span>
        <span className="text-small text-muted">{formatOffset(data?.clock_offset_ms ?? 0)}</span>
      </div>
      <div className="mb-2 flex flex-wrap gap-1.5">
        {([6, 12, 24] as const).map((h) => (
          <button
            key={h}
            type="button"
            disabled={busy}
            onClick={() => void moveClock(h)}
            className="rounded border border-line bg-surface-2 px-2 py-1 text-small text-fg hover:border-accent disabled:opacity-50"
          >
            +{h}h
          </button>
        ))}
        <button
          type="button"
          disabled={busy}
          onClick={() => void moveClock('reset')}
          className="rounded border border-line bg-surface-2 px-2 py-1 text-small text-fg hover:border-accent disabled:opacity-50"
        >
          Reset
        </button>
      </div>

      {status ? <p className="mb-1 text-small text-muted">{status}</p> : null}
      <p className="text-small text-muted">Demo data. Nothing leaves this page.</p>
    </div>
  );
}
