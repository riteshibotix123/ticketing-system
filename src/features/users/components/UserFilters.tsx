import { useEffect, useId, useState } from 'react';
import { FilterBar } from '@/components/common/FilterBar';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useDebounce } from '@/hooks/useDebounce';
import type { useUrlFilters } from '@/hooks/useUrlFilters';
import { ACCOUNT_STATE_LABEL, ROLE_LABEL } from '@/lib/constants';
import type { Department, Role } from '@/types/domain';

const ANY = 'any';
const ROLE_FILTERS: Role[] = ['employee', 'spoke', 'admin', 'super_admin'];
const STATE_FILTERS = [
  'active',
  'pending_approval',
  'pending_verification',
  'rejected',
  'deactivated',
] as const;

/**
 * Search + role/state/department filters for /users (spec 9.12). The search is
 * debounced 300ms before it reaches the URL; selects write to the URL directly,
 * so refresh and sharing restore the exact view.
 */
export function UserFilters({
  filters,
  departments,
}: {
  filters: ReturnType<typeof useUrlFilters>;
  departments: Department[];
}) {
  const roleId = useId();
  const stateId = useId();
  const departmentId = useId();
  const [search, setSearch] = useState(() => filters.get('q'));
  const debouncedSearch = useDebounce(search, 300);
  const q = filters.get('q');

  // Push the debounced search to the URL only once typing has settled, so a
  // pending debounce can never overwrite a Clear.
  useEffect(() => {
    if (search === debouncedSearch && debouncedSearch !== q) {
      filters.set({ q: debouncedSearch });
    }
  }, [search, debouncedSearch, q, filters]);

  const handleClear = () => {
    setSearch('');
    filters.clear();
  };

  return (
    <FilterBar
      searchValue={search}
      onSearchChange={setSearch}
      searchLabel="Search users"
      searchPlaceholder="Search by name or email"
      activeCount={filters.activeCount}
      onClear={handleClear}
    >
      <div className="w-[172px]">
        <label htmlFor={roleId} className="sr-only">
          Role
        </label>
        <Select
          value={filters.get('role') || ANY}
          onValueChange={(value) => filters.set({ role: value === ANY ? '' : value })}
        >
          <SelectTrigger id={roleId}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any role</SelectItem>
            {ROLE_FILTERS.map((role) => (
              <SelectItem key={role} value={role}>
                {ROLE_LABEL[role]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="w-[192px]">
        <label htmlFor={stateId} className="sr-only">
          Account state
        </label>
        <Select
          value={filters.get('state') || ANY}
          onValueChange={(value) => filters.set({ state: value === ANY ? '' : value })}
        >
          <SelectTrigger id={stateId}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any state</SelectItem>
            {STATE_FILTERS.map((state) => (
              <SelectItem key={state} value={state}>
                {ACCOUNT_STATE_LABEL[state]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="w-[200px]">
        <label htmlFor={departmentId} className="sr-only">
          Department
        </label>
        <Select
          value={filters.get('department_id') || ANY}
          onValueChange={(value) => filters.set({ department_id: value === ANY ? '' : value })}
        >
          <SelectTrigger id={departmentId}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any department</SelectItem>
            {departments.map((department) => (
              <SelectItem key={department.id} value={department.id}>
                {department.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </FilterBar>
  );
}
