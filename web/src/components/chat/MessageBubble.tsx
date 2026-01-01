'use client';

import { User, Bot, Info, Loader2, Brain, Sparkles, Cog, CheckCircle, FileText, MessageCircle } from 'lucide-react';
import { ChatMessage, AgentActivity, AgentType, AGENT_DISPLAY } from '@/types/chat';
import { cn, formatCurrency, formatNumber } from '@/lib/utils';
import { QAFeedbackBadge } from './QAFeedbackBadge';
import { MilestoneProgressCard } from './MilestoneProgressCard';
import { Badge } from '@/components/ui/badge';

interface MessageBubbleProps {
  message: ChatMessage;
  showDetails?: boolean;
  currentActivity?: AgentActivity | null;
  agentHistory?: AgentActivity[];
}

const AGENT_ICONS: Record<AgentType, React.ReactNode> = {
  conductor: <Brain className="h-4 w-4" />,
  meta_prompter: <Sparkles className="h-4 w-4" />,
  worker: <Cog className="h-4 w-4" />,
  qa: <CheckCircle className="h-4 w-4" />,
  summarizer: <FileText className="h-4 w-4" />,
  responder: <MessageCircle className="h-4 w-4" />,
};

const AGENT_COLORS: Record<AgentType, string> = {
  conductor: 'text-blue-500',
  meta_prompter: 'text-purple-500',
  worker: 'text-green-500',
  qa: 'text-orange-500',
  summarizer: 'text-gray-500',
  responder: 'text-teal-500',
};

export function MessageBubble({
  message,
  showDetails = true,
  currentActivity,
  agentHistory = [],
}: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const isAssistant = message.role === 'assistant';

  if (isSystem) {
    return (
      <div className="flex justify-center py-2">
        <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-muted text-xs text-muted-foreground">
          <Info className="h-3 w-3" />
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'flex gap-3 py-4',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center',
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted'
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* Content */}
      <div
        className={cn(
          'flex flex-col gap-2 max-w-[80%]',
          isUser ? 'items-end' : 'items-start'
        )}
      >
        {/* Current Activity Indicator (simplified - details shown in right panel) */}
        {isAssistant && message.isStreaming && currentActivity && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary/5 border border-primary/20 text-sm">
            <div className={cn('flex-shrink-0', AGENT_COLORS[currentActivity.agent])}>
              {AGENT_ICONS[currentActivity.agent]}
            </div>
            <span className="font-medium">
              {AGENT_DISPLAY[currentActivity.agent].label}
            </span>
            {currentActivity.status === 'running' ? (
              <Loader2 className="h-3 w-3 animate-spin text-primary" />
            ) : (
              <CheckCircle className="h-3 w-3 text-green-500" />
            )}
            <span className="text-xs text-muted-foreground truncate">
              {currentActivity.message || 'Processing...'}
            </span>
          </div>
        )}
        {/* Show thinking indicator when streaming but no activity yet */}
        {isAssistant && message.isStreaming && !currentActivity && !message.content && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary/5 border border-primary/20 text-sm">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            <span className="text-muted-foreground">Thinking...</span>
          </div>
        )}

        {/* Message Content */}
        {(!message.isStreaming || message.content) && (
          <div
            className={cn(
              'rounded-lg px-4 py-2',
              isUser
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted'
            )}
          >
            <div className="whitespace-pre-wrap break-words">{message.content}</div>
          </div>
        )}

        {/* Milestone Progress (for assistant messages with milestones) */}
        {isAssistant && showDetails && message.milestones && message.milestones.length > 0 && (
          <MilestoneProgressCard milestones={message.milestones} />
        )}

        {/* Usage Stats (for completed assistant messages) */}
        {isAssistant && showDetails && message.usage && !message.isStreaming && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="outline" className="text-xs">
              {formatNumber(message.usage.totalTokens)} tokens
            </Badge>
            <Badge variant="outline" className="text-xs">
              {formatCurrency(message.usage.costUsd)}
            </Badge>
            {message.usage.model && (
              <Badge variant="outline" className="text-xs">
                {message.usage.model}
              </Badge>
            )}
          </div>
        )}

        {/* QA Results (if any milestone has QA feedback) */}
        {isAssistant && showDetails && message.milestones?.some((m) => m.qaResult) && (
          <div className="flex flex-wrap gap-1">
            {message.milestones
              .filter((m) => m.qaResult)
              .map((milestone) => (
                <QAFeedbackBadge
                  key={milestone.id}
                  decision={milestone.qaResult!.decision}
                  feedback={milestone.qaResult!.feedback}
                  retryCount={milestone.qaResult!.retryCount}
                  maxRetries={milestone.qaResult!.maxRetries}
                />
              ))}
          </div>
        )}
      </div>
    </div>
  );
}
