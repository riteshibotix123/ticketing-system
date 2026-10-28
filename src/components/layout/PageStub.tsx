import { PageHeader } from '@/components/layout/PageHeader';

/** Temporary placeholder rendered until a feature page is implemented. */
export function PageStub({ title, description }: { title: string; description?: string }) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <div className="card flex items-center justify-center px-6 py-16 text-small text-muted">
        This screen is being built.
      </div>
    </>
  );
}
