import { useState, type FormEventHandler, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { errorMessage, isApiError } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import { ticketsApi, type TicketActionBody } from '@/api/endpoints/tickets';
import { FormField, useField } from '@/components/common/FormField';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/useToast';
import type { TicketAction } from '@/types/domain';

/**
 * React Hook Form's `setError` typed without `any`: the `never` parameter lets
 * the hook pass any server field key while the form keeps its own field types.
 */
type ServerFieldSetter = (name: never, error: { message: string; type: string }) => void;

export interface ActionSubmitApi {
  /** POST the action. Resolves true on success (toast + invalidation done). */
  submit: (body: TicketActionBody) => Promise<boolean>;
  pending: boolean;
  /** Non-field error for the form-level `role="alert"` box. */
  error: string | null;
}

/**
 * Shared mutation for every lifecycle action (spec 9.7 / 13 / 19):
 * success toast with the exact copy deck string, invalidate ticket, tickets and
 * dashboard, map `ApiError.fields` onto the form, and 409 → conflict toast +
 * ticket refetch.
 */
export function useActionSubmit(opts: {
  ticketId: string;
  action: TicketAction;
  successToast: string;
  setError?: ServerFieldSetter;
}): ActionSubmitApi {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(false);
  const [error, setErrorState] = useState<string | null>(null);

  async function submit(body: TicketActionBody): Promise<boolean> {
    const { ticketId, action, successToast, setError } = opts;
    setPending(true);
    setErrorState(null);
    try {
      await ticketsApi.act(ticketId, action, body);
      toast.success(successToast);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.ticket(ticketId) }),
        queryClient.invalidateQueries({ queryKey: ['tickets'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      ]);
      return true;
    } catch (err) {
      if (isApiError(err)) {
        if (err.status === 409) {
          // Spec 13: conflict → toast and refetch the latest version.
          toast.error('This ticket changed. Refreshed with the latest version.');
          void queryClient.invalidateQueries({ queryKey: queryKeys.ticket(ticketId) });
          return false;
        }
        const fieldErrors = Object.entries(err.fields ?? {});
        if (fieldErrors.length > 0 && setError) {
          fieldErrors.forEach(([name, message]) =>
            setError(name as never, { message, type: 'server' }),
          );
          return false;
        }
        setErrorState(err.message);
      } else {
        setErrorState(errorMessage(err));
      }
      return false;
    } finally {
      setPending(false);
    }
  }

  return { submit, pending, error };
}

export interface ActionFieldProps {
  label: string;
  error?: string;
  hint?: ReactNode;
  required?: boolean;
  /** Render prop: the control receives FormField's generated id and aria wiring. */
  render: (ctx: { id: string; describedBy?: string; invalid: boolean }) => ReactNode;
}

/**
 * Bridge over the shared `FormField`: gives action-form controls the field's
 * generated id, `aria-describedby` and `aria-invalid` (spec 3.5/3.6).
 */
export function ActionField({ label, error, hint, required, render }: ActionFieldProps) {
  return (
    <FormField label={label} error={error} hint={hint} required={required}>
      <FieldBridge render={render} />
    </FormField>
  );
}

function FieldBridge({ render }: { render: ActionFieldProps['render'] }) {
  const ctx = useField();
  return <>{render(ctx ?? { id: '', invalid: false, describedBy: undefined })}</>;
}

/**
 * Inline action form layout (spec 9.7): title, fields, form-level alert,
 * Cancel + Confirm. Not a modal — it renders under the action buttons.
 */
export function ActionFormShell({
  title,
  description,
  error,
  pending,
  confirmLabel = 'Confirm',
  confirmVariant = 'primary',
  onCancel,
  onConfirm,
  children,
}: {
  title: string;
  description?: string;
  error?: string | null;
  pending?: boolean;
  confirmLabel?: string;
  confirmVariant?: 'primary' | 'danger';
  onCancel: () => void;
  onConfirm: FormEventHandler<HTMLFormElement>;
  children: ReactNode;
}) {
  return (
    <div className="mt-3 rounded-md border border-line bg-surface-2 p-4">
      <h3 className="text-section-title text-fg">{title}</h3>
      {description ? (
        <p className="mt-1 max-w-[65ch] text-small text-muted">{description}</p>
      ) : null}
      <form noValidate className="mt-3 flex flex-col gap-3" onSubmit={onConfirm}>
        {children}
        {error ? (
          <div
            role="alert"
            className="border-crit/40 rounded border bg-crit-soft px-3 py-2 text-small text-crit"
          >
            {error}
          </div>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onCancel} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" variant={confirmVariant} loading={pending} loadingLabel="Saving">
            {confirmLabel}
          </Button>
        </div>
      </form>
    </div>
  );
}
