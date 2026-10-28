import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { Timeline } from '@/components/common/Timeline';
import type { TimelineEvent, UserRef } from '@/types/domain';

const rohan: UserRef = { id: 'u-rohan', name: 'Rohan Mehta', email: 'rohan.mehta@ibotix.ai' };
const asha: UserRef = { id: 'u-asha', name: 'Asha Verma', email: 'asha.verma@ibotix.ai' };

const events: TimelineEvent[] = [
  {
    id: 'e3',
    at: '2026-10-27T12:00:00.000Z',
    actor: rohan,
    type: 'comment',
    body: 'Working on it now.',
    public: true,
  },
  {
    id: 'e2',
    at: '2026-10-27T11:00:00.000Z',
    actor: rohan,
    type: 'internal_note',
    body: 'Vendor ticket #8821 raised.',
    public: false,
  },
  {
    id: 'e1',
    at: '2026-10-27T10:00:00.000Z',
    actor: { id: 'system', name: 'System' },
    type: 'audit',
    action: 'Escalation L2',
    detail: 'Initial response breached',
    public: false,
  },
];

describe('Timeline (spec 9.8)', () => {
  it('renders events oldest first for staff', () => {
    render(<Timeline events={events} isRequester={false} />);
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(within(items[0]!).getByText(/Escalation L2/)).toBeInTheDocument();
    expect(within(items[2]!).getByText('Working on it now.')).toBeInTheDocument();
  });

  it('shows internal notes to staff with a badge', () => {
    render(<Timeline events={events} isRequester={false} />);
    expect(screen.getByText('Vendor ticket #8821 raised.')).toBeInTheDocument();
    // The badge (and any accompanying description) mark the note as internal.
    expect(screen.getAllByText(/Internal note/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Includes internal notes and escalations/)).toBeInTheDocument();
  });

  it('hides internal notes and non-public events from the requester', () => {
    render(<Timeline events={events} isRequester={true} />);
    expect(screen.queryByText('Vendor ticket #8821 raised.')).not.toBeInTheDocument();
    expect(screen.queryByText(/Escalation L2/)).not.toBeInTheDocument();
    expect(screen.getByText('Working on it now.')).toBeInTheDocument();
    expect(screen.getByText(/Visible updates only/)).toBeInTheDocument();
  });

  it('never renders raw HTML from bodies (text only)', () => {
    const xss: TimelineEvent[] = [
      {
        id: 'x1',
        at: '2026-10-27T12:00:00.000Z',
        actor: asha,
        type: 'comment',
        body: '<img src=x onerror=alert(1)>',
        public: true,
      },
    ];
    const { container } = render(<Timeline events={xss} isRequester={false} />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
  });

  it('sorts ascending even when the API sends another order', () => {
    const shuffled = [events[0]!, events[2]!, events[1]!];
    render(<Timeline events={shuffled} isRequester={false} />);
    const items = screen.getAllByRole('listitem');
    expect(items[0]!.textContent).toContain('Escalation L2');
    expect(items[2]!.textContent).toContain('Working on it now.');
  });
});
