'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Coins, TrendingUp, TrendingDown, ArrowRight } from 'lucide-react';
import { formatCurrency } from '@/lib/utils';

interface CostTrackerProps {
  totalCost: number;
  dailyCost: number;
  dailyLimit: number;
  sessions: number;
}

export function CostTracker({
  totalCost,
  dailyCost,
  dailyLimit,
  sessions,
}: CostTrackerProps) {
  const usagePercent = (dailyCost / dailyLimit) * 100;
  const isNearLimit = usagePercent > 80;
  const isOverLimit = usagePercent > 100;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Coins className="h-5 w-5" />
          Cost Tracking
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">Total Cost</p>
            <p className="text-2xl font-bold">{formatCurrency(totalCost)}</p>
          </div>

          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">Today&apos;s Cost</p>
            <div className="flex items-center gap-2">
              <p className="text-2xl font-bold">{formatCurrency(dailyCost)}</p>
              {isNearLimit && !isOverLimit && (
                <TrendingUp className="h-5 w-5 text-yellow-500" />
              )}
              {isOverLimit && (
                <TrendingDown className="h-5 w-5 text-red-500" />
              )}
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">Daily Limit</p>
            <div className="flex items-center gap-2">
              <p className="text-2xl font-bold">{formatCurrency(dailyLimit)}</p>
              <span className="text-sm text-muted-foreground">
                ({usagePercent.toFixed(0)}% used)
              </span>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">Active Sessions</p>
            <p className="text-2xl font-bold">{sessions}</p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mt-6">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-muted-foreground">Daily Usage</span>
            <span
              className={
                isOverLimit
                  ? 'text-red-500'
                  : isNearLimit
                  ? 'text-yellow-500'
                  : 'text-green-500'
              }
            >
              {formatCurrency(dailyCost)} / {formatCurrency(dailyLimit)}
            </span>
          </div>
          <div className="w-full bg-secondary rounded-full h-3">
            <div
              className={`h-3 rounded-full transition-all ${
                isOverLimit
                  ? 'bg-red-500'
                  : isNearLimit
                  ? 'bg-yellow-500'
                  : 'bg-green-500'
              }`}
              style={{ width: `${Math.min(usagePercent, 100)}%` }}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
