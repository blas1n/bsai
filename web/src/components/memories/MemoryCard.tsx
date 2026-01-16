'use client';

import { Brain, Clock, Tag, Trash2, TrendingUp } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { Memory } from '@/types/memory';
import { formatRelativeTime } from '@/lib/utils';

interface MemoryCardProps {
  memory: Memory;
  onSelect?: (memory: Memory) => void;
  onDelete?: (memoryId: string) => void;
  showSimilarity?: number;
}

function getTypeVariant(memoryType: string) {
  switch (memoryType) {
    case 'task_result':
      return 'success';
    case 'learning':
      return 'info';
    case 'error':
      return 'destructive';
    case 'user_preference':
      return 'warning';
    default:
      return 'secondary';
  }
}

function getTypeLabel(memoryType: string) {
  switch (memoryType) {
    case 'task_result':
      return 'Task Result';
    case 'learning':
      return 'Learning';
    case 'error':
      return 'Error';
    case 'user_preference':
      return 'Preference';
    default:
      return memoryType;
  }
}

export function MemoryCard({ memory, onSelect, onDelete, showSimilarity }: MemoryCardProps) {
  const handleClick = () => {
    onSelect?.(memory);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete?.(memory.id);
  };

  return (
    <Card
      className={`transition-colors ${onSelect ? 'hover:bg-accent/50 cursor-pointer' : ''}`}
      onClick={onSelect ? handleClick : undefined}
    >
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
        <div className="flex items-start gap-2 min-w-0 flex-1">
          <Brain className="mt-0.5 h-4 w-4 flex-shrink-0 text-muted-foreground" />
          <CardTitle className="text-sm font-medium line-clamp-2">
            {memory.summary}
          </CardTitle>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0 ml-2">
          <Badge variant={getTypeVariant(memory.memory_type)}>
            {getTypeLabel(memory.memory_type)}
          </Badge>
          {onDelete && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-muted-foreground hover:text-destructive"
              onClick={handleDelete}
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col space-y-2 text-sm text-muted-foreground">
          <div className="flex items-center">
            <TrendingUp className="mr-2 h-4 w-4" />
            <span>Importance: {(memory.importance_score * 100).toFixed(0)}%</span>
            {showSimilarity !== undefined && (
              <span className="ml-4 text-primary">
                Similarity: {(showSimilarity * 100).toFixed(0)}%
              </span>
            )}
          </div>
          {memory.tags && memory.tags.length > 0 && (
            <div className="flex items-center flex-wrap gap-1">
              <Tag className="mr-1 h-4 w-4" />
              {memory.tags.slice(0, 3).map((tag) => (
                <Badge key={tag} variant="outline" className="text-xs">
                  {tag}
                </Badge>
              ))}
              {memory.tags.length > 3 && (
                <span className="text-xs">+{memory.tags.length - 3}</span>
              )}
            </div>
          )}
          <div className="flex items-center">
            <Clock className="mr-2 h-4 w-4" />
            <span>{formatRelativeTime(memory.created_at)}</span>
            {memory.access_count > 0 && (
              <span className="ml-4">Accessed {memory.access_count}x</span>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
