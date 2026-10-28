import { useMemo, useState } from 'react';
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
  type VisibilityState,
} from '@tanstack/react-table';
import { ChevronDown, ChevronLeft, ChevronRight, ChevronsUpDown } from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { SkeletonTable } from '@/components/ui/skeleton';
import { EmptyState, ErrorState } from '@/components/common/States';
import { cn } from '@/lib/cn';

export interface DataTablePagination {
  page: number;
  pageSize: number;
  total: number;
}

export interface DataTableProps<T> {
  columns: ColumnDef<T, unknown>[];
  data: T[];
  loading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
  /** Mouse click + Enter/Space on a row (spec 3.5). */
  onRowClick?: (row: T) => void;
  emptyState?: React.ReactNode;
  sorting?: SortingState;
  onSortingChange?: (sorting: SortingState) => void;
  columnVisibility?: VisibilityState;
  onColumnVisibilityChange?: (visibility: VisibilityState) => void;
  pagination?: DataTablePagination;
  onPageChange?: (page: number) => void;
  /** Accessible caption for the table. */
  caption: string;
  skeletonRows?: number;
}

function SortIndicator({ active, dir }: { active: boolean; dir: 'asc' | 'desc' | false }) {
  return (
    <span
      className={cn('ml-1 inline-flex', active ? 'text-accent' : 'text-muted/60')}
      aria-hidden="true"
    >
      {active ? (
        dir === 'asc' ? (
          <ChevronDown className="h-3.5 w-3.5 rotate-180" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5" />
        )
      ) : (
        <ChevronsUpDown className="h-3.5 w-3.5" />
      )}
    </span>
  );
}

/**
 * TanStack Table wrapper: sorting, column visibility, row activation,
 * sticky header, empty/loading/error rows, server-side pagination.
 */
export function DataTable<T>({
  columns,
  data,
  loading,
  error,
  onRetry,
  onRowClick,
  emptyState,
  sorting,
  onSortingChange,
  columnVisibility,
  onColumnVisibilityChange,
  pagination,
  onPageChange,
  caption,
  skeletonRows = 8,
}: DataTableProps<T>) {
  const [internalSorting, setInternalSorting] = useState<SortingState>([]);
  const [internalVisibility, setInternalVisibility] = useState<VisibilityState>({});

  const isControlledSorting = sorting !== undefined && onSortingChange !== undefined;
  const isControlledVisibility =
    columnVisibility !== undefined && onColumnVisibilityChange !== undefined;

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting: isControlledSorting ? sorting : internalSorting,
      columnVisibility: isControlledVisibility ? columnVisibility : internalVisibility,
    },
    onSortingChange: (updater) => {
      const next =
        typeof updater === 'function'
          ? updater(isControlledSorting ? sorting : internalSorting)
          : updater;
      if (isControlledSorting) onSortingChange(next);
      else setInternalSorting(next);
    },
    onColumnVisibilityChange: (updater) => {
      const next =
        typeof updater === 'function'
          ? updater(isControlledVisibility ? columnVisibility : internalVisibility)
          : updater;
      if (isControlledVisibility) onColumnVisibilityChange(next);
      else setInternalVisibility(next);
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getCoreRowModel(),
    manualSorting: isControlledSorting,
    manualPagination: Boolean(pagination && onPageChange),
    pageCount: pagination
      ? Math.max(1, Math.ceil(pagination.total / pagination.pageSize))
      : undefined,
  });

  const columnCount = useMemo(() => table.getVisibleLeafColumns().length, [table]);

  const showSkeleton = loading && data.length === 0;
  const showError = Boolean(error) && !loading;
  const showEmpty = !loading && !showError && data.length === 0;

  const pageCount = pagination ? Math.max(1, Math.ceil(pagination.total / pagination.pageSize)) : 0;
  const from = pagination ? (pagination.page - 1) * pagination.pageSize + 1 : 0;
  const to = pagination
    ? Math.min(pagination.total, pagination.page * pagination.pageSize)
    : data.length;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-end">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              aria-label="Show or hide columns"
              data-testid="column-visibility"
            >
              <ChevronsUpDown className="h-3.5 w-3.5" aria-hidden="true" />
              Columns
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {table
              .getAllLeafColumns()
              .filter((column) => column.getCanHide())
              .map((column) => (
                <DropdownMenuCheckboxItem
                  key={column.id}
                  checked={column.getIsVisible()}
                  onCheckedChange={(v) => column.toggleVisibility(Boolean(v))}
                  onSelect={(e) => e.preventDefault()}
                >
                  {typeof column.columnDef.header === 'string'
                    ? column.columnDef.header
                    : column.id}
                </DropdownMenuCheckboxItem>
              ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="card scroll-thin max-h-[70dvh] overflow-auto">
        <Table>
          <caption className="sr-only">{caption}</caption>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id} className="hover:bg-transparent">
                {headerGroup.headers.map((header) => {
                  const canSort = header.column.getCanSort();
                  const sorted = header.column.getIsSorted();
                  return (
                    <TableHead
                      key={header.id}
                      aria-sort={
                        sorted ? (sorted === 'asc' ? 'ascending' : 'descending') : undefined
                      }
                    >
                      {header.isPlaceholder ? null : canSort ? (
                        <button
                          type="button"
                          className="label-caps inline-flex items-center uppercase text-muted hover:text-fg"
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          <SortIndicator active={Boolean(sorted)} dir={sorted || false} />
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {showSkeleton ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={columnCount} className="p-0">
                  <SkeletonTable
                    rows={skeletonRows}
                    columns={Math.min(5, Math.max(2, columnCount))}
                  />
                </TableCell>
              </TableRow>
            ) : showError ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={columnCount} className="py-4">
                  <ErrorState
                    message={error?.message}
                    requestId={error?.requestId}
                    onRetry={onRetry}
                  />
                </TableCell>
              </TableRow>
            ) : showEmpty ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={columnCount} className="py-4">
                  {emptyState ?? <EmptyState />}
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  data-testid="data-row"
                  tabIndex={onRowClick ? 0 : undefined}
                  className={cn(onRowClick && 'cursor-pointer')}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                  onKeyDown={
                    onRowClick
                      ? (e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            onRowClick(row.original);
                          }
                        }
                      : undefined
                  }
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {pagination && onPageChange ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="tabular text-small text-muted" aria-live="polite">
            {pagination.total === 0 ? '0 results' : `${from}–${to} of ${pagination.total}`}
          </p>
          <div className="flex items-center gap-1">
            <Button
              variant="secondary"
              size="iconSm"
              onClick={() => onPageChange(pagination.page - 1)}
              disabled={pagination.page <= 1}
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            </Button>
            <span className="tabular px-2 text-small text-muted">
              Page {pagination.page} of {pageCount}
            </span>
            <Button
              variant="secondary"
              size="iconSm"
              onClick={() => onPageChange(pagination.page + 1)}
              disabled={pagination.page >= pageCount}
              aria-label="Next page"
            >
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
