import { useState } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Lock } from 'lucide-react';
import { errorMessage } from '@/api/client';
import { departmentsApi } from '@/api/endpoints/departments';
import { queryKeys } from '@/api/queryKeys';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/hooks/useToast';
import { PRIORITY_LABEL, PRIORITY_ORDER } from '@/lib/constants';
import { policyFormSchema, type PolicyFormInput } from '@/lib/zod-schemas';
import { buildPolicyDiff } from '../lib/policyDiff';
import { NumberField } from './NumberField';
import type { PolicyConfig } from '@/types/domain';

/**
 * Edit form for the global SLA/escalation policy (spec 9.13 + 11.2).
 * Saving shows a diff confirmation and creates a new policy version.
 * Read-only for Admins: fields visible but disabled ("Super Admin only").
 */
export function PolicyForm({ policy, readOnly }: { policy: PolicyConfig; readOnly: boolean }) {
  const { success } = useToast();
  const qc = useQueryClient();
  const [pendingDiff, setPendingDiff] = useState<string[] | null>(null);
  const [pendingNext, setPendingNext] = useState<PolicyConfig | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const { register, handleSubmit, control, formState, reset } = useForm<PolicyFormInput>({
    resolver: zodResolver(policyFormSchema),
    defaultValues: {
      initial_response_hours: policy.initial_response_hours,
      update_cadence_hours: policy.update_cadence_hours,
      requester_reminder_hours: policy.requester_reminder_hours,
      auto_close_business_days: policy.auto_close_business_days,
      sla_mode: policy.sla_mode,
      warning_hours: { ...policy.warning_hours },
      l3_hours: { ...policy.l3_hours },
    },
  });

  const mutation = useMutation({
    mutationFn: (next: PolicyConfig) => departmentsApi.updatePolicy(next),
    onSuccess: (saved) => {
      success('Policy saved. A new policy version was created.');
      void qc.invalidateQueries({ queryKey: queryKeys.policy });
      setPendingDiff(null);
      setPendingNext(null);
      setServerError(null);
      reset({
        initial_response_hours: saved.initial_response_hours,
        update_cadence_hours: saved.update_cadence_hours,
        requester_reminder_hours: saved.requester_reminder_hours,
        auto_close_business_days: saved.auto_close_business_days,
        sla_mode: saved.sla_mode,
        warning_hours: { ...saved.warning_hours },
        l3_hours: { ...saved.l3_hours },
      });
    },
    onError: (err) => {
      setServerError(errorMessage(err));
      setPendingDiff(null);
      setPendingNext(null);
    },
  });

  const onSubmit = (values: PolicyFormInput) => {
    setServerError(null);
    const next: PolicyConfig = {
      ...policy,
      ...values,
      warning_hours: { ...values.warning_hours },
      l3_hours: { ...values.l3_hours },
    };
    const diff = buildPolicyDiff(policy, next);
    if (diff.length === 0) return;
    setPendingNext(next);
    setPendingDiff(diff);
  };

  const disabled = readOnly || mutation.isPending;

  return (
    <section className="card p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-section-title text-fg">Edit policy</h2>
        {readOnly ? (
          <Badge variant="outline">
            <Lock className="h-3 w-3" aria-hidden="true" />
            Super Admin only
          </Badge>
        ) : null}
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5">
        <fieldset
          className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2 lg:grid-cols-3"
          disabled={disabled}
        >
          <legend className="label-caps mb-2 text-muted">Organisation</legend>
          <NumberField
            label="Initial response (hours)"
            field={register('initial_response_hours', { valueAsNumber: true })}
            error={formState.errors.initial_response_hours?.message}
            disabled={disabled}
          />
          <NumberField
            label="Update cadence (hours)"
            field={register('update_cadence_hours', { valueAsNumber: true })}
            error={formState.errors.update_cadence_hours?.message}
            disabled={disabled}
          />
          <NumberField
            label="Requester reminder (hours)"
            field={register('requester_reminder_hours', { valueAsNumber: true })}
            error={formState.errors.requester_reminder_hours?.message}
            disabled={disabled}
          />
          <NumberField
            label="Auto-close (days)"
            min={1}
            max={90}
            placeholder="Off"
            hint="Leave empty to never auto-close."
            field={register('auto_close_business_days', {
              setValueAs: (v: string) => (v === '' ? null : Number(v)),
            })}
            error={formState.errors.auto_close_business_days?.message}
            disabled={disabled}
          />
          <div className="flex flex-col gap-1">
            <span className="label-caps text-muted">SLA mode</span>
            <Controller
              control={control}
              name="sla_mode"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange} disabled={disabled}>
                  <SelectTrigger aria-label="SLA mode">
                    <SelectValue placeholder="Mode" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="calendar">Calendar hours</SelectItem>
                    <SelectItem value="business">Business hours</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
            <p className="text-small text-muted">Business-hours mode is not active yet.</p>
          </div>
        </fieldset>

        <fieldset className="grid grid-cols-2 gap-x-4 gap-y-3 md:grid-cols-4" disabled={disabled}>
          <legend className="label-caps mb-2 text-muted">Warning (L1) hours per priority</legend>
          {PRIORITY_ORDER.map((priority) => (
            <NumberField
              key={`warning-${priority}`}
              label={PRIORITY_LABEL[priority]}
              field={register(`warning_hours.${priority}`, { valueAsNumber: true })}
              error={formState.errors.warning_hours?.[priority]?.message}
              disabled={disabled}
            />
          ))}
        </fieldset>

        <fieldset className="grid grid-cols-2 gap-x-4 gap-y-3 md:grid-cols-4" disabled={disabled}>
          <legend className="label-caps mb-2 text-muted">L3 hours per priority</legend>
          {PRIORITY_ORDER.map((priority) => (
            <NumberField
              key={`l3-${priority}`}
              label={PRIORITY_LABEL[priority]}
              field={register(`l3_hours.${priority}`, { valueAsNumber: true })}
              error={formState.errors.l3_hours?.[priority]?.message}
              disabled={disabled}
            />
          ))}
        </fieldset>

        {serverError ? (
          <p role="alert" className="text-small text-crit">
            {serverError}
          </p>
        ) : null}

        {!readOnly ? (
          <div className="flex justify-end gap-2">
            <Button
              type="submit"
              variant="primary"
              loading={mutation.isPending}
              loadingLabel="Saving"
            >
              Save policy
            </Button>
          </div>
        ) : null}
      </form>

      <ConfirmDialog
        open={pendingDiff !== null}
        onOpenChange={(v) => {
          if (!v) {
            setPendingDiff(null);
            setPendingNext(null);
          }
        }}
        title="Confirm policy changes"
        description="Saving creates a new policy version."
        confirmLabel="Save policy"
        loading={mutation.isPending}
        onConfirm={() => {
          if (pendingNext) mutation.mutate(pendingNext);
        }}
      >
        <ul className="flex flex-col gap-1">
          {(pendingDiff ?? []).map((line) => (
            <li key={line} className="mono text-small text-fg">
              {line}
            </li>
          ))}
        </ul>
      </ConfirmDialog>
    </section>
  );
}
