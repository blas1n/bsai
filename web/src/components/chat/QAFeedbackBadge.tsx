'use client';

import { useState } from 'react';
import { Check, RefreshCw, X, ChevronDown, ChevronUp } from 'lucide-react';
import { QADecision, QA_DECISION_DISPLAY } from '@/types/chat';
import { cn } from '@/lib/utils';

interface QAFeedbackBadgeProps {
  decision: QADecision;
  feedback?: string;
  retryCount: number;
  maxRetries: number;
}

export function QAFeedbackBadge({
  decision,
  feedback,
  retryCount,
  maxRetries,
}: QAFeedbackBadgeProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const info = QA_DECISION_DISPLAY[decision];

  const Icon = {
    pass: Check,
    retry: RefreshCw,
    fail: X,
  }[decision];

  const colorClasses = {
    pass: 'bg-green-100 text-green-700 border-green-200',
    retry: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    fail: 'bg-red-100 text-red-700 border-red-200',
  }[decision];

  return (
    <div className="inline-block">
      <button
        onClick={() => feedback && setIsExpanded(!isExpanded)}
        className={cn(
          'flex items-center gap-1.5 px-2 py-1 rounded border text-xs font-medium',
          'transition-colors',
          colorClasses,
          feedback && 'cursor-pointer hover:opacity-80'
        )}
      >
        <Icon className="h-3 w-3" />
        <span>QA: {info.label}</span>
        {retryCount > 0 && (
          <span className="text-xs opacity-75">
            ({retryCount}/{maxRetries})
          </span>
        )}
        {feedback && (
          isExpanded ? (
            <ChevronUp className="h-3 w-3" />
          ) : (
            <ChevronDown className="h-3 w-3" />
          )
        )}
      </button>

      {/* Expanded Feedback */}
      {isExpanded && feedback && (
        <div
          className={cn(
            'mt-1 p-2 rounded border text-xs',
            colorClasses,
            'bg-opacity-50'
          )}
        >
          <p className="font-medium mb-1">QA Feedback:</p>
          <p className="whitespace-pre-wrap">{feedback}</p>
        </div>
      )}
    </div>
  );
}

// Summary badge for multiple QA results
export function QASummaryBadge({
  passed,
  retried,
  failed,
}: {
  passed: number;
  retried: number;
  failed: number;
}) {
  const total = passed + retried + failed;
  if (total === 0) return null;

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-muted-foreground">QA:</span>
      {passed > 0 && (
        <span className="flex items-center gap-1 text-green-600">
          <Check className="h-3 w-3" />
          {passed}
        </span>
      )}
      {retried > 0 && (
        <span className="flex items-center gap-1 text-yellow-600">
          <RefreshCw className="h-3 w-3" />
          {retried}
        </span>
      )}
      {failed > 0 && (
        <span className="flex items-center gap-1 text-red-600">
          <X className="h-3 w-3" />
          {failed}
        </span>
      )}
    </div>
  );
}
