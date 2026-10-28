import { useId, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { Textarea } from '@/components/ui/textarea';
import { errorMessage, isApiError } from '@/api/client';
import { usersApi } from '@/api/endpoints/users';
import { useToast } from '@/hooks/useToast';
import { reasonSchema } from '@/lib/zod-schemas';
import type { UserListItem } from '@/types/domain';

/**
 * Deactivate or activate an account: an in-page ConfirmDialog with a required
 * reason (reasonSchema) — never window.confirm (spec 13/18).
 */
export function DeactivateDialog({
  user,
  open,
  onOpenChange,
}: {
  user: UserListItem;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { success } = useToast();
  const queryClient = useQueryClient();
  const reasonId = useId();
  const activating = user.state === 'deactivated';

  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const mutation = useMutation<unknown, unknown, string | null>({
    mutationFn: (value: string | null) =>
      activating ? usersApi.activate(user.id) : usersApi.deactivate(user.id, value ?? ''),
    onSuccess: (data) => {
      const result = data as { result?: string } | null;
      success(
        result?.result === 'protected_request_created'
          ? 'Sent for second Super Admin approval.'
          : activating
            ? 'Account activated.'
            : 'Account deactivated.',
      );
      void queryClient.invalidateQueries({ queryKey: ['users'] });
      void queryClient.invalidateQueries({ queryKey: ['signup-requests'] });
      onOpenChange(false);
    },
    onError: (error) => {
      if (isApiError(error) && error.fields?.reason) setReasonError(error.fields.reason);
      setServerError(errorMessage(error));
    },
  });

  const confirm = () => {
    if (activating) {
      mutation.mutate(null);
      return;
    }
    const parsed = reasonSchema.safeParse({ reason });
    if (!parsed.success) {
      setReasonError(parsed.error.issues[0]?.message ?? 'Required.');
      return;
    }
    setReasonError(null);
    mutation.mutate(parsed.data.reason);
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={activating ? 'Activate account' : 'Deactivate account'}
      description={
        activating
          ? `${user.name} · ${user.email} regains access.`
          : `${user.name} · ${user.email} loses access immediately.`
      }
      confirmLabel={activating ? 'Activate' : 'Deactivate'}
      destructive={!activating}
      loading={mutation.isPending}
      onConfirm={confirm}
    >
      <div className="flex flex-col gap-1.5">
        <label htmlFor={reasonId} className="text-small font-medium text-fg">
          Reason
          <span aria-hidden="true" className="ml-1 text-crit">
            *
          </span>
        </label>
        <Textarea
          id={reasonId}
          rows={2}
          value={reason}
          disabled={mutation.isPending}
          onChange={(event) => setReason(event.target.value)}
          placeholder={
            activating ? 'Why is access being restored?' : 'Why is access being revoked?'
          }
          aria-invalid={Boolean(reasonError) || undefined}
          aria-describedby={[`${reasonId}-hint`, reasonError ? `${reasonId}-err` : null]
            .filter(Boolean)
            .join(' ')}
        />
        <p id={`${reasonId}-hint`} className="text-small text-muted">
          Required. Recorded in the audit log.
        </p>
        {reasonError ? (
          <p id={`${reasonId}-err`} role="alert" className="text-small text-crit">
            {reasonError}
          </p>
        ) : null}
      </div>
      {serverError ? (
        <p
          role="alert"
          className="border-crit/40 mt-3 rounded border bg-crit-soft px-3 py-2 text-small text-crit"
        >
          {serverError}
        </p>
      ) : null}
    </ConfirmDialog>
  );
}
