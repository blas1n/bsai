'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

interface RadioGroupProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: string;
  onValueChange?: (value: string) => void;
}

const RadioGroupContext = React.createContext<{
  value?: string;
  onValueChange?: (value: string) => void;
}>({});

const RadioGroup = React.forwardRef<HTMLDivElement, RadioGroupProps>(
  ({ className, value, onValueChange, children, ...props }, ref) => {
    return (
      <RadioGroupContext.Provider value={{ value, onValueChange }}>
        <div
          ref={ref}
          role="radiogroup"
          className={cn('grid gap-2', className)}
          {...props}
        >
          {children}
        </div>
      </RadioGroupContext.Provider>
    );
  }
);
RadioGroup.displayName = 'RadioGroup';

interface RadioGroupItemProps extends React.InputHTMLAttributes<HTMLInputElement> {
  value: string;
}

const RadioGroupItem = React.forwardRef<HTMLInputElement, RadioGroupItemProps>(
  ({ className, value, id, ...props }, ref) => {
    const context = React.useContext(RadioGroupContext);
    const isChecked = context.value === value;

    return (
      <div
        className={cn(
          'aspect-square h-4 w-4 rounded-full border border-primary cursor-pointer',
          isChecked && 'border-primary bg-primary',
          className
        )}
        onClick={() => context.onValueChange?.(value)}
      >
        <input
          type="radio"
          ref={ref}
          id={id}
          value={value}
          checked={isChecked}
          onChange={() => context.onValueChange?.(value)}
          className="sr-only"
          {...props}
        />
        {isChecked && (
          <div className="flex items-center justify-center w-full h-full">
            <div className="h-2 w-2 rounded-full bg-primary-foreground" />
          </div>
        )}
      </div>
    );
  }
);
RadioGroupItem.displayName = 'RadioGroupItem';

export { RadioGroup, RadioGroupItem };
