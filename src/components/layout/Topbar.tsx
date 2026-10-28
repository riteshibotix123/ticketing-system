import { Moon, Sun } from 'lucide-react';
import { useTheme } from '@/hooks/useTheme';
import { usePermissions } from '@/hooks/usePermissions';
import { Button } from '@/components/ui/button';
import { GlobalSearch } from '@/components/layout/GlobalSearch';
import { NotificationBell } from '@/components/layout/NotificationBell';
import { UserMenu } from '@/components/layout/UserMenu';
import { RoleBadge } from '@/components/common/RoleBadge';

/** Sticky top bar: search, bell, theme toggle, user menu, role badge (spec 9.2). */
export function Topbar() {
  const { resolved, theme, setTheme } = useTheme();
  const { primaryRole } = usePermissions();
  const next = resolved === 'dark' ? 'light' : 'dark';

  return (
    <header
      className="bg-surface/95 safe-pt sticky top-0 z-30 flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5 backdrop-blur nav:px-6"
      data-testid="topbar"
    >
      <GlobalSearch />

      <div className="ml-auto flex items-center gap-1.5">
        {primaryRole ? (
          <span className="hidden md:block">
            <RoleBadge role={primaryRole} />
          </span>
        ) : null}
        <NotificationBell />
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Switch to ${next} theme (current: ${theme})`}
          onClick={() => setTheme(next)}
          data-testid="theme-toggle"
        >
          {resolved === 'dark' ? (
            <Sun className="h-4 w-4" aria-hidden="true" />
          ) : (
            <Moon className="h-4 w-4" aria-hidden="true" />
          )}
        </Button>
        <UserMenu />
      </div>
    </header>
  );
}
