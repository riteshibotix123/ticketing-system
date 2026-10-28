import { formatDistanceToNow } from 'date-fns';
import { DISPLAY_TZ } from './constants';

/** Format a duration in ms: under 60m → "45m", under 48h → "5h 12m", else "2d 4h". */
export function formatDuration(ms: number): string {
  const totalMinutes = Math.max(0, Math.round(ms / 60000));
  if (totalMinutes < 60) return `${totalMinutes}m`;
  const totalHours = Math.floor(totalMinutes / 60);
  if (totalHours < 48) {
    const h = totalHours;
    const m = totalMinutes % 60;
    return m === 0 ? `${h}h` : `${h}h ${m}m`;
  }
  const days = Math.floor(totalHours / 24);
  const hours = totalHours % 24;
  return hours === 0 ? `${days}d` : `${days}d ${hours}h`;
}

/** Countdown copy for a future deadline: "5h 12m". */
export function formatRemaining(dueAtIso: string, now: number = Date.now()): string {
  return formatDuration(new Date(dueAtIso).getTime() - now);
}

/** Overdue copy: "2h 10m". */
export function formatOverdue(dueAtIso: string, now: number = Date.now()): string {
  return formatDuration(now - new Date(dueAtIso).getTime());
}

const dateTimeFormatter = new Intl.DateTimeFormat('en-IN', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: DISPLAY_TZ,
});

const fullDateTimeFormatter = new Intl.DateTimeFormat('en-IN', {
  dateStyle: 'medium',
  timeStyle: 'medium',
  timeZone: DISPLAY_TZ,
});

/** Absolute time displayed in Asia/Kolkata, e.g. "26 Oct 2026, 4:30 pm". */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  return dateTimeFormatter.format(new Date(iso));
}

/** Same as formatDateTime but with seconds — used in tooltips. */
export function formatDateTimeFull(iso: string | null | undefined): string {
  if (!iso) return '—';
  return `${fullDateTimeFormatter.format(new Date(iso))} IST`;
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return '—';
  return formatDistanceToNow(new Date(iso), { addSuffix: true });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return `${parts[0]![0]}${parts[parts.length - 1]![0]}`.toUpperCase();
}

/** Duration between two ISO timestamps in ms (a - b). */
export function diffMs(a: string, b: string): number {
  return new Date(a).getTime() - new Date(b).getTime();
}

/** ISO string offset by hours (used for default ETA: now + 4h). */
export function isoPlusHours(hours: number, from: Date = new Date()): string {
  return new Date(from.getTime() + hours * 3600_000).toISOString();
}

/**
 * Value for `<input type="datetime-local">` in the browser's local time from an
 * ISO UTC string, and back. datetime-local is local-time only, so we convert.
 */
export function isoToLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function localInputToIso(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

/** Date value (yyyy-MM-dd) in local time for date inputs. */
export function isoToDateInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function dateInputToIso(value: string): string | null {
  if (!value) return null;
  const d = new Date(`${value}T23:59:59`);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}
