import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, FileText, ShieldAlert, UploadCloud, X } from 'lucide-react';
import { errorMessage } from '@/api/client';
import { authApi } from '@/api/endpoints/auth';
import { ticketsApi } from '@/api/endpoints/tickets';
import { queryKeys } from '@/api/queryKeys';
import { Button } from '@/components/ui/button';
import { formatBytes } from '@/lib/format';
import { cn } from '@/lib/cn';
import type { Attachment } from '@/types/domain';

/** Fallback when GET /public/config fails: 5 MB, and no type restriction (nothing disabled). */
const FALLBACK_MAX_BYTES = 5 * 1024 * 1024;

type UploadState = 'uploading' | 'done' | 'failed' | 'rejected';

interface UploadRow {
  key: string;
  name: string;
  size: number;
  state: UploadState;
  attachmentId?: string;
  scan?: Attachment['scan_status'];
  error?: string;
}

type ScanStatus = NonNullable<UploadRow['scan']>;

/** Scan pill (icon + text, never colour alone). */
const SCAN_PILL: Record<ScanStatus, { text: string; cls: string; Icon: typeof CheckCircle2 }> = {
  pending: { text: 'Scanning', cls: 'border-line bg-surface-2 text-muted', Icon: ShieldAlert },
  clean: { text: 'Scan clean', cls: 'border-ok/40 bg-ok-soft text-ok', Icon: CheckCircle2 },
  infected: { text: 'Infected', cls: 'border-crit/40 bg-crit-soft text-crit', Icon: ShieldAlert },
};

/**
 * Drag-and-drop / file-picker uploader (spec 9.5). Every file is validated
 * against the public config before upload; uploaded ids are reported up so the
 * form can send `attachment_ids` with the create call.
 */
export function AttachmentUploader({
  onIdsChange,
  onPendingChange,
}: {
  /** Called with the ids of files that finished uploading. */
  onIdsChange: (ids: string[]) => void;
  /** Called while any file is still uploading (submit must wait, spec 9.5). */
  onPendingChange: (pending: boolean) => void;
}) {
  const configQuery = useQuery({
    queryKey: queryKeys.publicConfig,
    queryFn: () => authApi.publicConfig(),
    retry: false,
  });
  const maxBytes = configQuery.data?.max_attachment_bytes ?? FALLBACK_MAX_BYTES;
  const allowedMimes = useMemo(
    () => configQuery.data?.allowed_attachment_mimes ?? [],
    [configQuery.data],
  );

  const [rows, setRows] = useState<UploadRow[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputId = useId();
  const keyCounter = useRef(0);

  useEffect(() => {
    onIdsChange(rows.filter((r) => r.attachmentId).map((r) => r.attachmentId as string));
    onPendingChange(rows.some((r) => r.state === 'uploading'));
  }, [rows, onIdsChange, onPendingChange]);

  const patchRow = useCallback((key: string, patch: Partial<UploadRow>) => {
    setRows((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }, []);

  const addFiles = useCallback(
    (files: File[]) => {
      for (const file of files) {
        const key = `f${keyCounter.current++}`;
        if (file.size > maxBytes) {
          setRows((prev) => [
            ...prev,
            {
              key,
              name: file.name,
              size: file.size,
              state: 'rejected',
              error: `Larger than the ${formatBytes(maxBytes)} limit.`,
            },
          ]);
          continue;
        }
        if (allowedMimes.length > 0 && file.type && !allowedMimes.includes(file.type)) {
          setRows((prev) => [
            ...prev,
            {
              key,
              name: file.name,
              size: file.size,
              state: 'rejected',
              error: `File type "${file.type}" is not allowed.`,
            },
          ]);
          continue;
        }
        setRows((prev) => [...prev, { key, name: file.name, size: file.size, state: 'uploading' }]);
        ticketsApi
          .uploadAttachment(file)
          .then((attachment) =>
            patchRow(key, {
              state: 'done',
              attachmentId: attachment.id,
              scan: attachment.scan_status,
            }),
          )
          .catch((err: unknown) => patchRow(key, { state: 'failed', error: errorMessage(err) }));
      }
    },
    [allowedMimes, maxBytes, patchRow],
  );

  const remove = useCallback((key: string) => {
    setRows((prev) => prev.filter((row) => row.key !== key));
  }, []);

  return (
    <div className="flex flex-col gap-2">
      <div
        role="presentation"
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(Array.from(e.dataTransfer.files));
        }}
        className={cn(
          'flex flex-col items-center justify-center gap-2 rounded border border-dashed px-4 py-6 text-center',
          dragging ? 'border-accent bg-surface-2' : 'border-line',
        )}
      >
        <UploadCloud className="h-5 w-5 text-muted" aria-hidden="true" />
        <p className="text-small text-muted">Drag files here, or</p>
        <label
          htmlFor={inputId}
          className="cursor-pointer rounded border border-line bg-surface px-3 py-1.5 text-small font-medium text-fg hover:bg-surface-2"
        >
          Choose files
        </label>
        <input
          id={inputId}
          type="file"
          multiple
          className="sr-only"
          accept={allowedMimes.length > 0 ? allowedMimes.join(',') : undefined}
          onChange={(e) => {
            addFiles(Array.from(e.target.files ?? []));
            e.target.value = '';
          }}
        />
        <p className="text-small text-muted">Up to {formatBytes(maxBytes)} per file.</p>
      </div>

      {rows.length > 0 ? (
        <ul className="flex flex-col gap-1.5" aria-label="Selected attachments">
          {rows.map((row) => {
            const pill = row.scan ? SCAN_PILL[row.scan] : null;
            return (
              <li
                key={row.key}
                className="flex items-center gap-2 rounded border border-line bg-surface px-2.5 py-2"
              >
                <FileText className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="truncate text-small text-fg">{row.name}</span>
                    <span className="tabular text-small text-muted">{formatBytes(row.size)}</span>
                    {row.state === 'uploading' ? (
                      <span
                        role="progressbar"
                        aria-label={`Uploading ${row.name}`}
                        className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-2"
                      >
                        <span className="block h-full w-1/3 animate-pulse rounded-full bg-accent" />
                      </span>
                    ) : null}
                    {pill ? (
                      <span
                        className={cn(
                          'inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-small font-medium',
                          pill.cls,
                        )}
                      >
                        <pill.Icon className="h-3 w-3" aria-hidden="true" />
                        {pill.text}
                      </span>
                    ) : null}
                    {row.state === 'failed' || row.state === 'rejected' ? (
                      <span role="alert" className="text-small text-crit">
                        {row.error}
                      </span>
                    ) : null}
                  </div>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="iconSm"
                  onClick={() => remove(row.key)}
                  aria-label={`Remove ${row.name}`}
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
