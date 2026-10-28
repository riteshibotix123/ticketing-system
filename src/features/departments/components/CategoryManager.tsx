import { useId, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { errorMessage } from '@/api/client';
import { departmentsApi } from '@/api/endpoints/departments';
import { queryKeys } from '@/api/queryKeys';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { useToast } from '@/hooks/useToast';
import { CategoryRow } from './CategoryRow';
import type { Category, Department } from '@/types/domain';

export function CategoryManager({
  department,
  editable,
}: {
  department: Department;
  editable: boolean;
}) {
  const { success, error: errorToast } = useToast();
  const qc = useQueryClient();
  const confidentialId = useId();
  const [draft, setDraft] = useState('');
  const [confidential, setConfidential] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Category | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.departments });
  };

  const fail = (err: unknown) => {
    setServerError(errorMessage(err));
    errorToast(errorMessage(err));
  };

  const addMutation = useMutation({
    mutationFn: (payload: { name: string; confidential: boolean }) =>
      departmentsApi.addCategory(department.id, payload),
    onSuccess: () => {
      success('Category added.');
      invalidate();
      setDraft('');
      setConfidential(false);
      setServerError(null);
    },
    onError: fail,
  });

  const updateMutation = useMutation({
    mutationFn: (updates: { category: Category; name?: string; confidential?: boolean }) =>
      departmentsApi.updateCategory(updates.category.id, {
        name: updates.name,
        confidential: updates.confidential,
      }),
    onSuccess: () => {
      success('Category updated.');
      invalidate();
      setServerError(null);
    },
    onError: fail,
  });

  const deleteMutation = useMutation({
    mutationFn: (categoryId: string) => departmentsApi.deleteCategory(categoryId),
    onSuccess: () => {
      success('Category removed.');
      invalidate();
      setPendingDelete(null);
      setServerError(null);
    },
    onError: fail,
  });

  const nameTooShort = draft.trim().length > 0 && draft.trim().length < 2;
  const busy = addMutation.isPending || updateMutation.isPending || deleteMutation.isPending;

  return (
    <div className="flex flex-col gap-2">
      <span className="label-caps text-muted">
        Categories — {department.name} ({department.categories.length})
      </span>

      {department.categories.length === 0 ? (
        <p className="text-small text-muted">No categories yet.</p>
      ) : (
        <ul>
          {department.categories.map((category) => (
            <CategoryRow
              key={category.id}
              category={category}
              editable={editable}
              busy={busy}
              onSave={(updates) => updateMutation.mutate({ category, ...updates })}
              onDelete={() => setPendingDelete(category)}
            />
          ))}
        </ul>
      )}

      {editable ? (
        <form
          className="flex flex-wrap items-center gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const name = draft.trim();
            if (name.length < 2) return;
            addMutation.mutate({ name, confidential });
          }}
        >
          <label className="sr-only" htmlFor={`new-category-${department.id}`}>
            New category name
          </label>
          <Input
            id={`new-category-${department.id}`}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="New category name"
            maxLength={80}
            className="h-8 max-w-[240px]"
            aria-invalid={nameTooShort || undefined}
          />
          <div className="flex items-center gap-2">
            <Checkbox
              id={confidentialId}
              checked={confidential}
              onCheckedChange={(value) => setConfidential(value === true)}
            />
            <label htmlFor={confidentialId} className="text-small text-fg">
              Confidential
            </label>
          </div>
          <Button
            type="submit"
            size="sm"
            loading={addMutation.isPending}
            loadingLabel="Adding"
            disabled={draft.trim().length < 2}
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            Add category
          </Button>
        </form>
      ) : null}

      {serverError ? (
        <p role="alert" className="text-small text-crit">
          {serverError}
        </p>
      ) : null}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(v) => {
          if (!v) setPendingDelete(null);
        }}
        title="Remove category?"
        description={
          pendingDelete
            ? `“${pendingDelete.name}” will no longer be selectable on new tickets in ${department.name}.`
            : undefined
        }
        confirmLabel="Remove"
        destructive
        loading={deleteMutation.isPending}
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
        }}
      />
    </div>
  );
}
