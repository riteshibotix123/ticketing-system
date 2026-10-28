import { Fragment, useState } from 'react';
import { Check, Pencil, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { CategoryManager } from './CategoryManager';
import { EscalationSelects } from './EscalationSelects';
import { SpokeManager } from './SpokeManager';
import type { Department, UserRef } from '@/types/domain';

const COLUMN_COUNT = 6;

/**
 * Departments table (spec 9.13): Spokes as chips, escalation contacts,
 * confidential/active pills, categories count with an inline expandable
 * manager, and row actions.
 */
export function DepartmentTable({
  departments,
  editable,
  spokeCandidates,
  escalationCandidates,
  onEdit,
}: {
  departments: Department[];
  editable: boolean;
  /** null → /users was refused (403); each row falls back to its own Spokes. */
  spokeCandidates: UserRef[] | null;
  /** null → /users was refused (403); each row falls back to its own Spokes. */
  escalationCandidates: UserRef[] | null;
  onEdit: (department: Department) => void;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="card scroll-thin max-h-[70dvh] overflow-auto">
      <Table>
        <caption className="sr-only">
          Departments with Spokes, escalation contacts and categories
        </caption>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Department</TableHead>
            <TableHead>Spokes</TableHead>
            <TableHead className="min-w-[230px]">Escalation contact</TableHead>
            <TableHead>Active</TableHead>
            <TableHead>Categories</TableHead>
            <TableHead>
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {departments.map((department) => {
            const expanded = expandedId === department.id;
            // 403 fallback: pick escalation contacts from the department's own Spokes.
            const escCandidates = escalationCandidates ?? department.spokes;
            return (
              <Fragment key={department.id}>
                <TableRow data-testid="department-row">
                  <TableCell className="font-medium text-fg">{department.name}</TableCell>
                  <TableCell>
                    <SpokeManager
                      department={department}
                      editable={editable}
                      candidates={spokeCandidates ?? department.spokes}
                    />
                  </TableCell>
                  <TableCell>
                    <EscalationSelects
                      key={department.id}
                      department={department}
                      candidates={escCandidates}
                      editable={editable}
                    />
                  </TableCell>
                  <TableCell>
                    {department.active ? (
                      <Badge variant="ok">
                        <Check className="h-3 w-3" aria-hidden="true" />
                        Active
                      </Badge>
                    ) : (
                      <Badge variant="muted">
                        <X className="h-3 w-3" aria-hidden="true" />
                        Inactive
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="tabular text-small text-muted">
                        {department.categories.length}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-expanded={expanded}
                        aria-label={`Manage categories for ${department.name}`}
                        onClick={() => setExpandedId(expanded ? null : department.id)}
                      >
                        {expanded ? 'Hide' : 'Manage'}
                      </Button>
                    </div>
                  </TableCell>
                  <TableCell>
                    {editable ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        aria-label={`Edit ${department.name}`}
                        onClick={() => onEdit(department)}
                      >
                        <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                        Edit
                      </Button>
                    ) : (
                      <span className="text-small text-muted">—</span>
                    )}
                  </TableCell>
                </TableRow>
                {expanded ? (
                  <TableRow className="hover:bg-transparent">
                    <TableCell colSpan={COLUMN_COUNT} className="bg-surface-2/60 px-4 py-3">
                      <CategoryManager department={department} editable={editable} />
                    </TableCell>
                  </TableRow>
                ) : null}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
