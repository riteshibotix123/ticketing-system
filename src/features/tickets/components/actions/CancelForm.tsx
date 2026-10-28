import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { cancelSchema, type CancelInput } from '@/lib/zod-schemas';
import { Textarea } from '@/components/ui/textarea';
import type { Ticket } from '@/types/domain';
import { ActionField, ActionFormShell, useActionSubmit } from './ActionFormShell';

/** Spec 9.7 / rule 10: cancelling needs a reason. Destructive confirm. */
export function CancelForm({ ticket, onDone }: { ticket: Ticket; onDone: () => void }) {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<CancelInput>({
    resolver: zodResolver(cancelSchema),
    defaultValues: { reason: '' },
  });

  const act = useActionSubmit({
    ticketId: ticket.id,
    action: 'cancel',
    successToast: 'Ticket cancelled.',
    setError,
  });

  const onValid = async (values: CancelInput) => {
    const ok = await act.submit({ reason: values.reason.trim() });
    if (ok) onDone();
  };

  return (
    <ActionFormShell
      title="Cancel ticket"
      description="The ticket stops here. Explain why it is being cancelled."
      error={act.error}
      pending={act.pending}
      confirmLabel="Cancel ticket"
      confirmVariant="danger"
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
