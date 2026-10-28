import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { errorMessage, isApiError } from '@/api/client';
import { usersApi } from '@/api/endpoints/users';
import { queryKeys } from '@/api/queryKeys';
import { FormField } from '@/components/common/FormField';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useToast } from '@/hooks/useToast';
import { emailSchema } from '@/lib/zod-schemas';

const addAdminSchema = z.object({
  name: z.string().trim().min(2, 'Enter a name.').max(120, 'Too long.'),
  email: emailSchema,
});
type AddAdminInput = z.infer<typeof addAdminSchema>;

/** "Add Admin" dialog (spec 9.13): name + email → invitation. */
export function AddAdminDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { success } = useToast();
  const qc = useQueryClient();
  const [serverError, setServerError] = useState<string | null>(null);

  const { register, handleSubmit, setError, formState, reset } = useForm<AddAdminInput>({
    resolver: zodResolver(addAdminSchema),
    defaultValues: { name: '', email: '' },
  });

  const mutation = useMutation({
    mutationFn: (values: AddAdminInput) => usersApi.createAdmin(values),
    onSuccess: () => {
      success('Admin invitation sent.');
      void qc.invalidateQueries({ queryKey: queryKeys.admins });
      reset();
      setServerError(null);
      onOpenChange(false);
    },
    onError: (err) => {
      setServerError(errorMessage(err));
      if (isApiError(err) && err.fields) {
        for (const [key, message] of Object.entries(err.fields)) {
          if (key === 'name' || key === 'email') setError(key, { message });
        }
      }
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!mutation.isPending) {
          setServerError(null);
          onOpenChange(v);
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Admin</DialogTitle>
          <DialogDescription>
            An invitation email is sent. The account becomes an Admin after signup and approval.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={handleSubmit((values) => mutation.mutate(values))}
          className="flex flex-col gap-4"
        >
          <FormField label="Full name" required error={formState.errors.name?.message}>
            <Input
              {...register('name')}
              placeholder="e.g. Priya Nair"
              maxLength={120}
              disabled={mutation.isPending}
              aria-invalid={formState.errors.name ? true : undefined}
            />
          </FormField>
          <FormField label="Company email" required error={formState.errors.email?.message}>
            <Input
              {...register('email')}
              type="email"
              placeholder="name@ibotix.ai"
              disabled={mutation.isPending}
              aria-invalid={formState.errors.email ? true : undefined}
            />
          </FormField>

          {serverError ? (
            <p role="alert" className="text-small text-crit">
              {serverError}
            </p>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              loading={mutation.isPending}
              loadingLabel="Sending"
            >
              Send invitation
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
