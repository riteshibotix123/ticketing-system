import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Ban, Lock, Trash2, UserCheck } from 'lucide-react';
import { errorMessage } from '@/api/client';
import { usersApi } from '@/api/endpoints/users';
import { queryKeys } from '@/api/queryKeys';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { RoleBadges } from '@/components/common/RoleBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useToast } from '@/hooks/useToast';
import { orderedRoles } from '@/lib/permissions';
import { reasonSchema } from '@/lib/zod-schemas';
import { StatePill } from './StatePill';
import type { UserListItem } from '@/types/domain';

type AdminActionKind = 'deactivate' | 'activate' | 'remove';

const ACTION_TOAST: Record<AdminActionKind, string> = {
  deactivate: 'Admin deactivated.',
  activate: 'Admin activated.',
  remove: 'Admin removed.',
};

const CONFIRM_COPY: Record<
  AdminActionKind,
  { title: string; label: string; destructive?: boolean }
> = {
  deactivate: { title: 'Deactivate admin?', label: 'Deactivate' },
  activate: { title: 'Activate admin?', label: 'Activate' },
  remove: { title: 'Remove admin?', label: 'Remove', destructive: true },
};

/**
 * Admin accounts list with Super Admin actions (spec 9.13 + rule 14).
 * Every action is confirmed in-page with a reason — never window.confirm.
 */
export function AdminList({ admins }: { admins: UserListItem[] }) {
  const { success } = useToast();
  const qc = useQueryClient();
  const [pending, setPending] = useState<{ kind: AdminActionKind; user: UserListItem } | null>(null);
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState<string | null>(null);

  const close = () => {
    setPending(null);
    setReason('');
    setReasonError(null);
    actionMutation.reset();
  };

  const actionMutation = useMutation({
    mutationFn: ({ kind, user }: { kind: AdminActionKind; user: UserListItem }): Promise<unknown> => {
      // Rule 10/14: every account change carries the confirmed reason so the
      // server can audit it.
      const trimmed = reason.trim();
      if (kind === 'deactivate') return usersApi.deactivate(user.id, trimmed);
      if (kind === 'activate') return usersApi.activate(user.id);
      return usersApi.removeAdmin(user.id);
    },
    onSuccess: (data, vars) => {
      const result = data as { result?: string } | null;
      success(
        result?.result === 'protected_request_created'
          ? 'Sent for second Super Admin approval.'
          : ACTION_TOAST[vars.kind],
      );
      void qc.invalidateQueries({ queryKey: queryKeys.admins });
      close();
    },
  });

  const open = (kind: AdminActionKind, user: UserListItem) => {
    actionMutation.reset();
    setReason('');
    setReasonError(null);
    setPending({ kind, user });
  };

  const confirm = () => {
    if (pending?.kind === 'deactivate') {
      const parsed = reasonSchema.safeParse({ reason: reason.trim() });
      if (!parsed.success) {
        setReasonError('Required.');
        return;
      }
    }
    setReasonError(null);
    if (pending) actionMutation.mutate(pending);
  };

  const copy = pending ? CONFIRM_COPY[pending.kind] : CONFIRM_COPY.deactivate;

  return (
    <>
      <div className="card scroll-thin overflow-x-auto">
        <Table>
          <caption className="sr-only">Admin accounts</caption>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Name</TableHead>
              <TableHead>Roles</TableHead>
              <TableHead>State</TableHead>
              <TableHead>
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {admins.map((admin) => {
              const isSuperAdmin = admin.roles.includes('super_admin');
              return (
                <TableRow key={admin.id} data-testid="admin-row">
                  <TableCell>
                    <span className="block font-medium text-fg">{admin.name}</span>
                    <span className="block text-small text-muted">{admin.email}</span>
                  </TableCell>
                  <TableCell>
                    <RoleBadges me={{ roles: orderedRoles(admin.roles) }} />
                  </TableCell>
                  <TableCell>
                    <span className="flex flex-wrap items-center gap-1.5">
                      <StatePill state={admin.state} />
                      {isSuperAdmin ? (
                        <Badge variant="info">
                          <Lock className="h-3 w-3" aria-hidden="true" />
                          Protected
                        </Badge>
                      ) : null}
                    </span>
                  </TableCell>
                  <TableCell>
                    {isSuperAdmin ? (
                      <span className="text-small text-muted">Managed by the server seed</span>
                    ) : (
                      <div className="flex justify-end gap-1">
                        {admin.state === 'deactivated' ? (
                          <Button
                            size="sm"
                            variant="secondary"
                            aria-label={`Activate ${admin.name}`}
                            onClick={() => open('activate', admin)}
                          >
                            <UserCheck className="h-3.5 w-3.5" aria-hidden="true" />
                            Activate
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            variant="secondary"
                            aria-label={`Deactivate ${admin.name}`}
                            onClick={() => open('deactivate', admin)}
                          >
                            <Ban className="h-3.5 w-3.5" aria-hidden="true" />
                            Deactivate
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="outlineDanger"
                          aria-label={`Remove ${admin.name}`}
                          onClick={() => open('remove', admin)}
                        >
                          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                          Remove
                        </Button>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(v) => {
          if (!v) close();
        }}
        title={copy.title}
        description={
          pending
            ? `${pending.user.name} (${pending.user.email})${
                pending.kind === 'remove'
                  ? ' will be removed from the admin list. Their account stays for tickets they own.'
                  : pending.kind === 'deactivate'
                    ? ' will lose admin access immediately.'
                    : ' regains admin access.'
              }`
            : undefined
        }
        confirmLabel={copy.label}
        destructive={copy.destructive}
        loading={actionMutation.isPending}
        onConfirm={confirm}
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor="admin-action-reason" className="text-small font-medium text-fg">
            Reason
            <span aria-hidden="true" className="ml-1 text-crit">
              *
            </span>
          </label>
          <Input
            id="admin-action-reason"
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              if (reasonError) setReasonError(null);
            }}
            placeholder="Why is this changing?"
            maxLength={500}
            disabled={actionMutation.isPending}
            aria-invalid={reasonError ? true : undefined}
          />
          {reasonError ? (
            <p role="alert" className="text-small text-crit">
              {reasonError}
            </p>
          ) : null}
          {actionMutation.isError ? (
            <p role="alert" className="flex items-center gap-1 text-small text-crit">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {errorMessage(actionMutation.error)}
            </p>
          ) : null}
        </div>
      </ConfirmDialog>
    </>
  );
}
