import { AlertTriangle } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { reviseEtaSchema, type ReviseEtaInput } from '@/lib/zod-schemas';
import { isoPlusHours, isoToLocalInput, localInputToIso } from '@/lib/format';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import type { Ticket } from '@/types/domain';
import { ActionField, ActionFormShell, useActionSubmit } from './ActionFormShell';

/** Spec 9.7 / rule 7: new ETA and reason both required; warn when it moves later. */
export function ReviseEtaForm({ ticket, onDone }: { ticket: Ticket; onDone: () => void }) {
  const {
    register,
    handleSubmit,
    setError,
    watch,
    formState: { errors },
  } = useForm<ReviseEtaInput>({
    resolver: zodResolver(reviseEtaSchema),
    defaultValues: { eta: isoToLocalInput(ticket.eta ?? isoPlusHours(4)), reason: '' },
  });

  const etaValue = watch('eta');
  const movesLater = Boolean(
    ticket.eta && etaValue && new Date(etaValue).getTime() > new Date(ticket.eta).getTime(),
  );

  const act = useActionSubmit({
    ticketId: ticket.id,
    action: 'revise_eta',
    successToast: 'ETA revised. Requester notified with the reason.',
    setError,
  });

  const onValid = async (values: ReviseEtaInput) => {
    const ok = await act.submit({ eta: localInputToIso(values.eta), reason: values.reason.trim() });
    if (ok) onDone();
  };

  return (
    <ActionFormShell
      title="Revise ETA"
      description="Move the promised completion time and explain why."
      error={act.error}
      pending={act.pending}
      confirmLabel="Revise ETA"
      onCancel={onDone}
      onConfirm={handleSubmit(onValid)}
    >
      <ActionField
        label="New ETA"
        required
        error={errors.eta?.message}
        render={(f) => (
          <Input
            id={f.id}
            type="datetime-local"
            aria-invalid={f.invalid}
            aria-describedby={f.describedBy}
            {...register('eta')}
          />
        )}
      />
      <ActionField
        label="Reason"
        required
        error={errors.reason?.message}
        render={(f) => (
          <Textarea
            id={f.id}
            rows={3}
            aria-invalid={f.invalid}
            aria-describedby={f.describedBy}
            {...register('reason')}
          />
        )}
      />
      {movesLater ? (
        <p className="flex items-center gap-1.5 text-small text-warn">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          Requester will be notified.
        </p>
      ) : null}
    </ActionFormShell>
  );
}
