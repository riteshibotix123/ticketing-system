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
import { usersApi, type RoleUpdatePayload } from '@/api/endpoints/users';
import { queryKeys } from '@/api/queryKeys';
import { useToast } from '@/hooks/useToast';
import { reasonSchema } from '@/lib/zod-schemas';
import type { Role, User } from '@/types/domain';

/**
 * Assign/remove Spoke (per department, with confidential authorisation) and
 * Resolver. Every change needs a reason and is audit logged (spec 9.12).
 */
export function RolesDialog({
  user,
  open,
  onOpenChange,
}: {
  user: User;
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
  const [confidential, setConfidential] = useState<string[]>(() => user.confidential_departments);
  const [resolver, setResolver] = useState<boolean>(() => user.roles.includes('resolver'));
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const add: Role[] = [];
  const remove: Role[] = [];
  if (resolver && !user.roles.includes('resolver')) add.push('resolver');
  if (!resolver && user.roles.includes('resolver')) remove.push('resolver');
  const isSpoke = spokeDepartments.length > 0;
  if (isSpoke && !user.roles.includes('spoke')) add.push('spoke');
  if (!isSpoke && user.roles.includes('spoke')) remove.push('spoke');

  const sameSet = (a: string[], b: string[]) =>
    a.length === b.length && a.every((id) => b.includes(id));
  const dirty =
    add.length > 0 ||
    remove.length > 0 ||
    !sameSet(spokeDepartments, user.spoke_departments) ||
    !sameSet(confidential, user.confidential_departments);

  const mutation = useMutation({
    mutationFn: (payload: RoleUpdatePayload) => usersApi.updateRoles(user.id, payload),
    onSuccess: () => {
      success('Roles updated. The change is audit logged.');
      void queryClient.invalidateQueries({ queryKey: ['users'] });
      void queryClient.invalidateQueries({ queryKey: ['signup-requests'] });
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
    if (!checked) {
      setConfidential((prev) => prev.filter((id) => id !== departmentId));
    }
  };

  const toggleConfidential = (departmentId: string, checked: boolean) => {
    setConfidential((prev) =>
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
    mutation.mutate({
      add,
      remove,
      department_ids: spokeDepartments,
      confidential_departments: confidential.filter((id) => spokeDepartments.includes(id)),
      reason: parsed.data.reason,
    });
  };

  return (
    <Dialog open={open} onOpenChange={(value) => !mutation.isPending && onOpenChange(value)}>
      <DialogContent className="w-[min(640px,calc(100vw-32px))]">
        <DialogHeader>
          <DialogTitle>Manage roles</DialogTitle>
          <DialogDescription>
            {user.name} · {user.email}. Every change needs a reason and is audit logged.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <section aria-labelledby={`${uid}-spoke-heading`}>
            <h3 id={`${uid}-spoke-heading`} className="label-caps">
              Spoke assignments
            </h3>
            <p className="mt-1 text-small text-muted">
              Confidential authorisation lets the Spoke open confidential tickets in that
              department.
            </p>
            {departmentsLoading ? (
              <p className="mt-2 text-small text-muted">Loading departments…</p>
            ) : (departments ?? []).length === 0 ? (
              <p className="mt-2 text-small text-muted">No departments found.</p>
            ) : (
              <ul className="mt-2 flex flex-col gap-1.5">
                {(departments ?? []).map((department) => {
                  const spokeId = `${uid}-spoke-${department.id}`;
                  const confidentialId = `${uid}-conf-${department.id}`;
                  const checked = spokeDepartments.includes(department.id);
                  return (
                    <li key={department.id} className="rounded border border-line px-3 py-2">
                      <div className="flex items-center gap-2">
                        <Checkbox
                          id={spokeId}
                          checked={checked}
                          disabled={mutation.isPending}
                          onCheckedChange={(value) => toggleSpoke(department.id, value === true)}
                        />
                        <label htmlFor={spokeId} className="cursor-pointer text-body text-fg">
                          {department.name}
                        </label>
                      </div>
                      {checked ? (
                        <div className="mt-1.5 flex items-center gap-2 pl-6">
                          <Checkbox
                            id={confidentialId}
                            checked={confidential.includes(department.id)}
                            disabled={mutation.isPending}
                            onCheckedChange={(value) =>
                              toggleConfidential(department.id, value === true)
                            }
                          />
                          <label
                            htmlFor={confidentialId}
                            className="cursor-pointer text-small text-muted"
                          >
                            Confidential authorised
                          </label>
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section aria-labelledby={`${uid}-resolver-heading`}>
            <h3 id={`${uid}-resolver-heading`} className="label-caps">
              Resolver
            </h3>
            <div className="mt-2 flex items-center gap-2">
              <Checkbox
                id={`${uid}-resolver`}
                checked={resolver}
                disabled={mutation.isPending}
                onCheckedChange={(value) => setResolver(value === true)}
              />
              <label htmlFor={`${uid}-resolver`} className="cursor-pointer text-body text-fg">
                Resolver role
              </label>
            </div>
            <p className="mt-1 text-small text-muted">
              Resolvers work on tickets assigned to them or shared with them.
            </p>
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
              placeholder="Why are you changing these roles?"
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
