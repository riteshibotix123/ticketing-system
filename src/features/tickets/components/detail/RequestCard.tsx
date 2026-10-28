import { useState } from 'react';
import {
  CheckCircle2,
  Clock,
  Download,
  Paperclip,
  ShieldAlert,
  type LucideIcon,
} from 'lucide-react';
import { formatBytes } from '@/lib/format';
import { Badge } from '@/components/ui/badge';
import { errorMessage } from '@/api/client';
import { ticketsApi } from '@/api/endpoints/tickets';
import type { Attachment, Ticket } from '@/types/domain';

const SCAN_META: Record<
  Attachment['scan_status'],
  { label: string; variant: 'ok' | 'warn' | 'crit'; Icon: LucideIcon }
> = {
  pending: { label: 'Scanning', variant: 'warn', Icon: Clock },
  clean: { label: 'Clean', variant: 'ok', Icon: CheckCircle2 },
  infected: { label: 'Infected', variant: 'crit', Icon: ShieldAlert },
};

/** Spec 9.6 card 1: description plus attachments with scan status and download. */
export function RequestCard({ ticket }: { ticket: Ticket }) {
  const [downloading, setDownloading] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const download = async (attachment: Attachment) => {
    setDownloading(attachment.id);
    setDownloadError(null);
    try {
      const blob = await ticketsApi.downloadAttachment(attachment.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = attachment.name;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError(errorMessage(err));
    } finally {
      setDownloading(null);
    }
  };

  return (
    <section className="card p-4">
      <h2 className="text-section-title text-fg">Request</h2>
      <p className="prose-body mt-2">{ticket.description}</p>
      {ticket.attachments.length > 0 ? (
        <div className="mt-4">
          <h3 className="label-caps">Attachments</h3>
          <ul className="mt-2 flex flex-col gap-1.5">
            {ticket.attachments.map((att) => {
              const scan = SCAN_META[att.scan_status];
              const ScanIcon = scan.Icon;
              return (
                <li
                  key={att.id}
                  className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded border border-line bg-surface-2 px-2.5 py-1.5 text-small"
                >
                  <Paperclip className="h-3.5 w-3.5 shrink-0 text-muted" aria-hidden="true" />
                  <span
                    className="min-w-0 max-w-[28ch] truncate font-medium text-fg"
                    title={att.name}
                  >
                    {att.name}
                  </span>
                  <span className="tabular text-muted">{formatBytes(att.size)}</span>
                  <Badge variant={scan.variant} className="ml-auto">
                    <ScanIcon className="h-3 w-3" aria-hidden="true" />
                    {scan.label}
                  </Badge>
                  {att.scan_status === 'clean' ? (
                    <button
                      type="button"
                      onClick={() => void download(att)}
                      disabled={downloading === att.id}
                      className="inline-flex items-center gap-1 font-medium text-accent underline-offset-4 hover:underline disabled:opacity-60"
                    >
                      <Download className="h-3.5 w-3.5" aria-hidden="true" />
                      {downloading === att.id ? 'Downloading…' : 'Download'}
                    </button>
                  ) : null}
                </li>
              );
            })}
          </ul>
          {downloadError ? (
            <p role="alert" className="mt-2 text-small text-crit">
              {downloadError}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
