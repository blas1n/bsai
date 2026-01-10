'use client';

import { useCallback, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { McpServerResponse, McpServerTestResponse } from '@/types/mcp';

interface McpServerCardProps {
  server: McpServerResponse;
  testResult?: McpServerTestResponse;
  isTesting?: boolean;
  onEdit?: (server: McpServerResponse) => void;
  onDelete?: (server: McpServerResponse) => void;
  onTest?: (server: McpServerResponse) => void;
  onToggleActive?: (server: McpServerResponse) => void;
}

const transportIcons: Record<string, string> = {
  http: 'H',
  sse: 'S',
  stdio: 'T',
};

const transportLabels: Record<string, string> = {
  http: 'HTTP',
  sse: 'SSE',
  stdio: 'stdio',
};

export function McpServerCard({
  server,
  testResult,
  isTesting,
  onEdit,
  onDelete,
  onTest,
  onToggleActive,
}: McpServerCardProps) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const handleDelete = useCallback(() => {
    if (showDeleteConfirm) {
      onDelete?.(server);
      setShowDeleteConfirm(false);
    } else {
      setShowDeleteConfirm(true);
    }
  }, [showDeleteConfirm, onDelete, server]);

  const handleCancelDelete = useCallback(() => {
    setShowDeleteConfirm(false);
  }, []);

  return (
    <Card className={cn(
      'relative transition-opacity',
      !server.is_active && 'opacity-60'
    )}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <div className={cn(
              'flex h-8 w-8 items-center justify-center rounded-md text-sm font-bold',
              server.transport_type === 'http' && 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
              server.transport_type === 'sse' && 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
              server.transport_type === 'stdio' && 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300',
            )}>
              {transportIcons[server.transport_type]}
            </div>
            <div>
              <CardTitle className="text-base">{server.name}</CardTitle>
              <CardDescription className="text-xs">
                {transportLabels[server.transport_type]}
                {server.server_url && ` - ${new URL(server.server_url).host}`}
              </CardDescription>
            </div>
          </div>
          <div className={cn(
            'h-2 w-2 rounded-full',
            server.is_active ? 'bg-green-500' : 'bg-gray-400'
          )} />
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {server.description && (
          <p className="text-sm text-muted-foreground line-clamp-2">
            {server.description}
          </p>
        )}

        <div className="flex flex-wrap gap-1">
          {server.enabled_for_worker && (
            <span className="inline-flex items-center rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/50 dark:text-blue-300">
              Worker
            </span>
          )}
          {server.enabled_for_qa && (
            <span className="inline-flex items-center rounded-full bg-orange-50 px-2 py-0.5 text-xs font-medium text-orange-700 dark:bg-orange-900/50 dark:text-orange-300">
              QA
            </span>
          )}
          <span className={cn(
            'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
            server.require_approval === 'always' && 'bg-red-50 text-red-700 dark:bg-red-900/50 dark:text-red-300',
            server.require_approval === 'conditional' && 'bg-yellow-50 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300',
            server.require_approval === 'never' && 'bg-green-50 text-green-700 dark:bg-green-900/50 dark:text-green-300',
          )}>
            {server.require_approval === 'always' && 'Always approve'}
            {server.require_approval === 'conditional' && 'Conditional'}
            {server.require_approval === 'never' && 'Auto approve'}
          </span>
        </div>

        {server.available_tools && server.available_tools.length > 0 && (
          <div className="text-xs text-muted-foreground">
            {server.available_tools.length} tool{server.available_tools.length !== 1 && 's'} available
          </div>
        )}

        {testResult && (
          <div className={cn(
            'rounded-md p-2 text-xs',
            testResult.success
              ? 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300'
              : 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300'
          )}>
            {testResult.success ? (
              <span>Connected ({testResult.latency_ms}ms) - {testResult.available_tools?.length || 0} tools</span>
            ) : (
              <div className="space-y-1">
                <span className="font-medium">Test Failed</span>
                <p className="break-words">{testResult.error}</p>
              </div>
            )}
          </div>
        )}

        <div className="flex gap-2 pt-2">
          {server.transport_type !== 'stdio' && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onTest?.(server)}
              disabled={isTesting}
              className="flex-1"
            >
              {isTesting ? 'Testing...' : 'Test'}
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => onEdit?.(server)}
            className="flex-1"
          >
            Edit
          </Button>
          {showDeleteConfirm ? (
            <>
              <Button
                variant="destructive"
                size="sm"
                onClick={handleDelete}
              >
                Confirm
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleCancelDelete}
              >
                Cancel
              </Button>
            </>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleDelete}
              className="text-destructive hover:text-destructive"
            >
              Delete
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
