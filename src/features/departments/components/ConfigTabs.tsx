import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/cn';
import { usePermissions } from '@/hooks/usePermissions';

const TABS = [
  { to: '/config/departments', label: 'Departments' },
  { to: '/config/policy', label: 'Policy' },
  { to: '/config/admins', label: 'Admin accounts', permission: 'admins.manage' },
];

/**
 * Sub-navigation shared by the three configuration screens (spec 9.13) — the
 * sidebar only links /config/departments, so without this Policy and Admin
 * accounts would be unreachable. Admin accounts stays Super-Admin only.
 */
export function ConfigTabs() {
  const { can } = usePermissions();
  const tabs = TABS.filter((tab) => !tab.permission || can(tab.permission));

  return (
    <nav aria-label="Configuration sections" className="mb-4 border-b border-line">
      <div className="flex flex-wrap gap-1">
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              cn(
                '-mb-px border-b-2 px-3 py-2 text-body transition-colors',
                isActive
                  ? 'border-accent font-medium text-accent'
                  : 'border-transparent text-muted hover:text-fg',
              )
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
