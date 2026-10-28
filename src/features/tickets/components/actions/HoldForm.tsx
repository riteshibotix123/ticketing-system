import { useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { holdSchema, type HoldInput } from '@/lib/zod-schemas';
import { dateInputToIso, isoToDateInput } from '@/lib/format';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import type { Ticket } from '@/types/domain';
import { ActionField, ActionFormShell, useActionSubmit } from './ActionFormShell';

/** Spec 9.7 / rule 6: reason and next review date, date must be in the future. */
export function HoldForm({ ticket, onDone }: { ticket: Ticket; onDone: () => void }) {
  const schema = useMemo(
    () =>
      holdSchema.refine((v) => v.review_date > isoToDateInput(new Date().toISOString()), {
        message: 'Pick a date in the future.',
        path: ['review_date'],
      }),
    [],
  );

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<HoldInput>({
    resolver: zodResolver(schema),
    defaultValues: { reason: '', review_date: '' },
  });

  const act = useActionSubmit({
    ticketId: ticket.id,
    action: 'hold',
    successToast: 'Put on hold. SLA timer paused.',
    setError,
  });

  const onValid = async (values: HoldInput) => {
    const ok = await act.submit({
      reason: values.reason.trim(),
      review_date: dateInputToIso(values.review_date) ?? undefined,
    });
    if (ok) onDone();
  };

  return (
    <ActionFormShell
      title="Put on hold"
      description="Pause work on this ticket until the review date."
      error={act.error}
      pending={act.pending}
      confirmLabel="Put on hold"
      onCancel={onDone}
      onConfirm={handleSubmit(onValid)}
    >
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
      <ActionField
        label="Next review date"
        required
        error={errors.review_date?.message}
        hint="The ticket is reviewed on this date."
        render={(f) => (
          <Input
            id={f.id}
            type="date"
            min={isoToDateInput(new Date(Date.now() + 86_400_000).toISOString())}
            aria-invalid={f.invalid}
            aria-describedby={f.describedBy}
            {...register('review_date')}
          />
        )}
      />
    </ActionFormShell>
  );
}
