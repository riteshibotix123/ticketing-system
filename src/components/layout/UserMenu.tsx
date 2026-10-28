import { useNavigate } from 'react-router-dom';
import { Check, ChevronDown, LogOut, Monitor, Moon, Sun } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { usePermissions } from '@/hooks/usePermissions';
import { useTheme, type ThemeChoice } from '@/hooks/useTheme';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { RoleBadges } from '@/components/common/RoleBadge';

const THEME_OPTIONS: { value: ThemeChoice; label: string; icon: typeof Sun }[] = [
  { value: 'system', label: 'System', icon: Monitor },
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
];

/** User menu: name, roles, MFA status, theme choice, logout (spec 9.2). */
export function UserMenu() {
  const { me, logout } = useAuth();
  const { primaryRole } = usePermissions();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();

  if (!me) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          aria-label={`${me.name} — account menu`}
          data-testid="user-menu"
        >
          <span className="hidden max-w-[120px] truncate sm:inline">{me.name}</span>
          <ChevronDown className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[260px]">
        <DropdownMenuLabel className="normal-case tracking-normal">
          <span className="block text-body font-medium text-fg">{me.name}</span>
          <span className="block truncate text-small font-normal text-muted">{me.email}</span>
        </DropdownMenuLabel>
        <div className="flex flex-wrap gap-1 px-2 pb-2">
          <RoleBadges me={me} />
        </div>
        <div className="flex items-center justify-between px-2 pb-2 text-small">
          <span className="text-muted">MFA</span>
          <span className={me.mfa_enabled ? 'text-ok' : 'text-warn'}>
            {me.mfa_enabled ? 'Enabled' : 'Not enabled'}
          </span>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="label-caps">Theme</DropdownMenuLabel>
        {THEME_OPTIONS.map((option) => {
          const Icon = option.icon;
          return (
            <DropdownMenuItem key={option.value} onSelect={() => setTheme(option.value)}>
              <Icon className="h-4 w-4 text-muted" aria-hidden="true" />
              {option.label}
              {theme === option.value ? (
                <Check className="ml-auto h-4 w-4 text-accent" aria-hidden="true" />
              ) : null}
            </DropdownMenuItem>
          );
        })}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            void logout().then(() => navigate('/login'));
          }}
        >
          <LogOut className="h-4 w-4 text-muted" aria-hidden="true" />
          Sign out
        </DropdownMenuItem>
        {primaryRole ? (
          <p className="px-2 py-1.5 text-small text-muted">
            Signed in as {primaryRole.replace('_', ' ')}
          </p>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
