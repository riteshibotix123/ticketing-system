import { createContext, useContext } from 'react';

export interface FieldContextValue {
  /** Generated id shared with the FormField label. */
  id: string;
  describedBy?: string;
  invalid: boolean;
}

/**
 * Shared between FormField (which sets it) and the ui controls (Input,
 * Textarea, SelectTrigger, Checkbox — which read it), so a plain
 * `<FormField label=…><Input/></FormField>` produces a correctly associated
 * label, `aria-invalid` and `aria-describedby` without extra wiring.
 */
export const FieldContext = createContext<FieldContextValue | null>(null);

export function useField(): FieldContextValue | null {
  return useContext(FieldContext);
}
