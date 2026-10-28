import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { reopenSchema, type ReopenInput } from '@/lib/zod-schemas';
import { Textarea } from '@/components/ui/textarea';
import type { Ticket } from '@/types/domain';
import { ActionField, ActionFormShell, useActionSubmit } from './ActionFormShell';

/** Spec 9.7 / rule 10: reopening needs a reason. */
export function ReopenForm({ ticket, onDone }: { ticket: Ticket; onDone: () => void }) {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<ReopenInput>({
    resolver: zodResolver(reopenSchema),
    defaultValues: { reason: '' },
  });

  const act = useActionSubmit({
    ticketId: ticket.id,
    action: 'reopen',
    successToast: 'Ticket reopened. Responsible team notified.',
    setError,
  });

  const onValid = async (values: ReopenInput) => {
    const ok = await act.submit({ reason: values.reason.trim() });
    if (ok) onDone();
  };

  return (
    <ActionFormShell
      title="Reopen ticket"
      description="Explain what is still wrong. The responsible team is notified."
      error={act.error}
      pending={act.pending}
      confirmLabel="Reopen"
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
    </ActionFormShell>
  );
}
