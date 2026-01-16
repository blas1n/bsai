'use client';

import { useEffect } from 'react';
import { Brain, Clock, ExternalLink, Tag, Trash2, TrendingUp } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useMemoryStore } from '@/stores/memoryStore';
import { formatRelativeTime } from '@/lib/utils';
import type { Memory } from '@/types/memory';
import Link from 'next/link';

interface MemoryDetailDialogProps {
  memory: Memory | null;
  onClose: () => void;
  onDelete?: (memoryId: string) => void;
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

export function MemoryDetailDialog({ memory, onClose, onDelete }: MemoryDetailDialogProps) {
  const { currentMemory, fetchMemory, isLoading } = useMemoryStore();

  useEffect(() => {
    if (memory?.id) {
      fetchMemory(memory.id);
    }
  }, [memory?.id, fetchMemory]);

  const handleDelete = () => {
    if (memory && onDelete) {
      onDelete(memory.id);
      onClose();
    }
  };

  const displayMemory = currentMemory?.id === memory?.id ? currentMemory : memory;

  return (
    <Dialog open={!!memory} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-2 min-w-0 flex-1">
              <Brain className="mt-1 h-5 w-5 flex-shrink-0 text-muted-foreground" />
              <div>
                <DialogTitle className="text-lg">
                  {displayMemory?.summary}
                </DialogTitle>
                <DialogDescription className="mt-1">
                  Memory ID: {displayMemory?.id.slice(0, 8)}...
                </DialogDescription>
              </div>
            </div>
            <Badge variant={getTypeVariant(displayMemory?.memory_type || '')}>
              {getTypeLabel(displayMemory?.memory_type || '')}
            </Badge>
          </div>
        </DialogHeader>

        {displayMemory && (
          <div className="space-y-4 mt-4">
            {/* Metadata */}
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="flex items-center text-muted-foreground">
                <TrendingUp className="mr-2 h-4 w-4" />
                <span>Importance: {(displayMemory.importance_score * 100).toFixed(0)}%</span>
              </div>
              <div className="flex items-center text-muted-foreground">
                <Clock className="mr-2 h-4 w-4" />
                <span>Created: {formatRelativeTime(displayMemory.created_at)}</span>
              </div>
              {displayMemory.last_accessed_at && (
                <div className="flex items-center text-muted-foreground">
                  <Clock className="mr-2 h-4 w-4" />
                  <span>Last accessed: {formatRelativeTime(displayMemory.last_accessed_at)}</span>
                </div>
              )}
              <div className="flex items-center text-muted-foreground">
                <span>Access count: {displayMemory.access_count}</span>
              </div>
            </div>

            {/* Tags */}
            {displayMemory.tags && displayMemory.tags.length > 0 && (
              <div className="flex items-center flex-wrap gap-1">
                <Tag className="mr-1 h-4 w-4 text-muted-foreground" />
                {displayMemory.tags.map((tag: string) => (
                  <Badge key={tag} variant="outline">
                    {tag}
                  </Badge>
                ))}
              </div>
            )}

            {/* Links */}
            <div className="flex gap-2 text-sm">
              {displayMemory.session_id && (
                <Link
                  href={`/sessions/${displayMemory.session_id}`}
                  className="flex items-center text-primary hover:underline"
                  onClick={onClose}
                >
                  <ExternalLink className="mr-1 h-3 w-3" />
                  View Session
                </Link>
              )}
            </div>

            {/* Content */}
            {'content' in displayMemory && (displayMemory as { content?: string }).content && (
              <div className="space-y-2">
                <h4 className="font-medium">Content</h4>
                <div className="rounded-md bg-muted p-4 text-sm whitespace-pre-wrap">
                  {isLoading ? 'Loading...' : (displayMemory as { content: string }).content}
                </div>
              </div>
            )}

            {/* Metadata JSON */}
            {'metadata_json' in displayMemory && (displayMemory as { metadata_json?: Record<string, unknown> }).metadata_json && Object.keys((displayMemory as { metadata_json: Record<string, unknown> }).metadata_json).length > 0 && (
              <div className="space-y-2">
                <h4 className="font-medium">Metadata</h4>
                <div className="rounded-md bg-muted p-4 text-sm">
                  <pre className="whitespace-pre-wrap text-xs">
                    {JSON.stringify((displayMemory as { metadata_json: Record<string, unknown> }).metadata_json, null, 2)}
                  </pre>
                </div>
              </div>
            )}

            {/* Actions */}
            {onDelete && (
              <div className="flex justify-end pt-4 border-t">
                <Button variant="destructive" size="sm" onClick={handleDelete}>
                  <Trash2 className="mr-2 h-4 w-4" />
                  Delete Memory
                </Button>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
