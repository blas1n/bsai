'use client';

import * as React from 'react';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CheckboxProps extends React.InputHTMLAttributes<HTMLInputElement> {
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
}

const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, checked, onCheckedChange, id, ...props }, ref) => {
    return (
      <div
        className={cn(
          'peer inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border border-primary cursor-pointer',
          checked && 'bg-primary text-primary-foreground',
          className
        )}
        onClick={() => onCheckedChange?.(!checked)}
      >
        <input
          type="checkbox"
          ref={ref}
          id={id}
          checked={checked}
          onChange={(e) => onCheckedChange?.(e.target.checked)}
          className="sr-only"
          {...props}
        />
        {checked && <Check className="h-3 w-3" />}
      </div>
    );
  }
);
Checkbox.displayName = 'Checkbox';

export { Checkbox };
