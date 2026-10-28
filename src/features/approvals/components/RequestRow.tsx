import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BadgeCheck } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { RelativeTime } from '@/components/common/RelativeTime';
import { departmentsApi } from '@/api/endpoints/departments';
import { queryKeys } from '@/api/queryKeys';
import { useAuth } from '@/hooks/useAuth';
import { usePermissions } from '@/hooks/usePermissions';
import { ROLE_LABEL } from '@/lib/constants';
import type { SignupRequest } from '@/types/domain';

/**
 * One pending signup request (spec 9.11). The Review button renders only when
 * `canApproveSignup` is true for the viewer; self-requests are never reviewable
 * (rule 12) and everything else shows "Needs a Super Admin".
 */
export function RequestRow({
  request,
  onReview,
}: {
  request: SignupRequest;
  onReview: (request: SignupRequest) => void;
}) {
  const { me } = useAuth();
  const permissions = usePermissions();
  const { data: departments } = useQuery({
    queryKey: queryKeys.departments,
    queryFn: departmentsApi.list,
    staleTime: 60_000,
  });

  const isSelf = (me?.email ?? '').toLowerCase() === request.email.toLowerCase();
  const canReview = permissions.canApproveSignup(request.requested_role, isSelf);
  const departmentLabel =
    departments?.find((d) => d.id === request.requested_department)?.name ??
    request.requested_department;

  let action: ReactNode;
  if (isSelf) {
    action = <p className="text-small text-muted">You cannot review your own request.</p>;
  } else if (canReview) {
    action = (
      <Button
        size="sm"
        variant="secondary"
        onClick={() => onReview(request)}
        aria-label={`Review access request from ${request.name}`}
      >
        Review
      </Button>
    );
  } else {
    action = <p className="text-small text-muted">Needs a Super Admin</p>;
  }

  return (
    <li className="card flex flex-wrap items-start justify-between gap-3 p-4">
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-body font-medium text-fg">{request.name}</span>
          {request.email_verified ? (
            <Badge variant="ok">
              <BadgeCheck className="h-3.5 w-3.5" aria-hidden="true" />
              Verified
            </Badge>
          ) : null}
        </div>
        <p className="break-all text-small text-muted">{request.email}</p>
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          <Badge variant="accent">{ROLE_LABEL[request.requested_role]}</Badge>
          <Badge variant="outline">{departmentLabel}</Badge>
          <span className="text-small text-muted">
            Requested <RelativeTime iso={request.created_at} />
          </span>
        </div>
      </div>
      <div className="flex shrink-0 items-center pt-0.5">{action}</div>
    </li>
  );
}
