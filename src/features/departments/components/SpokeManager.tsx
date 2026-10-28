import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, X } from 'lucide-react';
import { errorMessage } from '@/api/client';
import { departmentsApi } from '@/api/endpoints/departments';
import { queryKeys } from '@/api/queryKeys';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useToast } from '@/hooks/useToast';
import type { Department, UserRef } from '@/types/domain';

/**
 * Spokes as chips with a remove ✕, plus add via a searchable picker (spec 9.13).
 * `candidates` are users eligible to become Spokes.
 */
export function SpokeManager({
  department,
  editable,
  candidates,
}: {
  department: Department;
  editable: boolean;
  candidates: UserRef[];
}) {
  const { success, error: errorToast } = useToast();
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [filter, setFilter] = useState('');
  const [pendingRemove, setPendingRemove] = useState<UserRef | null>(null);
  const filterRef = useRef<HTMLInputElement>(null);

  // Focus the filter when the picker opens (no autoFocus — jsx-a11y).
  useEffect(() => {
    if (addOpen) filterRef.current?.focus();
  }, [addOpen]);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.departments });
    // Spokes receive L1 escalation emails — ticket caches may change.
    void qc.invalidateQueries({ queryKey: ['tickets'] });
  };

  const addMutation = useMutation({
    mutationFn: (userId: string) => departmentsApi.addSpoke(department.id, userId),
    onSuccess: () => {
      success('Spoke added.');
      invalidate();
      setAddOpen(false);
      setFilter('');
    },
    onError: (err) => errorToast(errorMessage(err)),
  });

  const removeMutation = useMutation({
    mutationFn: (userId: string) => departmentsApi.removeSpoke(department.id, userId),
    onSuccess: () => {
      success('Spoke removed.');
      invalidate();
      setPendingRemove(null);
    },
    onError: (err) => errorToast(errorMessage(err)),
  });

  const options = useMemo(() => {
    const current = new Set(department.spokes.map((s) => s.id));
    return candidates.filter((u) => !current.has(u.id));
  }, [candidates, department]);

  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return options;
    return options.filter(
      (u) => u.name.toLowerCase().includes(needle) || u.email.toLowerCase().includes(needle),
    );
  }, [options, filter]);

  return (
    <div className="flex flex-wrap items-center gap-1">
      {department.spokes.length === 0 ? (
        <span className="text-small text-muted">No spokes yet.</span>
      ) : null}
      {department.spokes.map((spoke) => (
        <span
          key={spoke.id}
          className="inline-flex items-center gap-1 rounded-full border border-line bg-surface-2 py-0.5 pl-2 text-small text-fg"
        >
          {spoke.name}
          {editable ? (
            <button
              type="button"
              aria-label={`Remove ${spoke.name} as Spoke`}
              onClick={() => setPendingRemove(spoke)}
              className="rounded p-0.5 text-muted hover:bg-crit-soft hover:text-crit"
            >
              <X className="h-3 w-3" aria-hidden="true" />
            </button>
          ) : (
            <span className="pr-1.5" aria-hidden="true" />
          )}
        </span>
      ))}

      {editable ? (
        <Popover
          open={addOpen}
          onOpenChange={(v) => {
            setAddOpen(v);
            if (!v) setFilter('');
          }}
        >
          <PopoverTrigger asChild>
            <Button variant="ghost" size="sm" aria-label={`Add a Spoke to ${department.name}`}>
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
              Add
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[260px] p-2" align="start">
            <label className="sr-only" htmlFor={`spoke-filter-${department.id}`}>
              Filter people
            </label>
            <Input
              id={`spoke-filter-${department.id}`}
              ref={filterRef}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter people…"
              className="h-8"
            />
            <ul className="scroll-thin mt-2 max-h-52 overflow-y-auto">
              {shown.length === 0 ? (
                <li className="px-2 py-3 text-small text-muted">No people to add.</li>
              ) : null}
              {shown.map((user) => (
                <li key={user.id}>
                  <button
                    type="button"
                    disabled={addMutation.isPending}
                    onClick={() => addMutation.mutate(user.id)}
                    className="flex w-full flex-col rounded-sm px-2 py-1.5 text-left hover:bg-surface-2"
                  >
                    <span className="text-body text-fg">{user.name}</span>
                    <span className="text-small text-muted">{user.email}</span>
                  </button>
                </li>
              ))}
            </ul>
          </PopoverContent>
        </Popover>
      ) : null}

      <ConfirmDialog
        open={pendingRemove !== null}
        onOpenChange={(v) => {
          if (!v) setPendingRemove(null);
        }}
        title="Remove Spoke?"
        description={
          pendingRemove
            ? `${pendingRemove.name} will no longer own or receive tickets for ${department.name}.`
            : undefined
        }
        confirmLabel="Remove"
        destructive
        loading={removeMutation.isPending}
        onConfirm={() => {
          if (pendingRemove) removeMutation.mutate(pendingRemove.id);
        }}
      />
    </div>
  );
}
