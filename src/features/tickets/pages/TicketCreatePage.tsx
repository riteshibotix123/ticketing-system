import { PageHeader } from '@/components/layout/PageHeader';
import { CreateTicketForm } from '../components/create/CreateTicketForm';

export default function TicketCreatePage() {
  return (
    <div className="mx-auto w-full max-w-2xl">
      <PageHeader
        title="New ticket"
        backTo="/tickets"
        backLabel="Back to tickets"
        description="Tell us what is happening. The team confirms priority."
      />
      <CreateTicketForm />
    </div>
  );
}
