import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { changePrioritySchema, type ChangePriorityInput } from '@/lib/zod-schemas';
import { PRIORITY_LABEL, PRIORITY_MEANING, PRIORITY_ORDER } from '@/lib/constants';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import type { Ticket } from '@/types/domain';
import { ActionField, ActionFormShell, useActionSubmit } from './ActionFormShell';

/**
 * Spec 9.7 / rule 9: priority + required reason. Each option shows its fixed
 * meaning (spec 11.1). The server only offers this action to Spoke/Admin, so no
 * client-side option filtering is needed.
 */
export function ChangePriorityForm({ ticket, onDone }: { ticket: Ticket; onDone: () => void }) {
  const {
    control,
    register,
    handleSubmit,
    setError,
    watch,
    formState: { errors },
  } = useForm<ChangePriorityInput>({
    resolver: zodResolver(changePrioritySchema),
    defaultValues: { priority: ticket.priority, reason: '' },
  });

  const act = useActionSubmit({
    ticketId: ticket.id,
    action: 'change_priority',
    successToast: 'Priority changed. Requester notified.',
    setError,
  });

  const onValid = async (values: ChangePriorityInput) => {
    const ok = await act.submit({ priority: values.priority, reason: values.reason.trim() });
    if (ok) onDone();
  };

  return (
    <ActionFormShell
      title="Change priority"
      description="Priority affects sorting and escalation speed."
      error={act.error}
      pending={act.pending}
      confirmLabel="Change priority"
      onCancel={onDone}
      onConfirm={handleSubmit(onValid)}
    >
      <ActionField
        label="Priority"
        required
        error={errors.priority?.message}
        render={(f) => (
          <Controller
            control={control}
            name="priority"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id={f.id} aria-describedby={f.describedBy} aria-invalid={f.invalid}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PRIORITY_ORDER.map((p) => (
                    <SelectItem key={p} value={p} hint={PRIORITY_MEANING[p]}>
                      {PRIORITY_LABEL[p]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        )}
      />
      <p className="text-small text-muted">{PRIORITY_MEANING[watch('priority')]}</p>
      <ActionField
        label="Reason"
        required
        error={errors.reason?.message}
        render={(f) => (
          <Textarea
            id={f.id}
            rows={2}
            aria-invalid={f.invalid}
            aria-describedby={f.describedBy}
            {...register('reason')}
          />
        )}
      />
      <p className="text-small text-muted">Requester will be notified.</p>
    </ActionFormShell>
  );
}
