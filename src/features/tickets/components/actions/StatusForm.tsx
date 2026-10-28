import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { askRequesterSchema, type AskRequesterInput } from '@/lib/zod-schemas';
import { Textarea } from '@/components/ui/textarea';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import type { Ticket, TicketAction } from '@/types/domain';
import { ActionField, ActionFormShell, useActionSubmit } from './ActionFormShell';

type StatusAction = Extract<TicketAction, 'start_work' | 'ask_requester' | 'resume'>;

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
      action === 'ask_requester'
        ? 'Awaiting requester. Timer paused.'
        : 'Status set to In Progress.',
    setError,
  });

  if (action === 'start_work' || action === 'resume') {
    const resuming = action === 'resume';
    return (
      <ConfirmDialog
        open
        onOpenChange={(open) => {
          if (!open) onDone();
        }}
        title={resuming ? 'Resume work?' : 'Start work?'}
        description={
          resuming
            ? 'This resumes the timers and sets the ticket to In Progress.'
            : 'This sets the ticket to In Progress and notifies the requester.'
        }
        confirmLabel={resuming ? 'Resume work' : 'Start work'}
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
    const ok = await act.submit({
      status: 'awaiting_requester',
      message: values.message.trim(),
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
        label="Message"
        required
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
