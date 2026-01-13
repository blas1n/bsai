'use client';

import { ExternalLink, Activity } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface LangfuseTraceLinkProps {
  /** The Langfuse trace URL */
  traceUrl: string | null | undefined;
  /** Optional variant for different display styles */
  variant?: 'badge' | 'button' | 'icon';
  /** Optional class name for styling */
  className?: string;
  /** Whether to show the full URL or just an icon */
  showLabel?: boolean;
}

/**
 * Component to display a link to Langfuse trace for debugging and observability.
 *
 * @example
 * // Badge style (default)
 * <LangfuseTraceLink traceUrl={message.traceUrl} />
 *
 * @example
 * // Button style
 * <LangfuseTraceLink traceUrl={message.traceUrl} variant="button" />
 *
 * @example
 * // Icon only
 * <LangfuseTraceLink traceUrl={message.traceUrl} variant="icon" />
 */
export function LangfuseTraceLink({
  traceUrl,
  variant = 'badge',
  className = '',
  showLabel = true,
}: LangfuseTraceLinkProps) {
  if (!traceUrl) {
    return null;
  }

  const handleClick = () => {
    window.open(traceUrl, '_blank', 'noopener,noreferrer');
  };

  if (variant === 'icon') {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={handleClick}
              className={`inline-flex items-center justify-center p-1 text-muted-foreground hover:text-primary transition-colors ${className}`}
              aria-label="View trace in Langfuse"
            >
              <Activity className="h-4 w-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent>
            <p>View trace in Langfuse</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  if (variant === 'button') {
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={handleClick}
        className={`gap-2 ${className}`}
      >
        <Activity className="h-4 w-4" />
        {showLabel && 'View Trace'}
        <ExternalLink className="h-3 w-3" />
      </Button>
    );
  }

  // Default: badge style
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant="outline"
            className={`cursor-pointer hover:bg-accent transition-colors gap-1 ${className}`}
            onClick={handleClick}
          >
            <Activity className="h-3 w-3" />
            {showLabel && <span>Trace</span>}
            <ExternalLink className="h-3 w-3" />
          </Badge>
        </TooltipTrigger>
        <TooltipContent>
          <p>View detailed trace in Langfuse</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export default LangfuseTraceLink;
