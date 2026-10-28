import type { ComponentProps } from 'react';
import { Link } from 'react-router-dom';
import type { ColumnDef } from '@tanstack/react-table';
import { Ban, CheckCircle2, Clock, XCircle } from 'lucide-react';
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
import { RelativeTime } from '@/components/common/RelativeTime';
import { ACCOUNT_STATE_LABEL } from '@/lib/constants';
import type { AccountState, Department, UserListItem } from '@/types/domain';

type BadgeVariant = ComponentProps<typeof Badge>['variant'];
type IconType = typeof Ban;

const STATE_META: Record<AccountState, { variant: BadgeVariant; Icon: IconType }> = {
  active: { variant: 'ok', Icon: CheckCircle2 },
  pending_approval: { variant: 'info', Icon: Clock },
  pending_verification: { variant: 'info', Icon: Clock },
  rejected: { variant: 'crit', Icon: XCircle },
  deactivated: { variant: 'muted', Icon: Ban },
};

export interface UserColumnOptions {
  departments: Department[];
  onRoles: (user: UserListItem) => void;
  onAccount: (user: UserListItem) => void;
}

export function getUserColumns({
  departments,
  onRoles,
  onAccount,
}: UserColumnOptions): ColumnDef<UserListItem, unknown>[] {
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
      id: 'roles',
      header: 'Roles',
      enableSorting: false,
      cell: ({ row }) => <RoleBadges me={{ roles: row.original.roles }} />,
    },
    {
      id: 'state',
      header: 'Account state',
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
      id: 'department',
      header: 'Home department',
      enableSorting: false,
      cell: ({ row }) => {
        const departmentId = row.original.department_id;
        if (!departmentId) return <span className="text-muted">—</span>;
        return departmentNames.get(departmentId) ?? departmentId;
      },
    },
    {
      id: 'spoke-departments',
      header: 'Spoke departments',
      enableSorting: false,
      cell: ({ row }) => {
        const ids = row.original.spoke_departments;
        if (ids.length === 0) return <span className="text-small text-muted">None</span>;
        return (
          <span className="flex flex-wrap gap-1">
            {ids.map((id) => (
              <Badge key={id} variant="outline">
                {departmentNames.get(id) ?? id}
              </Badge>
            ))}
          </span>
        );
      },
    },
    {
      id: 'last-login',
      header: 'Last login',
      enableSorting: false,
      cell: ({ row }) =>
        row.original.last_login_at ? (
          <RelativeTime iso={row.original.last_login_at} className="text-small text-muted" />
        ) : (
          <span className="text-small text-muted">Never</span>
        ),
    },
    {
      id: 'actions',
      header: 'Actions',
      enableSorting: false,
      cell: ({ row }) => {
        const user = row.original;
        if (user.roles.includes('admin') || user.roles.includes('super_admin')) {
          return (
            <Link
              to="/config/admins"
              className="text-small font-medium text-accent underline-offset-4 hover:underline"
            >
              Managed in Admin accounts
            </Link>
          );
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
              <DropdownMenuItem onSelect={() => onRoles(user)}>
                Manage Spoke departments…
              </DropdownMenuItem>
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
