'use client';

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { McpServerCard } from './McpServerCard';
import { McpServerForm } from './McpServerForm';
import { useMcpStore } from '@/stores/mcpStore';
import { useAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import type { McpServerResponse, McpServerDetailResponse, McpServerCreateRequest, McpServerUpdateRequest } from '@/types/mcp';

export function McpServerList() {
  const { accessToken } = useAuth();
  const {
    servers,
    testResults,
    isTesting,
    isLoading,
    isCreating,
    error,
    fetchServers,
    createServer,
    updateServer,
    deleteServer,
    testServer,
    clearError,
  } = useMcpStore();

  const [showForm, setShowForm] = useState(false);
  const [editingServer, setEditingServer] = useState<McpServerDetailResponse | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  useEffect(() => {
    if (accessToken) {
      api.setToken(accessToken);
      fetchServers();
    }
  }, [accessToken, fetchServers]);

  const handleCreate = useCallback(async (data: McpServerCreateRequest | McpServerUpdateRequest) => {
    await createServer(data as McpServerCreateRequest);
    setShowForm(false);
  }, [createServer]);

  const handleUpdate = useCallback(async (data: McpServerCreateRequest | McpServerUpdateRequest) => {
    if (editingServer) {
      await updateServer(editingServer.id, data as McpServerUpdateRequest);
      setEditingServer(null);
    }
  }, [editingServer, updateServer]);

  const handleEdit = useCallback(async (server: McpServerResponse) => {
    setIsLoadingDetail(true);
    try {
      const detail = await api.getMcpServer(server.id, true);
      setEditingServer(detail);
      setShowForm(false);
    } catch {
      // Fall back to basic server info
      setEditingServer(server);
      setShowForm(false);
    } finally {
      setIsLoadingDetail(false);
    }
  }, []);

  const handleDelete = useCallback(async (server: McpServerResponse) => {
    try {
      await deleteServer(server.id);
    } catch {
      // Error is handled by store
    }
  }, [deleteServer]);

  const handleTest = useCallback(async (server: McpServerResponse) => {
    try {
      await testServer(server.id);
    } catch {
      // Error is handled by store
    }
  }, [testServer]);

  const handleCancel = useCallback(() => {
    setShowForm(false);
    setEditingServer(null);
    clearError();
  }, [clearError]);

  if ((isLoading && servers.length === 0) || isLoadingDetail) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted-foreground">
          {isLoadingDetail ? 'Loading server details...' : 'Loading MCP servers...'}
        </div>
      </div>
    );
  }

  if (showForm) {
    return (
      <McpServerForm
        onSubmit={handleCreate}
        onCancel={handleCancel}
        isSubmitting={isCreating}
      />
    );
  }

  if (editingServer) {
    return (
      <McpServerForm
        server={editingServer}
        onSubmit={handleUpdate}
        onCancel={handleCancel}
        isSubmitting={false}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">MCP Servers</h2>
          <p className="text-sm text-muted-foreground">
            Manage Model Context Protocol servers for external tool integration
          </p>
        </div>
        <Button onClick={() => setShowForm(true)}>Add Server</Button>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300">
          {error}
          <button
            onClick={clearError}
            className="ml-2 underline hover:no-underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {servers.length === 0 ? (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <h3 className="text-lg font-medium">No MCP servers configured</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Add an MCP server to enable external tool integration for your agents.
          </p>
          <Button className="mt-4" onClick={() => setShowForm(true)}>
            Add Your First Server
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {servers.map((server) => (
            <McpServerCard
              key={server.id}
              server={server}
              testResult={testResults[server.id]}
              isTesting={isTesting[server.id]}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onTest={handleTest}
            />
          ))}
        </div>
      )}
    </div>
  );
}
