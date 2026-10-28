import type { CreateTicketInput } from '@/lib/zod-schemas';

/**
 * Create-ticket draft persistence (spec 9.5). sessionStorage only, never
 * tokens (spec 18); every access is guarded because storage can be blocked
 * or full — losing a draft must never break the form.
 */
const DRAFT_KEY = 'ibotix-create-ticket-draft';

const PRIORITIES = ['low', 'medium', 'high', 'critical'] as const;

/** Restore only well-typed keys; anything else falls back to the defaults. */
export function readDraft(): Partial<CreateTicketInput> | null {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return null;
    const draft = parsed as Partial<CreateTicketInput>;
    return {
      department_id: typeof draft.department_id === 'string' ? draft.department_id : '',
      category_id: typeof draft.category_id === 'string' ? draft.category_id : '',
      title: typeof draft.title === 'string' ? draft.title : '',
      description: typeof draft.description === 'string' ? draft.description : '',
      priority:
        typeof draft.priority === 'string' &&
        PRIORITIES.includes(draft.priority as (typeof PRIORITIES)[number])
          ? (draft.priority as CreateTicketInput['priority'])
          : 'medium',
      confidential: draft.confidential === true,
    };
  } catch {
    return null;
  }
}

export function saveDraft(values: Partial<CreateTicketInput> | undefined): void {
  if (!values) return;
  try {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(values));
  } catch {
    // Storage unavailable: the form keeps working without the draft.
  }
}

/** Cleared after a successful submit (spec 9.5). */
export function clearDraft(): void {
  try {
    sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    // Nothing to do: the stale draft is replaced on the next change anyway.
  }
}
