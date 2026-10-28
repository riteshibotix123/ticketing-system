import { useId, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { errorMessage, isApiError } from '@/api/client';
import { departmentsApi } from '@/api/endpoints/departments';
import { usersApi } from '@/api/endpoints/users';
import { queryKeys } from '@/api/queryKeys';
import { useToast } from '@/hooks/useToast';
import { reasonSchema } from '@/lib/zod-schemas';
import type { UserListItem } from '@/types/domain';

export function RolesDialog({
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
  const uid = useId();

  const { data: departments, isLoading: departmentsLoading } = useQuery({
    queryKey: queryKeys.departments,
    queryFn: departmentsApi.list,
    staleTime: 60_000,
  });

  const [spokeDepartments, setSpokeDepartments] = useState<string[]>(() => user.spoke_departments);
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const sameSet = (a: string[], b: string[]) =>
    a.length === b.length && a.every((id) => b.includes(id));
  const dirty = !sameSet(spokeDepartments, user.spoke_departments);

  const mutation = useMutation({
    mutationFn: (payload: { spoke_departments: string[]; reason: string }) =>
      usersApi.updateRoles(user.id, payload),
    onSuccess: () => {
      success('Spoke departments updated.');
      void queryClient.invalidateQueries({ queryKey: ['users'] });
      void queryClient.invalidateQueries({ queryKey: ['signup-requests'] });
      void queryClient.invalidateQueries({ queryKey: ['departments'] });
      onOpenChange(false);
    },
    onError: (error) => {
      if (isApiError(error) && error.fields?.reason) setReasonError(error.fields.reason);
      setServerError(errorMessage(error));
    },
  });

  const toggleSpoke = (departmentId: string, checked: boolean) => {
    setSpokeDepartments((prev) =>
      checked ? [...prev, departmentId] : prev.filter((id) => id !== departmentId),
    );
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsed = reasonSchema.safeParse({ reason });
    if (!parsed.success) {
      setReasonError(parsed.error.issues[0]?.message ?? 'Required.');
      return;
    }
    setReasonError(null);
    mutation.mutate({ spoke_departments: spokeDepartments, reason: parsed.data.reason });
  };

  return (
    <Dialog open={open} onOpenChange={(value) => !mutation.isPending && onOpenChange(value)}>
      <DialogContent className="w-[min(640px,calc(100vw-32px))]">
        <DialogHeader>
          <DialogTitle>Manage Spoke departments</DialogTitle>
          <DialogDescription>
            {user.name} · {user.email}. Every change needs a reason and is audit logged.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <section aria-labelledby={`${uid}-spoke-heading`}>
            <h3 id={`${uid}-spoke-heading`} className="label-caps">
              Spoke departments
            </h3>
            <p className="mt-1 text-small text-muted">
              A Spoke covers every department ticked here. Confidential access is granted
              separately, per category.
            </p>
            {departmentsLoading ? (
              <p className="mt-2 text-small text-muted">Loading departments…</p>
            ) : (departments ?? []).length === 0 ? (
              <p className="mt-2 text-small text-muted">No departments found.</p>
            ) : (
              <ul className="mt-2 flex flex-col gap-1.5">
                {(departments ?? []).map((department) => {
                  const spokeId = `${uid}-spoke-${department.id}`;
                  return (
                    <li key={department.id} className="rounded border border-line px-3 py-2">
                      <div className="flex items-center gap-2">
                        <Checkbox
                          id={spokeId}
                          checked={spokeDepartments.includes(department.id)}
                          disabled={mutation.isPending}
                          onCheckedChange={(value) => toggleSpoke(department.id, value === true)}
                        />
                        <label htmlFor={spokeId} className="cursor-pointer text-body text-fg">
                          {department.name}
                        </label>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${uid}-reason`} className="text-small font-medium text-fg">
              Reason
              <span aria-hidden="true" className="ml-1 text-crit">
                *
              </span>
            </label>
            <Textarea
              id={`${uid}-reason`}
              rows={2}
              value={reason}
              disabled={mutation.isPending}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Why are you changing these Spoke departments?"
              aria-invalid={Boolean(reasonError) || undefined}
              aria-describedby={`${uid}-reason-hint`}
            />
            <p id={`${uid}-reason-hint`} className="text-small text-muted">
              Required. Recorded in the audit log.
            </p>
            {reasonError ? (
              <p role="alert" className="text-small text-crit">
                {reasonError}
              </p>
            ) : null}
          </div>

          {serverError ? (
            <p
              role="alert"
              className="border-crit/40 rounded border bg-crit-soft px-3 py-2 text-small text-crit"
            >
              {serverError}
            </p>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              disabled={mutation.isPending}
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              loading={mutation.isPending}
              disabled={!dirty}
              loadingLabel="Saving"
            >
              Save changes
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
