import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import type { Ticket, TicketAction } from '@/types/domain';
import { useActionSubmit } from '../actions/ActionFormShell';
import { AcknowledgeForm } from '../actions/AcknowledgeForm';
import { AssignForm } from '../actions/AssignForm';
import { CancelForm } from '../actions/CancelForm';
import { ChangePriorityForm } from '../actions/ChangePriorityForm';
import { HoldForm } from '../actions/HoldForm';
import { ReopenForm } from '../actions/ReopenForm';
import { ResolveForm } from '../actions/ResolveForm';
import { ReviseEtaForm } from '../actions/ReviseEtaForm';
import { StatusForm } from '../actions/StatusForm';
import { TransferForm } from '../actions/TransferForm';

/** Actions with an inline form; comment/internal_note belong to the comment box. */
const FORM_ACTIONS: TicketAction[] = [
  'acknowledge',
  'assign',
  'transfer',
  'change_priority',
  'revise_eta',
  'start_work',
  'ask_requester',
  'hold',
  'resolve',
  'confirm_closure',
  'reopen',
  'cancel',
];

const ACTION_LABEL: Record<TicketAction, string> = {
  acknowledge: 'Acknowledge',
  assign: 'Assign / delegate',
  transfer: 'Transfer department',
  change_priority: 'Change priority',
  revise_eta: 'Revise ETA',
  start_work: 'Start work',
  ask_requester: 'Ask requester',
  hold: 'Put on hold',
  resolve: 'Resolve',
  confirm_closure: 'Confirm closure',
  reopen: 'Reopen',
  cancel: 'Cancel',
  comment: 'Comment',
  internal_note: 'Internal note',
};

/**
 * Spec 9.7: buttons only for actions the server put in `ticket.allowed_actions`.
 * Each button toggles an inline form (not a modal) under the row; confirm
 * closure uses the in-page ConfirmDialog since it has no fields.
 */
export function TicketActionPanel({ ticket }: { ticket: Ticket }) {
  const [open, setOpen] = useState<TicketAction | null>(null);
  const confirmClosure = useActionSubmit({
    ticketId: ticket.id,
    action: 'confirm_closure',
    successToast: 'Ticket closed. Thank you.',
  });

  const actions = ticket.allowed_actions.filter((a) => FORM_ACTIONS.includes(a));
  if (actions.length === 0) return null;

  const toggle = (action: TicketAction) =>
    setOpen((current) => (current === action ? null : action));

  function renderForm() {
    if (!open) return null;
    const done = () => setOpen(null);
    switch (open) {
      case 'acknowledge':
        return <AcknowledgeForm ticket={ticket} onDone={done} />;
      case 'assign':
        return <AssignForm ticket={ticket} onDone={done} />;
      case 'transfer':
        return <TransferForm ticket={ticket} onDone={done} />;
      case 'change_priority':
        return <ChangePriorityForm ticket={ticket} onDone={done} />;
      case 'revise_eta':
        return <ReviseEtaForm ticket={ticket} onDone={done} />;
      case 'start_work':
      case 'ask_requester':
        return <StatusForm ticket={ticket} action={open} onDone={done} />;
      case 'hold':
        return <HoldForm ticket={ticket} onDone={done} />;
      case 'resolve':
        return <ResolveForm ticket={ticket} onDone={done} />;
      case 'reopen':
        return <ReopenForm ticket={ticket} onDone={done} />;
      case 'cancel':
        return <CancelForm ticket={ticket} onDone={done} />;
      case 'confirm_closure':
        return (
          <ConfirmDialog
            open
            onOpenChange={(isOpen) => {
              if (!isOpen) setOpen(null);
            }}
            title="Confirm closure"
            description="Confirm the ticket is fixed. It will be closed."
            confirmLabel="Confirm closure"
            loading={confirmClosure.pending}
            onConfirm={() => {
              void confirmClosure.submit({}).then((ok) => {
                if (ok) setOpen(null);
              });
            }}
          >
            {confirmClosure.error ? (
              <p role="alert" className="text-small text-crit">
                {confirmClosure.error}
              </p>
            ) : null}
          </ConfirmDialog>
        );
      default:
        return null;
    }
  }

  return (
    <section className="card p-4">
      <h2 className="text-section-title text-fg">Actions</h2>
      <div className="mt-3 flex flex-wrap gap-2">
        {actions.map((action) => (
          <Button
            key={action}
            type="button"
            size="sm"
            variant={action === 'cancel' ? 'outlineDanger' : 'secondary'}
            aria-expanded={open === action}
            onClick={() => toggle(action)}
          >
            {ACTION_LABEL[action]}
          </Button>
        ))}
      </div>
      {renderForm()}
    </section>
  );
}
