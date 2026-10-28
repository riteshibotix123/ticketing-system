import { useId } from 'react';
import { Controller, useForm, type SubmitErrorHandler } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { acknowledgeSchema, type AcknowledgeInput } from '@/lib/zod-schemas';
import { isoPlusHours, isoToLocalInput, localInputToIso } from '@/lib/format';
import type { TicketActionBody } from '@/api/endpoints/tickets';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import type { Ticket } from '@/types/domain';
import { ActionField, ActionFormShell, useActionSubmit } from './ActionFormShell';

/**
 * Spec 9.7: acknowledge with an ETA (default now + 4h, must be future), or the
 * "cannot commit an ETA" mode with a reason and next checkpoint (rule 4).
 */
export function AcknowledgeForm({ ticket, onDone }: { ticket: Ticket; onDone: () => void }) {
  const {
    control,
    register,
    handleSubmit,
    getValues,
    setError,
    clearErrors,
    watch,
    formState: { errors },
  } = useForm<AcknowledgeInput>({
    resolver: zodResolver(acknowledgeSchema),
    defaultValues: {
      use_eta: true,
      eta: isoToLocalInput(isoPlusHours(4)),
      no_eta_reason: '',
      checkpoint: '',
    },
  });
  const useEta = watch('use_eta');
  const modeId = useId();

  const act = useActionSubmit({
    ticketId: ticket.id,
    action: 'acknowledge',
    successToast: 'Acknowledged. Response SLA met.',
    setError,
  });

  // The schema reports the shared "one of the two" rule at `eta`; in no-ETA mode
  // surface that message on the fields it actually applies to.
  const onInvalid: SubmitErrorHandler<AcknowledgeInput> = (errs) => {
    if (getValues('use_eta') || !errs.eta) return;
    const message = errs.eta.message ?? 'Required.';
    if (!getValues('no_eta_reason')?.trim()) setError('no_eta_reason', { type: 'server', message });
    else if (!getValues('checkpoint')?.trim()) setError('checkpoint', { type: 'server', message });
  };

  const onValid = async (values: AcknowledgeInput) => {
    let body: TicketActionBody;
    if (values.use_eta) {
      body = { eta: localInputToIso(values.eta ?? '') };
    } else {
      // Whitespace-only values slip past the schema; block them here (rule 4).
      const reason = values.no_eta_reason?.trim();
      const checkpoint = values.checkpoint?.trim();
      if (!reason || !checkpoint) {
        if (!reason) setError('no_eta_reason', { type: 'validate', message: 'Required.' });
        if (!checkpoint) setError('checkpoint', { type: 'validate', message: 'Required.' });
        return;
      }
      body = { no_eta_reason: reason, checkpoint };
    }
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
      onConfirm={handleSubmit(onValid, onInvalid)}
    >
      <label htmlFor={modeId} className="flex items-center gap-2 text-body text-fg">
        <Controller
          control={control}
          name="use_eta"
          render={({ field }) => (
            <Checkbox
              id={modeId}
              checked={field.value}
              onCheckedChange={(checked) => {
                field.onChange(checked === true);
                clearErrors(['eta', 'no_eta_reason', 'checkpoint']);
              }}
            />
          )}
        />
        I cannot commit an ETA yet
      </label>

      {useEta ? (
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
            error={errors.checkpoint?.message}
            hint="When you will next update the requester."
            render={(f) => (
              <Input
                id={f.id}
                type="text"
                placeholder="e.g. After the vendor replies"
                aria-invalid={f.invalid}
                aria-describedby={f.describedBy}
                {...register('checkpoint')}
              />
            )}
          />
        </>
      )}
    </ActionFormShell>
  );
}
