import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { askRequesterSchema, type AskRequesterInput } from '@/lib/zod-schemas';
import { Textarea } from '@/components/ui/textarea';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import type { Ticket, TicketAction } from '@/types/domain';
import { ActionField, ActionFormShell, useActionSubmit } from './ActionFormShell';

type StatusAction = Extract<TicketAction, 'start_work' | 'ask_requester'>;

/**
 * Spec 9.7: "Start work" has no fields (in-page confirm dialog, sets
 * In Progress); "Ask requester" takes an optional message and sets
 * Awaiting Requester, which pauses the timer.
 */
export function StatusForm({
  ticket,
  action,
  onDone,
}: {
  ticket: Ticket;
  action: StatusAction;
  onDone: () => void;
}) {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<AskRequesterInput>({
    resolver: zodResolver(askRequesterSchema),
    defaultValues: { message: '' },
  });

  const act = useActionSubmit({
    ticketId: ticket.id,
    action,
    successToast:
      action === 'start_work' ? 'Status set to In Progress.' : 'Awaiting requester. Timer paused.',
    setError,
  });

  if (action === 'start_work') {
    return (
      <ConfirmDialog
        open
        onOpenChange={(open) => {
          if (!open) onDone();
        }}
        title="Start work?"
        description="This sets the ticket to In Progress and notifies the requester."
        confirmLabel="Start work"
        loading={act.pending}
        onConfirm={() => {
          void act.submit({ status: 'in_progress' }).then((ok) => {
            if (ok) onDone();
          });
        }}
      >
        {act.error ? (
          <p role="alert" className="text-small text-crit">
            {act.error}
          </p>
        ) : null}
      </ConfirmDialog>
    );
  }

  const onValid = async (values: AskRequesterInput) => {
    const message = values.message?.trim();
    const ok = await act.submit({
      status: 'awaiting_requester',
      ...(message ? { message } : {}),
    });
    if (ok) onDone();
  };

  return (
    <ActionFormShell
      title="Ask the requester"
      description="Sets the ticket to Awaiting Requester. The timer pauses until they reply."
      error={act.error}
      pending={act.pending}
      confirmLabel="Ask requester"
      onCancel={onDone}
      onConfirm={handleSubmit(onValid)}
    >
      <ActionField
        label="Message (optional)"
        error={errors.message?.message}
        hint="Sent to the requester with the status change."
        render={(f) => (
          <Textarea
            id={f.id}
            rows={3}
            aria-invalid={f.invalid}
            aria-describedby={f.describedBy}
            {...register('message')}
          />
        )}
      />
    </ActionFormShell>
  );
}
