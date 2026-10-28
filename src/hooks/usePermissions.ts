import { useMemo } from 'react';
import { useAuth } from '@/hooks/useAuth';
import {
  canApproveSignup,
  grantableRoles,
  hasPermission,
  hasRole,
  isStaff,
  primaryRole,
} from '@/lib/permissions';
import type { Me, Role } from '@/types/domain';

export interface PermissionsApi {
  me: Me | null;
  /** True while /auth/me is loading. */
  loading: boolean;
  can: (flag: string) => boolean;
  canAny: (flags: string[]) => boolean;
  hasRole: (...roles: Role[]) => boolean;
  isStaff: boolean;
  primaryRole: Role | null;
  canApproveSignup: (
    requestedRole: 'employee' | 'admin' | 'super_admin',
    isSelf: boolean,
  ) => boolean;
  grantableRoles: Array<'employee' | 'admin' | 'super_admin'>;
  isSpokeFor: (departmentId: string) => boolean;
}

/**
 * Permission helpers built from the flags in `/auth/me` (spec 4).
 * Never derive from role names where a flag exists.
 */
export function usePermissions(): PermissionsApi {
  const { me, status } = useAuth();

  return useMemo<PermissionsApi>(() => {
    const base: Pick<Me, 'permissions'> = { permissions: me?.permissions ?? [] };
    return {
      me,
      loading: status === 'loading',
      can: (flag) => hasPermission(base, flag),
      canAny: (flags) => flags.some((f) => hasPermission(base, f)),
      hasRole: (...roles) => hasRole(me, ...roles),
      isStaff: isStaff(me),
      primaryRole: primaryRole(me),
      canApproveSignup: (requestedRole, isSelf) => canApproveSignup(base, requestedRole, isSelf),
      grantableRoles: grantableRoles(base),
      isSpokeFor: (departmentId) => (me?.spoke_departments ?? []).includes(departmentId),
    };
  }, [me, status]);
}
