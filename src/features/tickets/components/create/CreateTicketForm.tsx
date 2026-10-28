import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { errorMessage, isApiError } from '@/api/client';
import { departmentsApi } from '@/api/endpoints/departments';
import { ticketsApi, type CreateTicketPayload } from '@/api/endpoints/tickets';
import { queryKeys } from '@/api/queryKeys';
import { FormField } from '@/components/common/FormField';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { MAX_DESCRIPTION_LENGTH, MAX_TITLE_LENGTH } from '@/lib/constants';
import { useToast } from '@/hooks/useToast';
import { createTicketSchema, type CreateTicketInput } from '@/lib/zod-schemas';
import { AttachmentUploader } from './AttachmentUploader';
import { CategorySelect } from './CategorySelect';
import { DepartmentSelect } from './DepartmentSelect';
import { PriorityPicker } from './PriorityPicker';
import { clearDraft, readDraft, saveDraft } from './ticketDraft';

const CONFIDENTIAL_HELP =
  'Only you, the assignee and authorised leads can open it. Emails show no details.';

export function CreateTicketForm() {
  const navigate = useNavigate();
  const { success, error: errorToast } = useToast();
  const queryClient = useQueryClient();
  const [serverError, setServerError] = useState<string | null>(null);
  const [attachmentIds, setAttachmentIds] = useState<string[]>([]);
  const [uploadsPending, setUploadsPending] = useState(false);

  const departmentsQuery = useQuery({
    queryKey: queryKeys.departments,
    queryFn: () => departmentsApi.list(),
  });
  const departments = useMemo(() => departmentsQuery.data ?? [], [departmentsQuery.data]);
  // Fallback 24 only if the policy call itself fails (spec 11.2 default).
  const policyQuery = useQuery({
    queryKey: queryKeys.policy,
    queryFn: () => departmentsApi.policy(),
    retry: false,
  });
  const responseHours = policyQuery.data?.initial_response_hours ?? 24;

  const draft = useMemo(() => readDraft(), []);
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<CreateTicketInput>({
    resolver: zodResolver(createTicketSchema),
    defaultValues: {
      department_id: draft?.department_id ?? '',
      category_id: draft?.category_id ?? '',
      title: draft?.title ?? '',
      description: draft?.description ?? '',
      priority: draft?.priority ?? 'medium',
      confidential: draft?.confidential ?? false,
    },
  });

  // Draft persistence (spec 9.5): save on change, cleared after successful submit.
  useEffect(() => {
    const subscription = watch((values) => saveDraft(values));
    return () => subscription.unsubscribe();
  }, [watch]);

  const departmentId = watch('department_id');
  const categoryId = watch('category_id');
  const priority = watch('priority');
  const confidential = watch('confidential');
  const title = watch('title');
  const description = watch('description');

  const selectedDepartment = departments.find((d) => d.id === departmentId) ?? null;
  const categories = (selectedDepartment?.categories ?? []).filter((category) => category.active);
  const selectedCategory = categories.find((category) => category.id === categoryId) ?? null;
  const confidentialAllowed = Boolean(selectedCategory?.confidential);

  const pickCategory = (id: string) => {
    setValue('category_id', id, { shouldValidate: true });
    const category = categories.find((item) => item.id === id) ?? null;
    setValue('confidential', Boolean(category?.confidential));
  };

  // Changing department clears the now-invalid category and confidential flag.
  // A ref guard skips the first run so a restored draft survives the mount.
  const prevDepartmentId = useRef(departmentId);
  useEffect(() => {
    if (prevDepartmentId.current === departmentId) return;
    prevDepartmentId.current = departmentId;
    setValue('category_id', '');
    setValue('confidential', false);
  }, [departmentId, setValue]);

  const createMutation = useMutation({
    mutationFn: (payload: CreateTicketPayload) => ticketsApi.create(payload),
  });

  const onSubmit = handleSubmit(async (values) => {
    setServerError(null);
    try {
      const ticket = await createMutation.mutateAsync({
        department_id: values.department_id,
        category_id: values.category_id,
        title: values.title,
        description: values.description,
        priority: values.priority,
        confidential: values.confidential,
        attachment_ids: attachmentIds.length > 0 ? attachmentIds : undefined,
      });
      clearDraft();
      void queryClient.invalidateQueries({ queryKey: ['tickets'] });
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      success(
        `Ticket ${ticket.id} created. A first response is due within ${responseHours} hours.`,
      );
      navigate(`/tickets/${ticket.id}`);
    } catch (err) {
      if (isApiError(err)) {
        if (err.status === 403) {
          setServerError(err.message);
          return;
        }
        if (err.fields) {
          for (const [field, message] of Object.entries(err.fields)) {
            setError(field as keyof CreateTicketInput, { message });
          }
          return;
        }
      }
      errorToast('Could not create the ticket.', errorMessage(err));
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {serverError ? (
        <div
          role="alert"
          className="border-crit/50 rounded border bg-crit-soft px-3 py-2 text-small text-crit"
        >
          {serverError}
        </div>
      ) : null}

      <FormField label="Department" required error={errors.department_id?.message}>
        <DepartmentSelect
          value={departmentId}
          onChange={(id) => setValue('department_id', id, { shouldValidate: true })}
          departments={departments}
        />
      </FormField>

      <FormField
        label="Category"
        required
        error={errors.category_id?.message}
        hint={selectedDepartment ? undefined : 'Choose a department first.'}
      >
        <CategorySelect
          value={categoryId ?? ''}
          onChange={pickCategory}
          categories={categories}
          disabled={!selectedDepartment}
        />
      </FormField>

      <FormField label="Title" required error={errors.title?.message}>
        <div className="flex items-center gap-2">
          <Input
            placeholder="Short summary of the problem"
            aria-invalid={Boolean(errors.title)}
            {...register('title')}
          />
          <span className="tabular shrink-0 text-small text-muted" aria-hidden="true">
            {title.length}/{MAX_TITLE_LENGTH}
          </span>
        </div>
      </FormField>

      <FormField label="Description" required error={errors.description?.message}>
        <div className="flex flex-col gap-1">
          <Textarea
            rows={6}
            placeholder="What happened, what you expected, and any steps to reproduce."
            aria-invalid={Boolean(errors.description)}
            {...register('description')}
          />
          <span className="tabular self-end text-small text-muted" aria-hidden="true">
            {description.length}/{MAX_DESCRIPTION_LENGTH}
          </span>
        </div>
      </FormField>

      <FormField label="Priority" required error={errors.priority?.message}>
        <PriorityPicker
          value={priority}
          onChange={(p) => setValue('priority', p, { shouldValidate: true })}
        />
      </FormField>

      <FormField label="Attachments" hint="Optional. Screenshots or log files help the team.">
        <AttachmentUploader onIdsChange={setAttachmentIds} onPendingChange={setUploadsPending} />
      </FormField>

      {confidentialAllowed ? (
        <FormField label="Confidential" hint={CONFIDENTIAL_HELP}>
          <span className="flex w-fit items-center gap-2">
            <Checkbox id="ct-confidential" checked={confidential} disabled />
            <label htmlFor="ct-confidential" className="text-body text-fg">
              This category is confidential
            </label>
          </span>
        </FormField>
      ) : null}

      <div className="flex items-center gap-3">
        <Button
          type="submit"
          variant="primary"
          loading={isSubmitting || uploadsPending}
          loadingLabel="Creating"
        >
          Create ticket
        </Button>
        {uploadsPending ? (
          <span role="status" className="inline-flex items-center gap-1.5 text-small text-muted">
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
            Waiting for attachments to finish uploading.
          </span>
        ) : null}
      </div>
    </form>
  );
}
