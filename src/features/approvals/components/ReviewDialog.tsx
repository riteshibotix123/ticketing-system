import { useId, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { errorMessage, isApiError } from '@/api/client';
import { departmentsApi } from '@/api/endpoints/departments';
import { usersApi } from '@/api/endpoints/users';
import { queryKeys } from '@/api/queryKeys';
import { usePermissions } from '@/hooks/usePermissions';
import { useToast } from '@/hooks/useToast';
import { ROLE_LABEL } from '@/lib/constants';
import {
  approveSignupSchema,
  rejectSignupSchema,
  type ApproveSignupInput,
  type RejectSignupInput,
} from '@/lib/zod-schemas';
import type { Role, SignupRequest } from '@/types/domain';

const fieldLabel = (id: string, text: string) => (
  <label htmlFor={id} className="text-small font-medium text-fg">
    {text}
    <span aria-hidden="true" className="ml-1 text-crit">
      *
    </span>
  </label>
);

const fieldError = (id: string, message?: string) =>
  message ? (
    <p id={`${id}-err`} role="alert" className="text-small text-crit">
      {message}
    </p>
  ) : null;

const serverAlert = (message: string | null) =>
  message ? (
    <p
      role="alert"
      className="border-crit/40 rounded border bg-crit-soft px-3 py-2 text-small text-crit"
    >
      {message}
    </p>
  ) : null;

/**
 * Approve or reject one signup request (spec 9.11). Approve offers only the
 * roles the viewer can grant; Reject reveals a required reason. The parent
 * mounts this with `key={request.id}` so every open starts clean.
 */
export function ReviewDialog({
  request,
  open,
  onOpenChange,
}: {
  request: SignupRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const permissions = usePermissions();
  const { success } = useToast();
  const queryClient = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const roleId = useId();
  const departmentId = useId();
  const reasonId = useId();

  const { data: departments } = useQuery({
    queryKey: queryKeys.departments,
    queryFn: departmentsApi.list,
    staleTime: 60_000,
  });

  const grantable = permissions.grantableRoles;
  const {
    watch,
    setValue,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<ApproveSignupInput>({
    resolver: zodResolver(approveSignupSchema),
    defaultValues: {
      approved_role: grantable.includes(request.requested_role)
        ? request.requested_role
        : (grantable[0] ?? 'employee'),
      approved_department: request.requested_department,
    },
  });
  const {
    register: registerReason,
    handleSubmit: handleRejectSubmit,
    setError: setRejectError,
    formState: { errors: rejectErrors },
  } = useForm<RejectSignupInput>({
    resolver: zodResolver(rejectSignupSchema),
    defaultValues: { reason: '' },
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['signup-requests'] });
    void queryClient.invalidateQueries({ queryKey: queryKeys.pendingSignupCount });
    void queryClient.invalidateQueries({ queryKey: ['users'] });
  };

  const approveMutation = useMutation({
    mutationFn: (input: ApproveSignupInput) => usersApi.approve(request.id, input),
    onSuccess: () => {
      success('Access request approved.');
      invalidate();
      onOpenChange(false);
    },
    onError: (error) => {
      if (isApiError(error) && error.fields) {
        for (const [field, message] of Object.entries(error.fields)) {
          if (field === 'approved_role' || field === 'approved_department') {
            setError(field, { message });
          }
        }
      }
      setServerError(errorMessage(error));
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (input: RejectSignupInput) => usersApi.reject(request.id, input.reason),
    onSuccess: () => {
      success('Access request rejected.');
      invalidate();
      onOpenChange(false);
    },
    onError: (error) => {
      if (isApiError(error) && error.fields?.reason)
        setRejectError('reason', { message: error.fields.reason });
      setServerError(errorMessage(error));
    },
  });

  const pending = approveMutation.isPending || rejectMutation.isPending;
  const close = (value: boolean) => {
    if (!pending) onOpenChange(value);
  };
  const switchMode = (next: 'review' | 'reject') => {
    setRejecting(next === 'reject');
    setServerError(null);
  };
  const onApprove = handleSubmit((input) => approveMutation.mutate(input));
  const onReject = handleRejectSubmit((input) => rejectMutation.mutate(input));

  const requestedDepartmentLabel =
    departments?.find((d) => d.id === request.requested_department)?.name ??
    request.requested_department;
  const departmentOptions = (departments ?? []).map((d) => ({ value: d.id, label: d.name }));
  if (!departmentOptions.some((option) => option.value === request.requested_department)) {
    departmentOptions.push({
      value: request.requested_department,
      label: requestedDepartmentLabel,
    });
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Review access request</DialogTitle>
          <DialogDescription>{`${request.name} · ${request.email}`}</DialogDescription>
        </DialogHeader>

        <div className="mb-4 flex flex-wrap items-center gap-1.5">
          <Badge variant="accent">Requested {ROLE_LABEL[request.requested_role]}</Badge>
          <Badge variant="outline">{requestedDepartmentLabel}</Badge>
        </div>

        {!rejecting ? (
          <form onSubmit={onApprove} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              {fieldLabel(roleId, 'Approve as role')}
              <Select
                value={watch('approved_role')}
                onValueChange={(value) =>
                  setValue('approved_role', value as Role, { shouldValidate: true })
                }
              >
                <SelectTrigger
                  id={roleId}
                  aria-invalid={Boolean(errors.approved_role) || undefined}
                >
                  <SelectValue placeholder="Pick a role" />
                </SelectTrigger>
                <SelectContent>
                  {grantable.map((role) => (
                    <SelectItem key={role} value={role}>
                      {ROLE_LABEL[role]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-small text-muted">Only roles you can grant are listed.</p>
              {fieldError(roleId, errors.approved_role?.message)}
            </div>

            <div className="flex flex-col gap-1.5">
              {fieldLabel(departmentId, 'Confirm department')}
              <Select
                value={watch('approved_department')}
                disabled={!departments}
                onValueChange={(value) =>
                  setValue('approved_department', value, { shouldValidate: true })
                }
              >
                <SelectTrigger
                  id={departmentId}
                  aria-invalid={Boolean(errors.approved_department) || undefined}
                >
                  <SelectValue
                    placeholder={departments ? 'Pick a department' : 'Loading departments…'}
                  />
                </SelectTrigger>
                <SelectContent>
                  {departmentOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-small text-muted">
                Requested {requestedDepartmentLabel}. Confirm or change it.
              </p>
              {fieldError(departmentId, errors.approved_department?.message)}
            </div>

            {serverAlert(serverError)}

            <DialogFooter>
              <Button
                type="button"
                variant="outlineDanger"
                disabled={pending}
                onClick={() => switchMode('reject')}
              >
                Reject
              </Button>
              <Button type="submit" variant="primary" loading={approveMutation.isPending}>
                Approve
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <form onSubmit={onReject} className="flex flex-col gap-4">
            <p className="text-small text-muted">
              The applicant is emailed your reason. The decision is audit logged.
            </p>
            <div className="flex flex-col gap-1.5">
              {fieldLabel(reasonId, 'Rejection reason')}
              <Textarea
                id={reasonId}
                rows={3}
                placeholder="Explain why this request is not approved."
                aria-invalid={Boolean(rejectErrors.reason) || undefined}
                {...registerReason('reason')}
              />
              {fieldError(reasonId, rejectErrors.reason?.message)}
            </div>

            {serverAlert(serverError)}

            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                disabled={pending}
                onClick={() => switchMode('review')}
              >
                Back
              </Button>
              <Button type="submit" variant="danger" loading={rejectMutation.isPending}>
                Reject request
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
