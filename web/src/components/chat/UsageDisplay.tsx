'use client';

import { Zap, Coins, Clock, Cpu } from 'lucide-react';
import { MessageUsage } from '@/types/chat';
import { formatNumber, formatCurrency } from '@/lib/utils';
import { cn } from '@/lib/utils';

interface UsageDisplayProps {
  usage: MessageUsage;
  className?: string;
  variant?: 'inline' | 'card';
}

export function UsageDisplay({
  usage,
  className,
  variant = 'inline',
}: UsageDisplayProps) {
  if (variant === 'card') {
    return (
      <div className={cn('rounded-lg border bg-card p-3', className)}>
        <h4 className="text-xs font-medium text-muted-foreground mb-2">Usage</h4>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="flex items-center gap-2">
            <Zap className="h-3 w-3 text-muted-foreground" />
            <span className="text-muted-foreground">Tokens:</span>
            <span className="font-medium">{formatNumber(usage.totalTokens)}</span>
          </div>
          <div className="flex items-center gap-2">
            <Coins className="h-3 w-3 text-muted-foreground" />
            <span className="text-muted-foreground">Cost:</span>
            <span className="font-medium">{formatCurrency(usage.costUsd)}</span>
          </div>
          <div className="flex items-center gap-2 col-span-2">
            <Cpu className="h-3 w-3 text-muted-foreground" />
            <span className="text-muted-foreground">Model:</span>
            <span className="font-medium">{usage.model}</span>
          </div>
          <div className="col-span-2 text-xs text-muted-foreground">
            {formatNumber(usage.inputTokens)} in / {formatNumber(usage.outputTokens)} out
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={cn('flex items-center gap-3 text-xs text-muted-foreground', className)}>
      <span className="flex items-center gap-1">
        <Zap className="h-3 w-3" />
        {formatNumber(usage.totalTokens)}
      </span>
      <span className="flex items-center gap-1">
        <Coins className="h-3 w-3" />
        {formatCurrency(usage.costUsd)}
      </span>
      <span className="flex items-center gap-1">
        <Cpu className="h-3 w-3" />
        {usage.model}
      </span>
    </div>
  );
}

// Floating usage indicator for bottom of chat
export function FloatingUsageIndicator({
  totalTokens,
  totalCostUsd,
  isVisible = true,
}: {
  totalTokens: number;
  totalCostUsd: number;
  isVisible?: boolean;
}) {
  if (!isVisible || (totalTokens === 0 && totalCostUsd === 0)) {
    return null;
  }

  return (
    <div className="fixed bottom-20 right-4 z-10">
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-background border shadow-lg text-xs">
        <span className="flex items-center gap-1">
          <Zap className="h-3 w-3 text-yellow-500" />
          {formatNumber(totalTokens)}
        </span>
        <span className="text-muted-foreground">|</span>
        <span className="flex items-center gap-1">
          <Coins className="h-3 w-3 text-green-500" />
          {formatCurrency(totalCostUsd)}
        </span>
      </div>
    </div>
  );
}
