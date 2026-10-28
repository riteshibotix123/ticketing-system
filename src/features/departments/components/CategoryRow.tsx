import { useEffect, useId, useRef, useState } from 'react';
import { Check, Lock, Pencil, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import type { Category } from '@/types/domain';

export function CategoryRow({
  category,
  editable,
  busy,
  onSave,
  onDelete,
}: {
  category: Category;
  editable: boolean;
  busy: boolean;
  onSave: (updates: { name?: string; confidential?: boolean }) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(category.name);
  const inputRef = useRef<HTMLInputElement>(null);
  const confidentialId = useId();

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

      {category.confidential ? (
        <span className="inline-flex items-center gap-1 text-small text-muted">
          <Lock className="h-3.5 w-3.5" aria-hidden="true" />
          Confidential
        </span>
      ) : null}

      {editable ? (
        <>
          <div className="flex items-center gap-2">
            <Checkbox
              id={confidentialId}
              checked={category.confidential}
              onCheckedChange={(value) => onSave({ confidential: value === true })}
              disabled={busy}
            />
            <label htmlFor={confidentialId} className="text-small text-fg">
              Confidential
            </label>
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
      ) : null}
    </li>
  );
}
