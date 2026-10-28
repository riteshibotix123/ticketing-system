import { useMemo } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import { transferSchema, type TransferInput } from '@/lib/zod-schemas';
import { queryKeys } from '@/api/queryKeys';
import { departmentsApi } from '@/api/endpoints/departments';
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

/** Spec 9.7 / rule 8: reason required, new department must differ from the current one. */
export function TransferForm({ ticket, onDone }: { ticket: Ticket; onDone: () => void }) {
  const departmentsQuery = useQuery({
    queryKey: queryKeys.departments,
    queryFn: departmentsApi.list,
  });

  const schema = useMemo(
    () =>
      transferSchema.refine((v) => v.department_id !== ticket.department_id, {
        message: 'Pick a different department.',
        path: ['department_id'],
      }),
    [ticket.department_id],
  );

  const {
    control,
    register,
    handleSubmit,
    setError,
    watch,
    setValue,
    formState: { errors },
  } = useForm<TransferInput>({
    resolver: zodResolver(schema),
    defaultValues: { department_id: '', category_id: '', reason: '' },
  });

  const target = (departmentsQuery.data ?? []).find((d) => d.id === watch('department_id'));

  const act = useActionSubmit({
    ticketId: ticket.id,
    action: 'transfer',
    successToast: `Transferred to ${target?.name ?? 'the new department'}. Requester and both departments notified.`,
    setError,
  });

  const onValid = async (values: TransferInput) => {
    const ok = await act.submit({
      department_id: values.department_id,
      category_id: values.category_id || undefined,
      reason: values.reason.trim(),
    });
    if (ok) onDone();
  };

  const categories = target?.categories ?? [];

  return (
    <ActionFormShell
      title="Transfer department"
      description="Move the ticket to another department."
      error={act.error}
      pending={act.pending}
      confirmLabel="Transfer"
      onCancel={onDone}
      onConfirm={handleSubmit(onValid)}
    >
      <ActionField
        label="New department"
        required
        error={errors.department_id?.message}
        hint="Pick a different department."
        render={(f) => (
          <Controller
            control={control}
            name="department_id"
            render={({ field }) => (
              <Select
                value={field.value || undefined}
                onValueChange={(value) => {
                  field.onChange(value);
                  setValue('category_id', ''); // categories belong to the chosen department
                }}
                disabled={departmentsQuery.isLoading}
              >
                <SelectTrigger id={f.id} aria-describedby={f.describedBy} aria-invalid={f.invalid}>
                  <SelectValue
                    placeholder={
                      departmentsQuery.isLoading ? 'Loading departments…' : 'Pick a department'
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {(departmentsQuery.data ?? [])
                    .filter((d) => d.active && d.id !== ticket.department_id)
                    .map((d) => (
                      <SelectItem key={d.id} value={d.id}>
                        {d.name}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            )}
          />
        )}
      />
      {departmentsQuery.isError ? (
        <p role="alert" className="text-small text-crit">
          Could not load departments.
        </p>
      ) : null}
      <ActionField
        label="Category (optional)"
        error={errors.category_id?.message}
        render={(f) => (
          <Controller
            control={control}
            name="category_id"
            render={({ field }) => (
              <Select
                value={field.value || undefined}
                onValueChange={field.onChange}
                disabled={!target || categories.length === 0}
              >
                <SelectTrigger id={f.id} aria-describedby={f.describedBy} aria-invalid={f.invalid}>
                  <SelectValue
                    placeholder={
                      !target
                        ? 'Pick a department first'
                        : categories.length === 0
                          ? 'No categories in this department'
                          : 'Pick a category (optional)'
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {categories.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
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
      <p className="text-small text-muted">The response timer restarts in the new department.</p>
    </ActionFormShell>
  );
}
