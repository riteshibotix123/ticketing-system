import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { EmptyState } from '@/components/common/States';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/cn';
import type { AdminDashboard } from '@/types/domain';

type DeptRow = AdminDashboard['by_department'][number];

const LEGEND = [
  { key: 'on_track', label: 'On track', swatch: 'bg-ok' },
  { key: 'warning', label: 'Warning', swatch: 'bg-warn' },
  { key: 'breached', label: 'Breached', swatch: 'bg-crit' },
] as const;

function rowLabel(row: DeptRow): string {
  return `${row.name}: ${row.on_track} on track, ${row.warning} warning, ${row.breached} breached`;
}

/**
 * Admin only (spec 9.3): stacked horizontal bars of open tickets per department
 * (on track / warning / breached). Counts are always shown as text — colour is
 * never the only signal — and every bar row has an accessible label.
 */
export function DepartmentBars({ rows }: { rows: DeptRow[] }) {
  if (rows.length === 0) {
    return <EmptyState title="No open tickets." description="Department totals appear here." />;
  }

  // Height scales with the number of departments.
  const height = Math.max(160, rows.length * 34 + 48);
  const data = rows.map((r) => ({ ...r, total: r.on_track + r.warning + r.breached }));

  return (
    <section className="card p-4" aria-labelledby="dept-bars-title">
      <h2 id="dept-bars-title" className="text-section-title text-fg">
        Open tickets by department
      </h2>

      <ul className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-small text-muted">
        {LEGEND.map((l) => (
          <li key={l.key} className="inline-flex items-center gap-1.5">
            <span className={cn('h-2.5 w-2.5 rounded-sm', l.swatch)} aria-hidden="true" />
            {l.label}
          </li>
        ))}
      </ul>

      <div
        className="mt-3"
        role="img"
        aria-label={`Stacked bars of open tickets for ${rows.length} ${
          rows.length === 1 ? 'department' : 'departments'
        }. Exact counts are listed in the table below.`}
      >
        <ResponsiveContainer width="100%" height={height}>
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 4, right: 8, bottom: 4, left: 0 }}
            barCategoryGap="25%"
          >
            <XAxis type="number" hide domain={[0, 'dataMax']} />
            <YAxis
              type="category"
              dataKey="name"
              width={110}
              interval={0}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 12, fill: 'var(--muted)' }}
            />
            <Tooltip
              cursor={{ fill: 'var(--surface-2)' }}
              contentStyle={{
                background: 'var(--surface)',
                border: '1px solid var(--line)',
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: 'var(--fg)' }}
            />
            <Bar dataKey="on_track" name="On track" stackId="open" fill="var(--ok)" barSize={18} />
            <Bar dataKey="warning" name="Warning" stackId="open" fill="var(--warn)" barSize={18} />
            <Bar
              dataKey="breached"
              name="Breached"
              stackId="open"
              fill="var(--crit)"
              barSize={18}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="scroll-thin mt-3 overflow-x-auto">
        <Table>
          <caption className="sr-only">
            Open tickets per department by SLA state, with counts as text
          </caption>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Department</TableHead>
              <TableHead className="text-right">On track</TableHead>
              <TableHead className="text-right">Warning</TableHead>
              <TableHead className="text-right">Breached</TableHead>
              <TableHead className="text-right">Total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.department_id}>
                <TableCell>
                  <span aria-label={rowLabel(r)}>{r.name}</span>
                  <span className="sr-only">
                    : {r.on_track} on track, {r.warning} warning, {r.breached} breached
                  </span>
                </TableCell>
                <TableCell className="tabular text-right">{r.on_track}</TableCell>
                <TableCell className="tabular text-right">{r.warning}</TableCell>
                <TableCell className="tabular text-right">{r.breached}</TableCell>
                <TableCell className="tabular text-right">
                  {r.on_track + r.warning + r.breached}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}
