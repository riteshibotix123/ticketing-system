import { Check, Clock, XCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { ACCOUNT_STATE_LABEL } from '@/lib/constants';
import type { AccountState } from '@/types/domain';

/** Account state pill — text + icon, never colour alone (spec 3.1/3.6). */
export function StatePill({ state }: { state: AccountState }) {
  if (state === 'active') {
    return (
      <Badge variant="ok">
        <Check className="h-3 w-3" aria-hidden="true" />
        Active
      </Badge>
    );
  }
  if (state === 'deactivated') {
    return (
      <Badge variant="muted">
        <XCircle className="h-3 w-3" aria-hidden="true" />
        Deactivated
      </Badge>
    );
  }
  return (
    <Badge variant="warn">
      <Clock className="h-3 w-3" aria-hidden="true" />
      {ACCOUNT_STATE_LABEL[state] ?? state}
    </Badge>
  );
}
