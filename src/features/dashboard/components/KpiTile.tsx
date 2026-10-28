import { ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { StatCard } from './statCards';

/**
 * KPI tile (spec 9.3): a button that navigates to /tickets with the matching
 * filters and the same count. Informational tiles (no deep link) render as a
 * plain card so they are not focusable or clickable.
 */
export function KpiTile({ card }: { card: StatCard }) {
  const navigate = useNavigate();
  const { to } = card;

  const content = (
    <>
      <span className="label-caps block">{card.label}</span>
      <span className="tabular mt-1.5 block text-[26px] font-semibold leading-none text-fg">
        {card.value}
      </span>
      <span className="mt-1.5 block text-small text-muted">{card.hint}</span>
    </>
  );

  if (!to) {
    return <div className="card p-4">{content}</div>;
  }

  return (
    <button
      type="button"
      onClick={() => navigate(to)}
      className="card hover:border-accent/60 hover:bg-surface-2/60 p-4 text-left transition-colors"
    >
      {content}
      <span className="mt-2 inline-flex items-center gap-1 text-small font-medium text-accent">
        View list
        <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
      </span>
    </button>
  );
}
