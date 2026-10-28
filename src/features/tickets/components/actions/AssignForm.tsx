import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import { assignSchema, type AssignInput } from '@/lib/zod-schemas';
import { departmentsApi } from '@/api/endpoints/departments';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { Ticket } from '@/types/domain';
import { ActionField, ActionFormShell, useActionSubmit } from './ActionFormShell';

/** Spec 9.7: person required, optional reason, "You keep supervisory access." */
export function AssignForm({ ticket, onDone }: { ticket: Ticket; onDone: () => void }) {
  const {
    control,
    register,
    handleSubmit,
    setError,
    watch,
    formState: { errors },
  } = useForm<AssignInput>({
    resolver: zodResolver(assignSchema),
    defaultValues: { assignee_id: '', reason: '' },
  });

  const peopleQuery = useQuery({
    queryKey: ['ticket-assignable', ticket.department_id],
    queryFn: () => departmentsApi.members(ticket.department_id),
    staleTime: 60_000,
  });
  const people = peopleQuery.data ?? [];
  const selected = people.find((p) => p.id === watch('assignee_id'));

  const act = useActionSubmit({
    ticketId: ticket.id,
    action: 'assign',
    successToast: `Delegated to ${selected?.name ?? 'the assignee'}. You keep supervisory access.`,
    setError,
  });

  const onValid = async (values: AssignInput) => {
    const ok = await act.submit({
      assignee_id: values.assignee_id,
      reason: values.reason?.trim() || undefined,
    });
    if (ok) onDone();
  };

  return (
    <ActionFormShell
      title="Delegate ticket"
      description="Hand the ticket to an active member of this department."
      error={act.error}
      pending={act.pending}
      confirmLabel="Delegate"
      onCancel={onDone}
      onConfirm={handleSubmit(onValid)}
    >
      <ActionField
        label="Person"
        required
        error={errors.assignee_id?.message}
        render={(f) => (
          <Controller
            control={control}
            name="assignee_id"
            render={({ field }) => (
              <Select
                value={field.value || undefined}
                onValueChange={field.onChange}
                disabled={peopleQuery.isLoading}
              >
                <SelectTrigger id={f.id} aria-describedby={f.describedBy} aria-invalid={f.invalid}>
                  <SelectValue
                    placeholder={peopleQuery.isLoading ? 'Loading people…' : 'Pick a person'}
                  />
                </SelectTrigger>
                <SelectContent>
                  {people.map((p) => (
                    <SelectItem key={p.id} value={p.id} hint={p.email}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        )}
      />
      <p className="text-small text-muted">You keep supervisory access.</p>
      <ActionField
        label="Reason (optional)"
        error={errors.reason?.message}
        render={(f) => (
          <Input
            id={f.id}
            type="text"
            aria-invalid={f.invalid}
            aria-describedby={f.describedBy}
            {...register('reason')}
          />
        )}
      />
    </ActionFormShell>
  );
}
