import type { Me, Role } from '@/types/domain';
import { ROLE_LABEL } from '@/lib/constants';
import { orderedRoles } from '@/lib/permissions';
import { cn } from '@/lib/cn';
const TONE: Partial<Record<Role, string>> = {
  super_admin: 'border-crit/40 bg-crit-soft text-crit',
  admin: 'border-accent/40 bg-accent-soft text-accent',
  spoke: 'border-info/40 bg-info-soft text-info',
};

export function RoleBadge({ role, className }: { role: Role; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex whitespace-nowrap rounded-full border border-line bg-surface-2 px-2 py-0.5 text-small font-medium text-muted',
        TONE[role],
        className,
      )}
    >
      {ROLE_LABEL[role]}
    </span>
  );
}

/** All of a user's roles in display order (highest first). Pass `me` or `roles`. */
export function RoleBadges({
  me,
  roles,
  className,
}: {
  me?: Pick<Me, 'roles'>;
  roles?: Role[];
  className?: string;
}) {
  const list = roles ?? me?.roles ?? [];
  return (
    <span className={cn('flex flex-wrap gap-1', className)}>
      {orderedRoles(list).map((role) => (
        <RoleBadge key={role} role={role} />
      ))}
    </span>
  );
}
