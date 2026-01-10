'use client';

import { useCallback, useEffect, useState, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { ExternalLink, CheckCircle, Loader2 } from 'lucide-react';
import type {
  McpServerDetailResponse,
  McpServerCreateRequest,
  McpServerUpdateRequest,
  TransportType,
  AuthType,
  ApprovalMode,
} from '@/types/mcp';

interface McpServerFormProps {
  server?: McpServerDetailResponse;
  onSubmit: (data: McpServerCreateRequest | McpServerUpdateRequest) => Promise<void>;
  onCancel: () => void;
  isSubmitting?: boolean;
}

const transportOptions: { value: TransportType; label: string; description: string }[] = [
  { value: 'http', label: 'HTTP', description: 'Standard HTTP endpoint' },
  { value: 'sse', label: 'SSE', description: 'Server-Sent Events' },
];

const authOptions: { value: AuthType; label: string; description?: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'bearer', label: 'Bearer Token' },
  { value: 'api_key', label: 'API Key' },
  { value: 'oauth2', label: 'OAuth2', description: 'Authenticate via popup' },
];

const approvalOptions: { value: ApprovalMode; label: string; description: string }[] = [
  { value: 'always', label: 'Always', description: 'Require approval for all tools' },
  { value: 'conditional', label: 'Conditional', description: 'Require approval for risky tools' },
  { value: 'never', label: 'Never', description: 'Auto-approve all tools' },
];

export function McpServerForm({
  server,
  onSubmit,
  onCancel,
  isSubmitting,
}: McpServerFormProps) {
  const isEditing = !!server;

  const [name, setName] = useState(server?.name || '');
  const [description, setDescription] = useState(server?.description || '');
  const [transportType, setTransportType] = useState<TransportType>(server?.transport_type || 'sse');

  // HTTP/SSE fields
  const [serverUrl, setServerUrl] = useState(server?.server_url || '');
  const [authType, setAuthType] = useState<AuthType>(server?.auth_type || 'none');
  const [bearerToken, setBearerToken] = useState('');
  const [apiKeyHeader, setApiKeyHeader] = useState('X-API-Key');
  const [apiKeyValue, setApiKeyValue] = useState('');

  // Configuration
  const [availableTools, setAvailableTools] = useState(server?.available_tools?.join(', ') || '');
  const [requireApproval, setRequireApproval] = useState<ApprovalMode>(server?.require_approval || 'conditional');
  const [enabledForWorker, setEnabledForWorker] = useState(server?.enabled_for_worker ?? true);
  const [enabledForQa, setEnabledForQa] = useState(server?.enabled_for_qa ?? true);

  // OAuth state
  const [oauthState, setOauthState] = useState<string | null>(null);
  const [isOauthLoading, setIsOauthLoading] = useState(false);
  const [oauthAuthenticated, setOauthAuthenticated] = useState(false);
  const [oauthError, setOauthError] = useState<string | null>(null);
  const oauthWindowRef = useRef<Window | null>(null);

  const [error, setError] = useState<string | null>(null);

  // Check OAuth status when editing existing server
  useEffect(() => {
    if (server?.id && server?.auth_type === 'oauth2') {
      api.getMcpOAuthStatus(server.id).then((status) => {
        setOauthAuthenticated(status.has_oauth_tokens);
      }).catch((err) => {
        console.error('Failed to check OAuth status:', err);
      });
    }
  }, [server?.id, server?.auth_type]);

  // Listen for OAuth callback messages from popup
  useEffect(() => {
    const handleMessage = async (event: MessageEvent) => {
      if (event.data?.type === 'mcp-oauth-callback') {
        const { code, state: callbackState, error: callbackError } = event.data;

        if (callbackError) {
          setOauthError(callbackError);
          setIsOauthLoading(false);
          return;
        }

        if (callbackState !== oauthState) {
          setOauthError('OAuth state mismatch. Please try again.');
          setIsOauthLoading(false);
          return;
        }

        // Server ID is needed for callback - if editing, use existing ID
        // If creating new server, we need to save first (handled in submit flow)
        if (server?.id) {
          try {
            const result = await api.completeMcpOAuth({
              code,
              state: callbackState,
              server_id: server.id,
            });

            if (result.success) {
              setOauthAuthenticated(true);
              setOauthError(null);
            } else {
              setOauthError(result.error || 'OAuth authentication failed');
            }
          } catch (err) {
            setOauthError(err instanceof Error ? err.message : 'OAuth authentication failed');
          }
        } else {
          // For new servers, store the code and state for later
          setOauthAuthenticated(true);
        }

        setIsOauthLoading(false);
        oauthWindowRef.current?.close();
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [oauthState, server?.id]);

  const handleStartOAuth = useCallback(async (isReauth = false) => {
    if (!serverUrl.trim()) {
      setOauthError('Please enter the server URL first');
      return;
    }

    setIsOauthLoading(true);
    setOauthError(null);

    try {
      const callbackUrl = `${window.location.origin}/settings/mcp/oauth-callback`;

      // Use reauth endpoint if re-authenticating an existing server
      const result = isReauth && server?.id
        ? await api.reauthMcpServer(server.id, {
            server_url: serverUrl.trim(),
            callback_url: callbackUrl,
          })
        : await api.startMcpOAuth({
            server_url: serverUrl.trim(),
            callback_url: callbackUrl,
          });

      setOauthState(result.state);

      // Open OAuth popup
      const width = 600;
      const height = 700;
      const left = window.screenX + (window.outerWidth - width) / 2;
      const top = window.screenY + (window.outerHeight - height) / 2;

      oauthWindowRef.current = window.open(
        result.authorization_url,
        'mcp-oauth',
        `width=${width},height=${height},left=${left},top=${top},popup=true`
      );

      // Check if popup was blocked
      if (!oauthWindowRef.current) {
        setOauthError('Popup was blocked. Please allow popups for this site.');
        setIsOauthLoading(false);
      }
    } catch (err) {
      setOauthError(err instanceof Error ? err.message : 'Failed to start OAuth flow');
      setIsOauthLoading(false);
    }
  }, [serverUrl, server?.id]);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validation
    if (!name.trim()) {
      setError('Name is required');
      return;
    }

    if (!serverUrl.trim()) {
      setError('Server URL is required');
      return;
    }

    const data: McpServerCreateRequest | McpServerUpdateRequest = {
      name: name.trim(),
      description: description.trim() || undefined,
      require_approval: requireApproval,
      enabled_for_worker: enabledForWorker,
      enabled_for_qa: enabledForQa,
      available_tools: availableTools.trim()
        ? availableTools.split(',').map((t) => t.trim()).filter(Boolean)
        : undefined,
    };

    if (!isEditing) {
      (data as McpServerCreateRequest).transport_type = transportType;
    }

    data.server_url = serverUrl.trim();
    data.auth_type = authType;

    if (authType === 'bearer' && bearerToken) {
      data.auth_credentials = { token: bearerToken };
    } else if (authType === 'api_key' && apiKeyValue) {
      data.auth_credentials = {
        header_name: apiKeyHeader,
        api_key: apiKeyValue,
      };
    }

    try {
      await onSubmit(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save server');
    }
  }, [
    name, description, transportType, serverUrl, authType, bearerToken,
    apiKeyHeader, apiKeyValue, availableTools,
    requireApproval, enabledForWorker, enabledForQa, isEditing, onSubmit
  ]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{isEditing ? 'Edit MCP Server' : 'Add MCP Server'}</CardTitle>
        <CardDescription>
          {isEditing
            ? 'Update the MCP server configuration'
            : 'Configure a new MCP server for tool integration'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300">
              {error}
            </div>
          )}

          {/* Basic Info */}
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Name *</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                placeholder="My MCP Server"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Description</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                rows={2}
                placeholder="Optional description"
              />
            </div>
          </div>

          {/* Transport Type */}
          {!isEditing && (
            <div>
              <label className="block text-sm font-medium mb-2">Transport Type *</label>
              <div className="grid grid-cols-2 gap-2">
                {transportOptions.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setTransportType(option.value)}
                    className={cn(
                      'rounded-md border p-3 text-left transition-colors',
                      transportType === option.value
                        ? 'border-primary bg-primary/5'
                        : 'border-input hover:border-primary/50'
                    )}
                  >
                    <div className="font-medium text-sm">{option.label}</div>
                    <div className="text-xs text-muted-foreground">{option.description}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Server Connection */}
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Server URL *</label>
              <input
                type="url"
                value={serverUrl}
                onChange={(e) => setServerUrl(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                placeholder="https://api.example.com/mcp"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Authentication</label>
              <div className="flex gap-2">
                {authOptions.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setAuthType(option.value)}
                    className={cn(
                      'rounded-md border px-3 py-1.5 text-sm transition-colors',
                      authType === option.value
                        ? 'border-primary bg-primary/5'
                        : 'border-input hover:border-primary/50'
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            {authType === 'bearer' && (
              <div>
                <label className="block text-sm font-medium mb-1">Bearer Token</label>
                <input
                  type="password"
                  value={bearerToken}
                  onChange={(e) => setBearerToken(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  placeholder="Enter token"
                />
              </div>
            )}

            {authType === 'api_key' && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Header Name</label>
                  <input
                    type="text"
                    value={apiKeyHeader}
                    onChange={(e) => setApiKeyHeader(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">API Key</label>
                  <input
                    type="password"
                    value={apiKeyValue}
                    onChange={(e) => setApiKeyValue(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    placeholder="Enter API key"
                  />
                </div>
              </div>
            )}

            {authType === 'oauth2' && (
              <div className="rounded-md border border-input p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-sm">OAuth2 Authentication</div>
                    <div className="text-xs text-muted-foreground">
                      {oauthAuthenticated
                        ? 'Connected to MCP server'
                        : 'Click to authenticate with the MCP server'}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {oauthAuthenticated && (
                      <div className="flex items-center gap-1 text-green-600 dark:text-green-400">
                        <CheckCircle className="h-4 w-4" />
                        <span className="text-sm">Authenticated</span>
                      </div>
                    )}
                    {oauthAuthenticated && server?.id ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => handleStartOAuth(true)}
                        disabled={isOauthLoading || !serverUrl.trim()}
                      >
                        {isOauthLoading ? (
                          <>
                            <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                            Re-authenticating...
                          </>
                        ) : (
                          <>
                            <ExternalLink className="h-4 w-4 mr-1" />
                            Re-authenticate
                          </>
                        )}
                      </Button>
                    ) : !oauthAuthenticated && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => handleStartOAuth(false)}
                        disabled={isOauthLoading || !serverUrl.trim()}
                      >
                        {isOauthLoading ? (
                          <>
                            <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                            Authenticating...
                          </>
                        ) : (
                          <>
                            <ExternalLink className="h-4 w-4 mr-1" />
                            Authenticate
                          </>
                        )}
                      </Button>
                    )}
                  </div>
                </div>
                {oauthError && (
                  <div className="text-xs text-red-600 dark:text-red-400">
                    {oauthError}
                  </div>
                )}
                {!serverUrl.trim() && authType === 'oauth2' && (
                  <div className="text-xs text-amber-600 dark:text-amber-400">
                    Enter the server URL first to enable OAuth authentication
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Tool Configuration */}
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Available Tools (comma-separated)</label>
              <input
                type="text"
                value={availableTools}
                onChange={(e) => setAvailableTools(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                placeholder="Leave empty to allow all tools"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Filter which tools from this server can be used. Leave empty to allow all.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Approval Mode</label>
              <div className="space-y-2">
                {approvalOptions.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setRequireApproval(option.value)}
                    className={cn(
                      'w-full rounded-md border p-3 text-left transition-colors',
                      requireApproval === option.value
                        ? 'border-primary bg-primary/5'
                        : 'border-input hover:border-primary/50'
                    )}
                  >
                    <div className="font-medium text-sm">{option.label}</div>
                    <div className="text-xs text-muted-foreground">{option.description}</div>
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-3">
              <label className="block text-sm font-medium">Enable for Agents</label>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="worker"
                  checked={enabledForWorker}
                  onCheckedChange={(checked) => setEnabledForWorker(checked === true)}
                />
                <label htmlFor="worker" className="text-sm">Worker Agent</label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="qa"
                  checked={enabledForQa}
                  onCheckedChange={(checked) => setEnabledForQa(checked === true)}
                />
                <label htmlFor="qa" className="text-sm">QA Agent</label>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-2 pt-4">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving...' : isEditing ? 'Update Server' : 'Add Server'}
            </Button>
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
