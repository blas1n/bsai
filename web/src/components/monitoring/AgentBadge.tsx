'use client';

import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AgentType, AGENT_DISPLAY } from '@/types/chat';
import { AGENT_ICONS, AGENT_BADGE_COLORS } from '@/lib/agentConstants';

interface AgentBadgeProps {
  agent: AgentType;
  isActive?: boolean;
}

export function AgentBadge({ agent, isActive }: AgentBadgeProps) {
  const display = AGENT_DISPLAY[agent];
  const colorClasses = AGENT_BADGE_COLORS[agent];

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border',
        colorClasses,
        isActive && 'ring-2 ring-offset-2 ring-offset-background'
      )}
    >
      {AGENT_ICONS[agent]}
      <span>{display.label}</span>
      {isActive && <Loader2 className="h-3 w-3 animate-spin" />}
    </div>
  );
}
