import { useId, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { acknowledgeSchema, type AcknowledgeInput } from '@/lib/zod-schemas';
import { isoPlusHours, isoToLocalInput, localInputToIso } from '@/lib/format';
import type { TicketActionBody } from '@/api/endpoints/tickets';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import type { Ticket } from '@/types/domain';
import { ActionField, ActionFormShell, useActionSubmit } from './ActionFormShell';

export function AcknowledgeForm({ ticket, onDone }: { ticket: Ticket; onDone: () => void }) {
  const {
    register,
    handleSubmit,
    setValue,
    setError,
    clearErrors,
    watch,
    formState: { errors },
  } = useForm<AcknowledgeInput>({
    resolver: zodResolver(acknowledgeSchema),
    defaultValues: {
      eta: isoToLocalInput(isoPlusHours(4)),
      no_eta_reason: '',
      next_checkpoint_at: '',
    },
  });
  const [noEta, setNoEta] = useState(false);
  const modeId = useId();
  const eta = watch('eta');

  const act = useActionSubmit({
    ticketId: ticket.id,
    action: 'acknowledge',
    successToast: 'Acknowledged. Response SLA met.',
    setError,
  });

  const onValid = async (values: AcknowledgeInput) => {
    const body: TicketActionBody = noEta
      ? {
          no_eta_reason: values.no_eta_reason?.trim(),
          next_checkpoint_at: localInputToIso(values.next_checkpoint_at ?? ''),
        }
      : { eta: localInputToIso(values.eta ?? '') };
    const ok = await act.submit(body);
    if (ok) onDone();
  };

  return (
    <ActionFormShell
      title="Acknowledge ticket"
      description="Set an ETA for the requester, or record why you cannot commit one yet."
      error={act.error}
      pending={act.pending}
      confirmLabel="Acknowledge"
      onCancel={onDone}
      onConfirm={handleSubmit(onValid)}
    >
      <label htmlFor={modeId} className="flex items-center gap-2 text-body text-fg">
        <Checkbox
          id={modeId}
          checked={noEta}
          onCheckedChange={(checked) => {
            const next = checked === true;
            setNoEta(next);
            setValue('eta', next ? '' : isoToLocalInput(isoPlusHours(4)));
            clearErrors(['eta', 'no_eta_reason', 'next_checkpoint_at']);
          }}
        />
        I cannot commit an ETA yet
      </label>

      {!noEta ? (
        <ActionField
          label="ETA"
          required
          error={errors.eta?.message}
          hint="When the requester should expect the next update."
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
      ) : (
        <>
          <ActionField
            label="Reason"
            required
            error={errors.no_eta_reason?.message}
            render={(f) => (
              <Textarea
                id={f.id}
                rows={2}
                aria-invalid={f.invalid}
                aria-describedby={f.describedBy}
                {...register('no_eta_reason')}
              />
            )}
          />
          <ActionField
            label="Next checkpoint"
            required
            error={errors.next_checkpoint_at?.message}
            hint="When you will next update the requester."
            render={(f) => (
              <Input
                id={f.id}
                type="datetime-local"
                aria-invalid={f.invalid}
                aria-describedby={f.describedBy}
                {...register('next_checkpoint_at')}
              />
            )}
          />
        </>
      )}
      {eta === '' && !noEta ? (
        <p className="text-small text-muted">Pick an ETA or choose the no-ETA option.</p>
      ) : null}
    </ActionFormShell>
  );
}
