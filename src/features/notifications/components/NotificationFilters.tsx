import { ViewTabs } from '@/components/common/ViewTabs';

export type NotificationFilter = 'all' | 'unread';

/** "All / Unread" toggle (spec 9.10), synced to ?filter= by the page. */
export function NotificationFilters({
  value,
  onChange,
}: {
  value: NotificationFilter;
  onChange: (value: NotificationFilter) => void;
}) {
  return (
    <ViewTabs
      label="Notification filter"
      value={value}
      onChange={(next) => {
        // Values come from the two tabs rendered below.
        onChange(next as NotificationFilter);
      }}
      items={[
        { id: 'all', label: 'All' },
        { id: 'unread', label: 'Unread' },
      ]}
    />
  );
}
