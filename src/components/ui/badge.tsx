import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/cn';

const badgeVariants = cva(
  'inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-small font-medium',
  {
    variants: {
      variant: {
        outline: 'border border-line bg-transparent text-muted',
        solid: 'bg-surface-2 text-fg',
        ok: 'border border-ok/40 bg-ok-soft text-ok',
        warn: 'border border-warn/40 bg-warn-soft text-warn',
        crit: 'border border-crit/40 bg-crit-soft text-crit',
        info: 'border border-info/40 bg-info-soft text-info',
        accent: 'border border-accent/40 bg-accent-soft text-accent',
        muted: 'border border-line bg-surface-2 text-muted',
      },
    },
    defaultVariants: { variant: 'outline' },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { badgeVariants };
