'use client';

import { Coins, Zap } from 'lucide-react';
import { formatNumber, formatCurrency } from '@/lib/utils';

interface SessionStatsProps {
  totalTokens: number;
  totalCostUsd: number;
  inputTokens?: number;
  outputTokens?: number;
}

export function SessionStats({
  totalTokens,
  totalCostUsd,
  inputTokens,
  outputTokens,
}: SessionStatsProps) {
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center justify-between text-muted-foreground">
        <div className="flex items-center gap-1">
          <Zap className="h-3 w-3" />
          <span>Tokens</span>
        </div>
        <span className="font-medium text-foreground">
          {formatNumber(totalTokens)}
        </span>
      </div>
      {inputTokens !== undefined && outputTokens !== undefined && (
        <div className="flex items-center justify-between text-xs text-muted-foreground pl-4">
          <span>{formatNumber(inputTokens)} in / {formatNumber(outputTokens)} out</span>
        </div>
      )}
      <div className="flex items-center justify-between text-muted-foreground">
        <div className="flex items-center gap-1">
          <Coins className="h-3 w-3" />
          <span>Cost</span>
        </div>
        <span className="font-medium text-foreground">
          {formatCurrency(totalCostUsd)}
        </span>
      </div>
    </div>
  );
}
