'use client';

import Link from 'next/link';
import { Clock, Coins, Hash, MessageSquare } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Session } from '@/types/session';
import { formatCurrency, formatNumber, formatRelativeTime } from '@/lib/utils';

interface SessionCardProps {
  session: Session;
  selectable?: boolean;
  selected?: boolean;
  onSelectChange?: (selected: boolean) => void;
}

function getStatusVariant(status: string) {
  switch (status) {
    case 'active':
      return 'success';
    case 'paused':
      return 'warning';
    case 'completed':
      return 'info';
    case 'failed':
      return 'destructive';
    default:
      return 'secondary';
  }
}

export function SessionCard({ session, selectable, selected, onSelectChange }: SessionCardProps) {
  const totalTokens = session.total_input_tokens + session.total_output_tokens;
  const displayTitle = session.title || 'New session';

  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onSelectChange?.(!selected);
  };

  return (
    <Link href={`/sessions/${session.id}`}>
      <Card className={`hover:bg-accent/50 transition-colors cursor-pointer ${selected ? 'ring-2 ring-primary' : ''}`}>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            {selectable && (
              <div onClick={handleCheckboxClick}>
                <Checkbox checked={selected} />
              </div>
            )}
            <div className="flex items-center min-w-0 flex-1">
              <MessageSquare className="mr-2 h-4 w-4 flex-shrink-0 text-muted-foreground" />
              <CardTitle className="text-sm font-medium truncate" title={displayTitle}>
                {displayTitle}
              </CardTitle>
            </div>
          </div>
          <Badge variant={getStatusVariant(session.status)} className="flex-shrink-0 ml-2">
            {session.status}
          </Badge>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col space-y-2 text-sm text-muted-foreground">
            <div className="flex items-center">
              <Hash className="mr-2 h-4 w-4" />
              <span>{formatNumber(totalTokens)} tokens</span>
            </div>
            <div className="flex items-center">
              <Coins className="mr-2 h-4 w-4" />
              <span>{formatCurrency(session.total_cost_usd)}</span>
            </div>
            <div className="flex items-center">
              <Clock className="mr-2 h-4 w-4" />
              <span>{formatRelativeTime(session.created_at)}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
