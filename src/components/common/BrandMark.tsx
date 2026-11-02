import { cn } from '@/lib/cn';
import { APP_NAME } from '@/lib/constants';

type Tone = 'default' | 'ink' | 'auto';

function Logo({ variant, className }: { variant: 'navy' | 'white'; className?: string }) {
  return (
    <img
      src={variant === 'white' ? '/logo-white.svg' : '/logo.svg'}
      alt=""
      aria-hidden="true"
      width={118}
      height={22}
      className={cn('h-[22px] w-auto', className)}
      draggable={false}
    />
  );
}

/**
 * Ibotix logo (public/logo.svg) followed by the product label.
 * - `default`: navy logo, for light surfaces.
 * - `ink`: white logo (public/logo-white.svg), for always-dark surfaces such as the
 *   brand panel.
 * - `auto`: follows the theme (navy in light mode, white in dark mode), for the
 *   sidebar.
 */
export function BrandMark({ tone = 'default', className }: { tone?: Tone; className?: string }) {
  const product = APP_NAME.replace(/^Ibotix\s*/i, '') || 'Tickets';
  const labelClass = {
    default: 'border-line text-muted',
    ink: 'border-ink-line text-ink-muted',
    auto: 'border-side-line text-side-muted',
  }[tone];

  return (
    <span
      className={cn('inline-flex items-center gap-2.5', className)}
      role="img"
      aria-label={APP_NAME}
    >
      {tone === 'auto' ? (
        <>
          <Logo variant="navy" className="dark:hidden" />
          <Logo variant="white" className="hidden dark:block" />
        </>
      ) : (
        <Logo variant={tone === 'ink' ? 'white' : 'navy'} />
      )}
      <span
        aria-hidden="true"
        className={cn('border-l pl-2.5 text-[13px] font-semibold leading-none', labelClass)}
      >
        {product}
      </span>
    </span>
  );
}
