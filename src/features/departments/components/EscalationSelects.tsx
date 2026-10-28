import { useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { departmentsApi } from '@/api/endpoints/departments';
import { queryKeys } from '@/api/queryKeys';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/useToast';
import { UserSelect, mergeUserOptions } from './UserSelect';
import type { Department, UserRef } from '@/types/domain';

/**
 * Primary and backup escalation contacts as searchable selects (spec 9.13).
 * Saving calls PUT /departments/{id}/escalation with both ids.
 */
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
  const initialPrimary = department.escalation_primary?.id ?? null;
  const initialBackup = department.escalation_backup?.id ?? null;
  const [primaryId, setPrimaryId] = useState<string | null>(initialPrimary);
  const [backupId, setBackupId] = useState<string | null>(initialBackup);
  const [serverError, setServerError] = useState<string | null>(null);

  const options = useMemo(
    () =>
      mergeUserOptions(candidates, [department.escalation_primary, department.escalation_backup]),
    [candidates, department],
  );

  const dirty = primaryId !== initialPrimary || backupId !== initialBackup;

  const save = useMutation({
    mutationFn: () => departmentsApi.setEscalation(department.id, primaryId, backupId),
    onSuccess: () => {
      success('Escalation contacts updated.');
      void qc.invalidateQueries({ queryKey: queryKeys.departments });
      // L2 escalations email the primary contact — ticket caches may change.
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
      <div className="flex flex-col gap-0.5 text-small">
        <span className="text-fg">
          {department.escalation_primary?.name ?? 'No primary contact.'}
        </span>
        <span className="text-muted">
          {department.escalation_backup
            ? `Backup: ${department.escalation_backup.name}`
            : 'No backup contact.'}
        </span>
      </div>
    );
  }

  return (
    <div className="flex min-w-[210px] flex-col gap-1.5">
      <div>
        <span className="label-caps block text-muted">Primary</span>
        <UserSelect
          label="Primary escalation contact"
          value={primaryId}
          onChange={setPrimaryId}
          options={options}
          placeholder="No primary"
          allowClear
          disabled={save.isPending}
        />
      </div>
      <div>
        <span className="label-caps block text-muted">Backup</span>
        <UserSelect
          label="Backup escalation contact"
          value={backupId}
          onChange={setBackupId}
          options={options}
          placeholder="No backup"
          allowClear
          disabled={save.isPending}
        />
      </div>
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
          Save contacts
        </Button>
      ) : null}
    </div>
  );
}
