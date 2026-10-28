import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { usersApi } from '@/api/endpoints/users';
import { queryKeys } from '@/api/queryKeys';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useDebounce } from '@/hooks/useDebounce';
import { useToast } from '@/hooks/useToast';
import { UserSelect } from './UserSelect';

export function AddAdminDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { success } = useToast();
  const qc = useQueryClient();
  const [query, setQuery] = useState('');
  const [userId, setUserId] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const debounced = useDebounce(query, 300);
  const canSearch = debounced.trim().length >= 2;

  const lookup = useQuery({
    queryKey: ['users', 'lookup', debounced],
    queryFn: () => usersApi.lookup(debounced),
    enabled: canSearch,
  });

  const mutation = useMutation({
    mutationFn: (id: string) => usersApi.createAdmin(id),
    onSuccess: () => {
      success('Admin added.');
      void qc.invalidateQueries({ queryKey: queryKeys.admins });
      setQuery('');
      setUserId(null);
      setServerError(null);
      onOpenChange(false);
    },
    onError: (err) => setServerError(errorMessage(err)),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!mutation.isPending) {
          setServerError(null);
          onOpenChange(v);
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Admin</DialogTitle>
          <DialogDescription>
            Choose an active employee. Their account is promoted to Admin immediately.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="admin-lookup" className="text-small font-medium text-fg">
              Find a person
            </label>
            <Input
              id="admin-lookup"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setUserId(null);
              }}
              placeholder="Name or email"
              disabled={mutation.isPending}
            />
            <p className="text-small text-muted">Type at least 2 characters.</p>
          </div>

          <UserSelect
            label="New Admin"
            value={userId}
            onChange={setUserId}
            options={lookup.data ?? []}
            placeholder={
              canSearch
                ? lookup.isFetching
                  ? 'Searching…'
                  : 'Pick a person'
                : 'Search for a person first'
            }
            disabled={!canSearch || mutation.isPending}
          />

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
              type="button"
              variant="primary"
              onClick={() => userId && mutation.mutate(userId)}
              loading={mutation.isPending}
              loadingLabel="Saving"
              disabled={!userId}
            >
              Add Admin
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
