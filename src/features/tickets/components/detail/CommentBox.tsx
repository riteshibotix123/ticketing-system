import { useId, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { errorMessage, isApiError } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import { ticketsApi } from '@/api/endpoints/tickets';
import { commentSchema, type CommentInput } from '@/lib/zod-schemas';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Textarea } from '@/components/ui/textarea';
import { usePermissions } from '@/hooks/usePermissions';
import { useToast } from '@/hooks/useToast';
import type { Ticket } from '@/types/domain';

/**
 * Spec 9.9 comment box. Staff get an "Internal note" checkbox (label expands
 * when checked, submit becomes "Add note"); requesters just post. Hidden on
 * closed and cancelled tickets — reopen is the only action there.
 */
export function CommentBox({ ticket }: { ticket: Ticket }) {
  const { can, isStaff } = usePermissions();
  const canNote = can('tickets.internal_notes');
  const toast = useToast();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const bodyId = useId();
  const noteId = useId();

  const {
    register,
    handleSubmit,
    setError,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<CommentInput>({
    resolver: zodResolver(commentSchema),
    defaultValues: { body: '', internal: false },
  });
  const internal = watch('internal');

  if (ticket.status === 'closed' || ticket.status === 'cancelled') return null;

  const onSubmit = handleSubmit(async (values) => {
    setPending(true);
    setServerError(null);
    try {
      await ticketsApi.comment(ticket.id, values.body, values.internal);
      if (values.internal) {
        toast.success('Internal note added. The requester cannot see it.');
      } else {
        toast.success('Comment posted.');
      }
      reset({ body: '', internal: values.internal });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.ticket(ticket.id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.timeline(ticket.id) }),
        queryClient.invalidateQueries({ queryKey: ['tickets'] }),
      ]);
    } catch (err) {
      if (isApiError(err)) {
        if (err.status === 409) {
          toast.error('This ticket changed. Refreshed with the latest version.');
          void queryClient.invalidateQueries({ queryKey: queryKeys.ticket(ticket.id) });
        } else if (err.fields?.body) {
          setError('body', { type: 'server', message: err.fields.body });
        } else {
          setServerError(err.message);
        }
      } else {
        setServerError(errorMessage(err));
      }
    } finally {
      setPending(false);
    }
  });

  return (
    <section className="card p-4">
      <h2 className="text-section-title text-fg">Add a comment</h2>
      <form noValidate className="mt-3 flex flex-col gap-3" onSubmit={onSubmit}>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={bodyId} className="text-small font-medium text-fg">
            {isStaff ? 'Comment' : 'Add a comment'}
          </label>
          <Textarea
            id={bodyId}
            rows={4}
            aria-invalid={Boolean(errors.body) || undefined}
            aria-describedby={errors.body ? `${bodyId}-error` : undefined}
            placeholder={internal ? 'Only staff can see this note.' : 'Write your message…'}
            {...register('body')}
          />
          {errors.body ? (
            <p id={`${bodyId}-error`} role="alert" className="text-small text-crit">
              {errors.body.message}
            </p>
          ) : null}
        </div>

        {canNote ? (
          <label
            htmlFor={noteId}
            className={
              internal
                ? 'flex items-center gap-2 text-body text-warn'
                : 'flex items-center gap-2 text-body text-fg'
            }
          >
            <Checkbox
              id={noteId}
              checked={internal}
              onCheckedChange={(checked) => setValue('internal', checked === true)}
            />
            {internal ? 'Internal note (hidden from requester)' : 'Internal note'}
          </label>
        ) : null}

        {serverError ? (
          <div
            role="alert"
            className="border-crit/40 rounded border bg-crit-soft px-3 py-2 text-small text-crit"
          >
            {serverError}
          </div>
        ) : null}

        <div className="flex justify-end">
          <Button type="submit" variant="primary" loading={pending}>
            {canNote && internal ? 'Add note' : 'Post'}
          </Button>
        </div>
      </form>
    </section>
  );
}
