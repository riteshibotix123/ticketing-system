import { FilterBar } from '@/components/common/FilterBar';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { PRIORITY_LABEL, PRIORITY_ORDER, STATUS_LABEL } from '@/lib/constants';
import { SLA_STATE_FILTERS } from '@/lib/sla';
import type { Department } from '@/types/domain';

/** Filter values as raw URL query strings ('' / 'any' = unset). */
export interface TicketFilterValues {
  q: string;
  status: string;
  priority: string;
  department: string;
  sla: string;
  confidential: string;
  overdue: string;
}

const STATUS_OPTIONS: { id: string; label: string }[] = Object.entries(STATUS_LABEL).map(
  ([id, label]) => ({ id, label }),
);

export function TicketFilters({
  values,
  onSearchChange,
  onChange,
  departments,
  showDepartment,
  activeCount,
  onClear,
}: {
  values: TicketFilterValues;
  onSearchChange: (value: string) => void;
  /** Called with the complete value set; the parent maps it onto the URL. */
  onChange: (values: TicketFilterValues) => void;
  departments: Department[];
  /** Department filter needs tickets.view_all (spec 9.4). */
  showDepartment: boolean;
  activeCount: number;
  onClear: () => void;
}) {
  function update(patch: Partial<TicketFilterValues>) {
    onChange({ ...values, ...patch });
  }

  return (
    <FilterBar
      searchValue={values.q}
      onSearchChange={onSearchChange}
      searchPlaceholder="Search ID, title or text…"
      searchLabel="Search tickets"
      activeCount={activeCount}
      onClear={onClear}
    >
      <div className="w-[150px]">
        <label htmlFor="tf-status" className="sr-only">
          Status
        </label>
        <Select value={values.status} onValueChange={(v) => update({ status: v })}>
          <SelectTrigger id="tf-status" className="w-full">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any status</SelectItem>
            <SelectItem value="open">Open</SelectItem>
            {STATUS_OPTIONS.map((status) => (
              <SelectItem key={status.id} value={status.id}>
                {status.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="w-[150px]">
        <label htmlFor="tf-priority" className="sr-only">
          Priority
        </label>
        <Select value={values.priority} onValueChange={(v) => update({ priority: v })}>
          <SelectTrigger id="tf-priority" className="w-full">
            <SelectValue placeholder="Priority" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any priority</SelectItem>
            {PRIORITY_ORDER.map((priority) => (
              <SelectItem key={priority} value={priority}>
                {PRIORITY_LABEL[priority]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {showDepartment ? (
        <div className="w-[170px]">
          <label htmlFor="tf-department" className="sr-only">
            Department
          </label>
          <Select
            value={values.department || 'any'}
            onValueChange={(v) => update({ department: v === 'any' ? '' : v })}
          >
            <SelectTrigger id="tf-department" className="w-full">
              <SelectValue placeholder="Department" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Any department</SelectItem>
              {departments.map((dept) => (
                <SelectItem key={dept.id} value={dept.id}>
                  {dept.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : null}

      <div className="w-[150px]">
        <label htmlFor="tf-sla" className="sr-only">
          SLA state
        </label>
        <Select value={values.sla} onValueChange={(v) => update({ sla: v })}>
          <SelectTrigger id="tf-sla" className="w-full">
            <SelectValue placeholder="SLA state" />
          </SelectTrigger>
          <SelectContent>
            {SLA_STATE_FILTERS.map((filter) => (
              <SelectItem key={filter.id} value={filter.id}>
                {filter.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-wrap items-center gap-4 pb-2">
        <span className="flex items-center gap-2">
          <Checkbox
            id="tf-confidential"
            checked={values.confidential === '1'}
            onCheckedChange={(checked) => update({ confidential: checked === true ? '1' : '' })}
          />
          <label htmlFor="tf-confidential" className="cursor-pointer text-small text-fg">
            Confidential only
          </label>
        </span>
        <span className="flex items-center gap-2">
          <Checkbox
            id="tf-overdue"
            checked={values.overdue === '1'}
            onCheckedChange={(checked) => update({ overdue: checked === true ? '1' : '' })}
          />
          <label htmlFor="tf-overdue" className="cursor-pointer text-small text-fg">
            Overdue ETA
          </label>
        </span>
      </div>
    </FilterBar>
  );
}
