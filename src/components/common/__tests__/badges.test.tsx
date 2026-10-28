import { describe, expect, it } from 'vitest';
import { render, screen, type RenderResult } from '@testing-library/react';
import { PriorityBadge } from '../PriorityBadge';
import { StatusBadge } from '../StatusBadge';
import { ConfidentialBadge } from '../ConfidentialBadge';
import { RoleBadge } from '../RoleBadge';
import { SlaIndicator, SlaBanner } from '../SlaIndicator';
import { TooltipProvider } from '@/components/ui/tooltip';
import type { SlaState } from '@/types/domain';

/** The app wraps everything in TooltipProvider; tests mirror that. */
function renderUI(ui: React.ReactElement): RenderResult {
  return render(<TooltipProvider>{ui}</TooltipProvider>);
}

describe('PriorityBadge (spec 3.5)', () => {
  it('always shows text, never colour alone', () => {
    render(<PriorityBadge priority="critical" />);
    expect(screen.getByText('Critical')).toBeInTheDocument();
  });

  it('covers every priority', () => {
    (['low', 'medium', 'high', 'critical'] as const).forEach((priority) => {
      const { unmount } = render(<PriorityBadge priority={priority} />);
      expect(screen.getByText(/Low|Medium|High|Critical/)).toBeInTheDocument();
      unmount();
    });
  });
});

describe('StatusBadge', () => {
  it('renders the status label with a non-colour icon', () => {
    render(<StatusBadge status="resolved" />);
    const pill = screen.getByText('Resolved');
    expect(pill).toBeInTheDocument();
    expect(pill.closest('span')?.textContent).toContain('✓');
  });

  it('renders muted statuses as text too', () => {
    render(<StatusBadge status="cancelled" />);
    expect(screen.getByText('Cancelled')).toBeInTheDocument();
  });
});

describe('simple badges', () => {
  it('shows Confidential and role names', () => {
    render(<ConfidentialBadge />);
    expect(screen.getByText('Confidential')).toBeInTheDocument();
    // eslint-disable-next-line jsx-a11y/aria-role -- `role` is RoleBadge's domain prop, not an ARIA role
    render(<RoleBadge role="spoke" />);
    expect(screen.getByText('Spoke')).toBeInTheDocument();
  });
});

const sla = (over: Partial<SlaState> = {}): SlaState => ({
  level: 0,
  kind: 'initial_response',
  paused: false,
  stopped: false,
  due_at: '2099-01-01T00:00:00.000Z',
  label: 'Initial response due',
  ...over,
});

describe('SlaIndicator (spec 3.5 / 11.3)', () => {
  it('shows icon, label and countdown text', () => {
    renderUI(<SlaIndicator sla={sla()} now={Date.parse('2098-12-31T18:00:00.000Z')} />);
    // The server label is authoritative; the level tone/icon is decoration.
    expect(screen.getByText('Initial response due')).toBeInTheDocument();
    expect(screen.getByText(/Response due in/)).toBeInTheDocument();
    expect(screen.getByText('●')).toBeInTheDocument();
  });

  it('falls back to the level label when the server sends none', () => {
    renderUI(
      <SlaIndicator sla={sla({ label: '' })} now={Date.parse('2098-12-31T18:00:00.000Z')} />,
    );
    expect(screen.getByText('On track')).toBeInTheDocument();
  });

  it('shows breached states with their icon', () => {
    renderUI(
      <SlaIndicator sla={sla({ level: 2, due_at: null, label: 'Breached' })} now={Date.now()} />,
    );
    expect(screen.getByText('Breached')).toBeInTheDocument();
    expect(screen.getByText('■')).toBeInTheDocument();
  });

  it('never shows levels to the requester', () => {
    render(<SlaIndicator sla={sla({ level: 3 })} requesterView />);
    expect(screen.queryByText('Escalated L3')).not.toBeInTheDocument();
    expect(screen.getByText('Awaiting first response')).toBeInTheDocument();
  });

  it('renders paused timers as neutral', () => {
    renderUI(<SlaIndicator sla={sla({ paused: true, label: 'Timer paused' })} />);
    expect(screen.getByText('Timer paused')).toBeInTheDocument();
    expect(screen.getByText('◷')).toBeInTheDocument();
  });
});

describe('SlaBanner', () => {
  it('is announced with role=status', () => {
    const { container } = render(<SlaBanner ticket={{ sla: sla() }} isRequester={false} />);
    expect(container.querySelector('[role="status"]')).not.toBeNull();
  });

  it('keeps the plain-text wording for requesters', () => {
    const { container } = render(
      <SlaBanner ticket={{ sla: sla({ level: 3 }) }} isRequester={true} />,
    );
    expect(container.textContent).toContain('Initial response due');
    expect(container.textContent).not.toContain('Escalated L3');
  });
});
