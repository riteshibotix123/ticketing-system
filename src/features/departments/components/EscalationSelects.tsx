import { useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { departmentsApi } from '@/api/endpoints/departments';
import { queryKeys } from '@/api/queryKeys';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/useToast';
import { UserSelect, mergeUserOptions } from './UserSelect';
import type { Department, UserRef } from '@/types/domain';

export function EscalationSelects({
  department,
  candidates,
  editable,
}: {
  department: Department;
  candidates: UserRef[];
  editable: boolean;
}) {
  const { success, error: errorToast } = useToast();
  const qc = useQueryClient();
  const initialContact = department.escalation_contact?.id ?? null;
  const [contactId, setContactId] = useState<string | null>(initialContact);
  const [serverError, setServerError] = useState<string | null>(null);

  const options = useMemo(
    () => mergeUserOptions(candidates, [department.escalation_contact]),
    [candidates, department],
  );

  const dirty = contactId !== initialContact;

  const save = useMutation({
    mutationFn: () => departmentsApi.setEscalation(department.id, contactId),
    onSuccess: () => {
      success('Escalation contact updated.');
      void qc.invalidateQueries({ queryKey: queryKeys.departments });
      void qc.invalidateQueries({ queryKey: ['tickets'] });
      setServerError(null);
    },
    onError: (err) => {
      setServerError(errorMessage(err));
      errorToast(errorMessage(err));
    },
  });

  if (!editable) {
    return (
      <span className="text-small text-fg">
        {department.escalation_contact?.name ?? 'No escalation contact.'}
      </span>
    );
  }

  return (
    <div className="flex min-w-[210px] flex-col gap-1.5">
      <span className="label-caps block text-muted">Escalation contact</span>
      <UserSelect
        label="Escalation contact"
        value={contactId}
        onChange={setContactId}
        options={options}
        placeholder="No contact"
        allowClear
        disabled={save.isPending}
      />
      <p className="text-small text-muted">One contact per department. They receive L2.</p>
      {serverError ? (
        <p role="alert" className="text-small text-crit">
          {serverError}
        </p>
      ) : null}
      {dirty ? (
        <Button
          size="sm"
          className="self-start"
          onClick={() => {
            setServerError(null);
            save.mutate();
          }}
          loading={save.isPending}
          loadingLabel="Saving"
        >
          Save contact
        </Button>
      ) : null}
    </div>
  );
}
