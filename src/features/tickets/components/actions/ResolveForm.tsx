import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { resolveSchema, type ResolveInput } from '@/lib/zod-schemas';
import { Textarea } from '@/components/ui/textarea';
import type { Ticket } from '@/types/domain';
import { ActionField, ActionFormShell, useActionSubmit } from './ActionFormShell';

/** Spec 9.7 / rule 5: resolving needs a resolution summary. */
export function ResolveForm({ ticket, onDone }: { ticket: Ticket; onDone: () => void }) {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<ResolveInput>({
    resolver: zodResolver(resolveSchema),
    defaultValues: { summary: '' },
  });

  const act = useActionSubmit({
    ticketId: ticket.id,
    action: 'resolve',
    successToast: 'Resolved. Requester asked to confirm.',
    setError,
  });

  const onValid = async (values: ResolveInput) => {
    const ok = await act.submit({ summary: values.summary.trim() });
    if (ok) onDone();
  };

  return (
    <ActionFormShell
      title="Resolve ticket"
      description="Summarise what was done. The requester is asked to confirm closure."
      error={act.error}
      pending={act.pending}
      confirmLabel="Resolve"
      onCancel={onDone}
      onConfirm={handleSubmit(onValid)}
    >
      <ActionField
        label="Resolution summary"
        required
        error={errors.summary?.message}
        render={(f) => (
          <Textarea
            id={f.id}
            rows={5}
            aria-invalid={f.invalid}
            aria-describedby={f.describedBy}
            placeholder="What was the fix, and what should the requester check?"
            {...register('summary')}
          />
        )}
      />
    </ActionFormShell>
  );
}
