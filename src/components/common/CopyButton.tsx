import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/useToast';

/**
 * Clipboard copy with a fallback (execCommand) and a toast.
 * Used for ticket IDs.
 */
export function CopyButton({
  value,
  label = 'Copy',
  className,
}: {
  value: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const { toast } = useToast();

  async function copy() {
    let ok = false;
    try {
      await navigator.clipboard.writeText(value);
      ok = true;
    } catch {
      try {
        const el = document.createElement('textarea');
        el.value = value;
        el.setAttribute('readonly', '');
        el.style.position = 'fixed';
        el.style.opacity = '0';
        document.body.appendChild(el);
        el.select();
        ok = document.execCommand('copy');
        document.body.removeChild(el);
      } catch {
        ok = false;
      }
    }
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
      toast({ title: 'Copied to clipboard.', variant: 'success' });
    } else {
      toast({
        title: 'Could not copy.',
        description: 'Your browser blocked clipboard access.',
        variant: 'error',
      });
    }
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="iconSm"
      onClick={copy}
      className={className}
      aria-label={copied ? 'Copied' : `${label} ${value}`}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-ok" aria-hidden="true" />
      ) : (
        <Copy className="h-3.5 w-3.5" aria-hidden="true" />
      )}
    </Button>
  );
}
