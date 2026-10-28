import { cn } from '@/lib/cn';
import { slaDisplay, type SlaDisplay } from '@/lib/sla';
import type { SlaState, Ticket } from '@/types/domain';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

const TONE: Record<string, string> = {
  ok: 'text-ok',
  warn: 'text-warn',
  crit: 'text-crit',
  muted: 'text-muted',
  info: 'text-info',
};

export interface SlaIndicatorProps {
  sla: SlaState;
  now?: number;
  /** Requester view: never shows levels or escalation detail (spec 11.3). */
  requesterView?: boolean;
  /** Hide the countdown text (dense tables). */
  compact?: boolean;
  className?: string;
}

/**
 * Icon + label + countdown text. Icons: ● on track, ▲ warning, ■ breached/L3,
 * ◷ paused/stopped. Text: "Response due in 5h 12m", "Response overdue 2h 10m"…
 */
export function SlaIndicator({ sla, now, requesterView, compact, className }: SlaIndicatorProps) {
  if (requesterView) {
    return (
      <span className={cn('inline-flex items-center gap-1.5 text-small text-muted', className)}>
        <span aria-hidden="true">◷</span>
        {sla.stopped || sla.paused
          ? sla.label
          : sla.kind === 'initial_response'
            ? 'Awaiting first response'
            : 'In progress'}
      </span>
    );
  }

  const d: SlaDisplay = slaDisplay(sla, now);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn('inline-flex items-center gap-1.5 whitespace-nowrap text-small', className)}
          data-testid="sla-indicator"
        >
          <span aria-hidden="true" className={cn('font-mono leading-none', TONE[d.tone])}>
            {d.icon}
          </span>
          <span className={cn('font-medium', TONE[d.tone])}>{d.label}</span>
          {!compact && d.text ? <span className="tabular text-muted">{d.text}</span> : null}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        <p>{sla.label}</p>
        {d.text ? <p className="tabular text-muted">{d.text}</p> : null}
        {sla.level > 0 && !d.paused && !d.stopped ? (
          <p className="text-muted">Escalation level {sla.level}</p>
        ) : null}
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * Full-width SLA banner on the ticket detail (staff only).
 * Banner colour follows the escalation level; paused/stopped is neutral.
 */
export function SlaBanner({
  ticket,
  now,
  isRequester,
}: {
  ticket: Pick<Ticket, 'sla'>;
  now?: number;
  isRequester: boolean;
}) {
  const d = slaDisplay(ticket.sla, now);
  const toneClass =
    d.stopped || d.paused
      ? 'border-line bg-surface-2 text-muted'
      : d.tone === 'ok'
        ? 'border-ok/40 bg-ok-soft text-ok'
        : d.tone === 'warn'
          ? 'border-warn/40 bg-warn-soft text-warn'
          : 'border-crit/40 bg-crit-soft text-crit';

  if (isRequester) {
    return (
      <div
        className="rounded-md border border-line bg-surface-2 px-4 py-3 text-body text-muted"
        role="status"
      >
        <span aria-hidden="true" className="mr-2">
          ◷
        </span>
        {ticket.sla.label}
      </div>
    );
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border px-4 py-3',
        toneClass,
      )}
      data-testid="sla-banner"
    >
      <span aria-hidden="true" className="font-mono text-[13px] leading-none">
        {d.icon}
      </span>
      <span className="text-section-title">{d.label}</span>
      <span className="tabular text-body">{d.text || ticket.sla.label}</span>
      <span className="ml-auto text-small">{ticket.sla.label}</span>
    </div>
  );
}
