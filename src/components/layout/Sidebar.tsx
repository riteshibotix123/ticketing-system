import { NavLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Bell,
  ClipboardList,
  FilePlus2,
  Gauge,
  LayoutDashboard,
  ScrollText,
  Settings2,
  ShieldCheck,
  Users,
} from 'lucide-react';
import { notificationsApi } from '@/api/endpoints/ops';
import { usersApi } from '@/api/endpoints/users';
import { queryKeys } from '@/api/queryKeys';
import { USE_MOCKS } from '@/lib/constants';
import { sidebarFlags } from '@/lib/permissions';
import { usePermissions } from '@/hooks/usePermissions';
import { cn } from '@/lib/cn';

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: number;
  end?: boolean;
}

function CountBadge({ count, label }: { count: number; label: string }) {
  if (!count) return null;
  return (
    <span
      className="tabular ml-auto inline-flex min-w-[18px] items-center justify-center rounded-full bg-accent px-1 text-[11px] font-semibold text-accent-fg"
      aria-label={`${count} ${label}`}
    >
      {count > 99 ? '99+' : count}
    </span>
  );
}

/**
 * Left navigation (236px). Under 860px it becomes a horizontal wrapping nav at
 * the top (spec 3.4). Items are filtered by permission flags (spec 8).
 */
export function Sidebar() {
  const { can, me } = usePermissions();
  const flags = sidebarFlags(me ? { permissions: me.permissions } : null);

  const { data: unread } = useQuery({
    queryKey: queryKeys.unreadCount,
    queryFn: () => notificationsApi.unreadCount(),
    refetchInterval: 60_000,
    retry: false,
  });

  const { data: pending } = useQuery({
    queryKey: queryKeys.pendingSignupCount,
    queryFn: () => usersApi.pendingCount(),
    enabled: flags.approvals,
    refetchInterval: 60_000,
    retry: false,
  });

  const items: NavItem[] = [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, end: true },
    { to: '/tickets', label: 'Tickets', icon: ClipboardList },
    ...(can('tickets.create')
      ? [{ to: '/tickets/new', label: 'New ticket', icon: FilePlus2 }]
      : []),
    { to: '/notifications', label: 'Notifications', icon: Bell, badge: unread?.count ?? 0 },
    ...(flags.approvals
      ? [
          {
            to: '/approvals',
            label: 'Access requests',
            icon: ShieldCheck,
            badge: pending?.count ?? 0,
          },
        ]
      : []),
    ...(flags.users ? [{ to: '/users', label: 'Users', icon: Users }] : []),
    ...(flags.config
      ? [{ to: '/config/departments', label: 'Configuration', icon: Settings2 }]
      : []),
    ...(flags.audit ? [{ to: '/audit', label: 'Audit log', icon: ScrollText }] : []),
    ...(flags.reports ? [{ to: '/reports', label: 'Reports', icon: Gauge }] : []),
  ];

  return (
    <nav
      aria-label="Main navigation"
      className="flex shrink-0 flex-col border-b border-line bg-surface nav:w-[236px] nav:border-b-0 nav:border-r"
    >
      <div className="flex items-center gap-2 px-3 py-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-accent font-mono text-[13px] font-semibold text-accent-fg">
          IX
        </span>
        <span className="text-section-title text-fg">Ibotix Tickets</span>
      </div>

      <div className="flex flex-wrap gap-1 px-3 pb-3 nav:flex-1 nav:flex-col nav:gap-0.5 nav:pb-0">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 rounded px-2.5 py-2 text-body transition-colors',
                  isActive
                    ? 'bg-accent-soft font-medium text-accent'
                    : 'text-muted hover:bg-surface-2 hover:text-fg',
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="whitespace-nowrap">{item.label}</span>
              <CountBadge count={item.badge ?? 0} label="unread" />
            </NavLink>
          );
        })}
      </div>

      <div className="hidden px-4 pb-4 nav:block">
        <p className="text-muted/80 text-small">
          {USE_MOCKS ? 'Demo data. Nothing leaves this page.' : 'Internal use only.'}
        </p>
      </div>
    </nav>
  );
}
