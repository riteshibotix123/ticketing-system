import { useEffect, useRef, useState } from 'react';
import { Check, Pencil, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { UserSelect, mergeUserOptions } from './UserSelect';
import type { Category, UserRef } from '@/types/domain';

/**
 * One category line: rename inline, optional escalation override select,
 * remove button (spec 9.13). Deletion confirmation lives in CategoryManager.
 */
export function CategoryRow({
  category,
  editable,
  escalationOptions,
  busy,
  onSave,
  onDelete,
}: {
  category: Category;
  editable: boolean;
  escalationOptions: UserRef[];
  /** True while any category mutation for this department is pending. */
  busy: boolean;
  onSave: (updates: { name?: string; escalation_override_id?: string | null }) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(category.name);
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus the rename input when editing starts (no autoFocus — jsx-a11y).
  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const startEdit = () => {
    setDraft(category.name);
    setEditing(true);
  };

  const commit = () => {
    const name = draft.trim();
    setEditing(false);
    if (name.length < 2 || name === category.name) return;
    onSave({ name });
  };

  const overrideId = category.escalation_override?.id ?? null;

  return (
    <li className="flex flex-wrap items-center gap-2 border-b border-line py-2 last:border-b-0">
      {editing ? (
        <>
          <label className="sr-only" htmlFor={`cat-name-${category.id}`}>
            Category name
          </label>
          <Input
            id={`cat-name-${category.id}`}
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                commit();
              }
              if (e.key === 'Escape') setEditing(false);
            }}
            className="h-8 max-w-[220px]"
            maxLength={80}
            disabled={busy}
          />
          <Button
            size="iconSm"
            variant="ghost"
            aria-label={`Save name for ${category.name}`}
            onClick={commit}
            disabled={busy}
          >
            <Check className="h-3.5 w-3.5 text-ok" aria-hidden="true" />
          </Button>
          <Button
            size="iconSm"
            variant="ghost"
            aria-label={`Cancel rename of ${category.name}`}
            onClick={() => setEditing(false)}
            disabled={busy}
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </>
      ) : (
        <span className="min-w-[120px] flex-1 text-body text-fg">{category.name}</span>
      )}

      {editable ? (
        <>
          <div className="flex items-center gap-1.5">
            <span className="label-caps hidden text-muted sm:inline">Override</span>
            <UserSelect
              label={`Escalation override for ${category.name}`}
              value={overrideId}
              onChange={(id) => onSave({ escalation_override_id: id })}
              options={mergeUserOptions(escalationOptions, [category.escalation_override])}
              placeholder="No override"
              allowClear
              disabled={busy}
              className="w-[180px]"
            />
          </div>
          {!editing ? (
            <Button
              size="iconSm"
              variant="ghost"
              aria-label={`Rename ${category.name}`}
              onClick={startEdit}
              disabled={busy}
            >
              <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          ) : null}
          <Button
            size="iconSm"
            variant="ghost"
            aria-label={`Remove ${category.name}`}
            onClick={onDelete}
            disabled={busy}
          >
            <Trash2 className="h-3.5 w-3.5 text-crit" aria-hidden="true" />
          </Button>
        </>
      ) : (
        <span className="text-small text-muted">
          {category.escalation_override
            ? `Override: ${category.escalation_override.name}`
            : 'No override'}
        </span>
      )}
    </li>
  );
}
