import type { ComponentProps } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Ban, CheckCircle2, Clock, ShieldCheck, ShieldOff, XCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { RoleBadges } from '@/components/common/RoleBadge';
import { ACCOUNT_STATE_LABEL } from '@/lib/constants';
import type { AccountState, Department, User } from '@/types/domain';

type BadgeVariant = ComponentProps<typeof Badge>['variant'];
type IconType = typeof Ban;

/** Tone + icon per state; the label is always shown, never colour alone. */
const STATE_META: Record<AccountState, { variant: BadgeVariant; Icon: IconType }> = {
  active: { variant: 'ok', Icon: CheckCircle2 },
  pending_approval: { variant: 'info', Icon: Clock },
  pending_verification: { variant: 'info', Icon: Clock },
  rejected: { variant: 'crit', Icon: XCircle },
  deactivated: { variant: 'muted', Icon: Ban },
};

const ADMIN_MANAGED_NOTE = 'Managed under Configuration → Admin accounts.';

export interface UserColumnOptions {
  departments: Department[];
  onRoles: (user: User) => void;
  onAccount: (user: User) => void;
}

/**
 * Columns for /users. Admin and Super Admin rows are read-only here — they are
 * managed under Configuration → Admin accounts (spec 9.12).
 */
export function getUserColumns({
  departments,
  onRoles,
  onAccount,
}: UserColumnOptions): ColumnDef<User, unknown>[] {
  const departmentNames = new Map(departments.map((d) => [d.id, d.name]));

  return [
    {
      id: 'name',
      header: 'Name',
      enableSorting: false,
      cell: ({ row }) => (
        <div className="min-w-0">
          <p className="font-medium text-fg">{row.original.name}</p>
          <p className="break-all text-small text-muted">{row.original.email}</p>
        </div>
      ),
    },
    {
      id: 'department',
      header: 'Department',
      enableSorting: false,
      cell: ({ row }) => {
        const departmentId = row.original.department_id;
        if (!departmentId) return <span className="text-muted">—</span>;
        return departmentNames.get(departmentId) ?? departmentId;
      },
    },
    {
      id: 'roles',
      header: 'Roles',
      enableSorting: false,
      cell: ({ row }) => <RoleBadges me={{ roles: row.original.roles }} />,
    },
    {
      id: 'state',
      header: 'State',
      enableSorting: false,
      cell: ({ row }) => {
        const meta = STATE_META[row.original.state];
        const Icon = meta.Icon;
        return (
          <Badge variant={meta.variant}>
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
            {ACCOUNT_STATE_LABEL[row.original.state] ?? row.original.state}
          </Badge>
        );
      },
    },
    {
      id: 'mfa',
      header: 'MFA',
      enableSorting: false,
      cell: ({ row }) =>
        row.original.mfa_enabled ? (
          <span className="inline-flex items-center gap-1 whitespace-nowrap text-small text-ok">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            Enabled
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 whitespace-nowrap text-small text-muted">
            <ShieldOff className="h-3.5 w-3.5" aria-hidden="true" />
            Not enabled
          </span>
        ),
    },
    {
      id: 'actions',
      header: 'Actions',
      enableSorting: false,
      cell: ({ row }) => {
        const user = row.original;
        if (user.roles.includes('admin') || user.roles.includes('super_admin')) {
          return <p className="max-w-[26ch] text-small text-muted">{ADMIN_MANAGED_NOTE}</p>;
        }
        const activating = user.state === 'deactivated';
        const accountAction = activating ? 'Activate account' : 'Deactivate account';
        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="secondary" size="sm" aria-label={`Manage ${user.name}`}>
                Manage
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => onRoles(user)}>Assign roles…</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => onAccount(user)}
                className={activating ? undefined : 'text-crit'}
              >
                {accountAction}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
    },
  ];
}
