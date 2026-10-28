import { useId, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { errorMessage, isApiError } from '@/api/client';
import { departmentsApi } from '@/api/endpoints/departments';
import { queryKeys } from '@/api/queryKeys';
import { FormField } from '@/components/common/FormField';
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
import { Input } from '@/components/ui/input';
import { useToast } from '@/hooks/useToast';
import { departmentFormSchema, type DepartmentFormInput } from '@/lib/zod-schemas';
import type { Department } from '@/types/domain';

/** Rule 10.3: a department cannot be active without at least one active Spoke. */
export const SPOKE_RULE_MESSAGE =
  'Add at least one active Spoke before activating this department.';

/** Create / edit a department (name, active, confidential) — spec 9.13. */
export function DepartmentDialog({
  department,
  open,
  onOpenChange,
}: {
  /** null → create mode. */
  department: Department | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { success } = useToast();
  const qc = useQueryClient();
  const activeId = useId();
  const confidentialId = useId();
  const [serverError, setServerError] = useState<string | null>(null);

  const { register, handleSubmit, watch, setValue, setError, formState } =
    useForm<DepartmentFormInput>({
      resolver: zodResolver(departmentFormSchema),
      defaultValues: department
        ? {
            name: department.name,
            active: department.active,
            confidential: department.confidential,
          }
        : { name: '', active: false, confidential: false },
    });

  const spokeCount = department?.spokes.length ?? 0;
  const activeValue = watch('active');
  const confidentialValue = watch('confidential');
  const violatesSpokeRule = activeValue && spokeCount === 0;
  const activeError =
    formState.errors.active?.message ?? (violatesSpokeRule ? SPOKE_RULE_MESSAGE : undefined);

  const mutation = useMutation({
    mutationFn: (values: DepartmentFormInput) =>
      department ? departmentsApi.update(department.id, values) : departmentsApi.create(values),
    onSuccess: () => {
      success('Department saved.');
      void qc.invalidateQueries({ queryKey: queryKeys.departments });
      onOpenChange(false);
    },
    onError: (err) => {
      setServerError(errorMessage(err));
      if (isApiError(err) && err.fields) {
        for (const [key, message] of Object.entries(err.fields)) {
          if (key === 'name' || key === 'active' || key === 'confidential') {
            setError(key, { message });
          }
        }
      }
    },
  });

  const onSubmit = (values: DepartmentFormInput) => {
    if (values.active && spokeCount === 0) {
      setError('active', { message: SPOKE_RULE_MESSAGE });
      return;
    }
    mutation.mutate(values);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!mutation.isPending) onOpenChange(v);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{department ? 'Edit department' : 'New department'}</DialogTitle>
          <DialogDescription>
            {department
              ? 'Update the department details.'
              : 'Create a department. It starts inactive until it has a Spoke.'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
          <FormField label="Name" required error={formState.errors.name?.message}>
            <Input
              {...register('name')}
              placeholder="e.g. IT"
              maxLength={80}
              disabled={mutation.isPending}
              aria-invalid={formState.errors.name ? true : undefined}
            />
          </FormField>

          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <Checkbox
                id={activeId}
                checked={activeValue}
                onCheckedChange={(v) => setValue('active', v === true)}
                disabled={mutation.isPending}
                aria-invalid={activeError ? true : undefined}
              />
              <label htmlFor={activeId} className="text-small font-medium text-fg">
                Active
              </label>
            </div>
            <p className="text-small text-muted">
              A department needs at least one active Spoke before it can be activated.
            </p>
            {activeError ? (
              <p role="alert" className="text-small text-crit">
                {activeError}
              </p>
            ) : null}
          </div>

          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <Checkbox
                id={confidentialId}
                checked={confidentialValue}
                onCheckedChange={(v) => setValue('confidential', v === true)}
                disabled={mutation.isPending}
              />
              <label htmlFor={confidentialId} className="text-small font-medium text-fg">
                Confidential
              </label>
            </div>
            <p className="text-small text-muted">
              Only authorised leads can open confidential tickets for this department.
            </p>
          </div>

          {serverError ? (
            <p role="alert" className="text-small text-crit">
              {serverError}
            </p>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              loading={mutation.isPending}
              loadingLabel="Saving"
            >
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
