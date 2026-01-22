'use client';

import { useRef, useEffect, useState, useMemo } from 'react';
import { useChat } from '@/hooks/useChat';
import { useAuth } from '@/hooks/useAuth';
import { ChatInput } from './ChatInput';
import { MessageBubble } from './MessageBubble';
import { FloatingUsageIndicator } from './UsageDisplay';
import { Sidebar } from '@/components/sidebar';
import { AgentMonitorPanel } from '@/components/monitoring/AgentMonitorPanel';
import { LiveDetailPanel } from '@/components/monitoring/LiveDetailPanel';
import { ArtifactPanel, Artifact, CodeArtifact, TaskVersion } from '@/components/artifacts/ArtifactPanel';
import { api, TaskResponse } from '@/lib/api';
import { BreakpointModal } from '@/components/debug/BreakpointModal';
import { AlertCircle, Bot, LogIn, PanelRightClose, PanelRight, Activity, FileCode, Gauge } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { MilestoneInfo } from '@/types/chat';

interface ChatContainerProps {
  sessionId?: string;
}

type RightPanelTab = 'monitor' | 'artifacts' | 'details';

export function ChatContainer({ sessionId: initialSessionId }: ChatContainerProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { isAuthenticated, isLoading: authLoading, login } = useAuth();
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [rightPanelTab, setRightPanelTab] = useState<RightPanelTab>('monitor');
  const [breakpointEnabled, setBreakpointEnabled] = useState(false);
  const [completedTasks, setCompletedTasks] = useState<TaskVersion[]>([]);
  const [selectedArtifactVersion, setSelectedArtifactVersion] = useState<string | null>(null);
  const [versionArtifacts, setVersionArtifacts] = useState<Artifact[] | null>(null);

  const {
    sessionId,
    messages,
    isLoading,
    isStreaming,
    error,
    stats,
    currentActivity,
    completedAgents,
    agentHistory,
    breakpoint,
    isBreakpointLoading,
    streamingChunks,
    streamingAgent,
    sendMessage,
    cancelTask,
    createNewChat,
    clearError,
    resumeFromBreakpoint,
    rejectAtBreakpoint,
  } = useChat({
    sessionId: initialSessionId,
    breakpointEnabled,
    breakpointNodes: ['qa_breakpoint'],
  });

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  // Auto-open right panel when streaming starts
  useEffect(() => {
    if (isStreaming && !rightPanelOpen) {
      setRightPanelOpen(true);
      setRightPanelTab('monitor');
    }
  }, [isStreaming, rightPanelOpen]);

  // Update URL when session changes (for browser refresh support)
  useEffect(() => {
    if (sessionId && window.location.pathname === '/chat') {
      window.history.replaceState({}, '', `/chat/${sessionId}`);
    }
  }, [sessionId]);

  // Load completed tasks for version selection
  useEffect(() => {
    const loadCompletedTasks = async () => {
      if (!sessionId) {
        setCompletedTasks([]);
        return;
      }
      try {
        const response = await api.getTasks(sessionId, 'completed');
        const tasks: TaskVersion[] = response.items.map((t: TaskResponse, idx: number) => ({
          id: t.id,
          sequence_number: idx + 1,
          original_request: t.original_request,
          created_at: t.created_at,
        }));
        setCompletedTasks(tasks);
      } catch (err) {
        console.error('Failed to load completed tasks:', err);
      }
    };
    loadCompletedTasks();
  }, [sessionId, isStreaming]); // Reload when streaming ends (new task may have completed)

  // Handle version change for artifacts
  const handleVersionChange = async (taskId: string | null) => {
    setSelectedArtifactVersion(taskId);
    if (!taskId || !sessionId) {
      setVersionArtifacts(null); // Use latest from messages
      return;
    }
    try {
      const response = await api.getArtifacts(sessionId, taskId);
      const loadedArtifacts: Artifact[] = response.items.map((a) => ({
        id: a.id,
        type: 'code' as const,
        filename: a.filename,
        language: a.language || 'text',
        content: a.content,
        path: a.path || undefined,
      }));
      setVersionArtifacts(loadedArtifacts);
    } catch (err) {
      console.error('Failed to load artifacts for version:', err);
      setVersionArtifacts(null);
    }
  };

  const handleNewChat = async () => {
    const newSessionId = await createNewChat();
    window.history.pushState({}, '', `/chat/${newSessionId}`);
  };

  // Accumulate all milestones from all assistant messages in the session
  const currentMilestones = useMemo(() => {
    const milestonesMap = new Map<string, MilestoneInfo>();

    // Collect milestones from all assistant messages (including previous tasks in session)
    // Use Map to deduplicate by ID, keeping the latest version
    messages.forEach((m) => {
      if (m.role === 'assistant' && m.milestones?.length) {
        m.milestones.forEach((milestone) => {
          milestonesMap.set(milestone.id, milestone);
        });
      }
    });

    return Array.from(milestonesMap.values());
  }, [messages]);

  // Extract artifacts from the LATEST task only (task-level snapshot system)
  // Each task produces a complete artifact snapshot, so we only show the latest one
  const artifacts = useMemo(() => {
    const result: Artifact[] = [];

    // Find the latest assistant message with artifacts (represents current task state)
    // Reverse iterate to find the most recent one
    const latestMessageWithArtifacts = [...messages]
      .reverse()
      .find((msg) => msg.role === 'assistant' && msg.artifacts && msg.artifacts.length > 0);

    if (latestMessageWithArtifacts && latestMessageWithArtifacts.artifacts) {
      latestMessageWithArtifacts.artifacts.forEach((artifact, idx) => {
        const codeArtifact: CodeArtifact = {
          id: artifact.id || `${latestMessageWithArtifacts.id}-code-${idx}`,
          type: 'code',
          filename: artifact.filename,
          language: artifact.language || 'text',
          content: artifact.content,
          path: artifact.path || undefined,
        };
        result.push(codeArtifact);
      });
    } else {
      // Fallback: Parse code blocks from the latest assistant message
      const latestAssistant = [...messages]
        .reverse()
        .find((msg) => msg.role === 'assistant' && !msg.isStreaming && (msg.rawContent || msg.content));

      if (latestAssistant) {
        const contentToParse = latestAssistant.rawContent || latestAssistant.content;
        const codeBlockRegex = /```(\w+)?\n([\s\S]*?)```/g;
        let match;
        let fileIndex = 0;

        while ((match = codeBlockRegex.exec(contentToParse)) !== null) {
          const language = match[1] || 'text';
          const code = match[2].trim();

          if (!code) continue;

          // Try to extract filename from comment at the start
          const filenameMatch = code.match(/^(?:\/\/|#|\/\*)\s*(?:file(?:name)?:?\s*)?([^\n*]+)/i);
          let filename = filenameMatch ? filenameMatch[1].trim() : `code_${fileIndex + 1}`;

          // Add extension if missing
          if (!filename.includes('.')) {
            const extMap: Record<string, string> = {
              typescript: '.ts',
              javascript: '.js',
              python: '.py',
              rust: '.rs',
              go: '.go',
              java: '.java',
              css: '.css',
              html: '.html',
              json: '.json',
              yaml: '.yml',
              sql: '.sql',
              shell: '.sh',
              bash: '.sh',
            };
            filename += extMap[language] || '.txt';
          }

          const artifact: CodeArtifact = {
            id: `${latestAssistant.id}-code-${fileIndex}`,
            type: 'code',
            filename,
            language,
            content: code,
          };
          result.push(artifact);
          fileIndex++;
        }
      }
    }

    return result;
  }, [messages]);

  // Switch to artifacts tab when new artifacts are detected
  useEffect(() => {
    if (artifacts.length > 0 && !isStreaming) {
      setRightPanelTab('artifacts');
    }
  }, [artifacts.length, isStreaming]);

  // Switch to details tab when breakpoint is hit
  useEffect(() => {
    if (breakpoint) {
      setRightPanelOpen(true);
      setRightPanelTab('details');
    }
  }, [breakpoint]);

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <Sidebar
        currentSessionId={sessionId || undefined}
        onNewChat={handleNewChat}
        stats={stats}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex min-w-0">
        {/* Chat Area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-3xl mx-auto px-4 py-6">
              {/* Empty State */}
              {messages.length === 0 && !isLoading && (
                <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center">
                  <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-4">
                    <Bot className="h-8 w-8 text-primary" />
                  </div>
                  <h2 className="text-xl font-semibold mb-2">Welcome to BSAI</h2>
                  <p className="text-muted-foreground max-w-md mb-6">
                    Multi-Agent LLM Orchestration System with automatic cost optimization,
                    quality assurance, and context preservation.
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                    <FeatureCard
                      title="Cost Optimization"
                      description="Automatic LLM selection based on task complexity"
                    />
                    <FeatureCard
                      title="QA Validation"
                      description="Independent QA agent validates all outputs"
                    />
                    <FeatureCard
                      title="Context Memory"
                      description="Preserves context across sessions"
                    />
                  </div>
                </div>
              )}

              {/* Messages */}
              {messages.map((message) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  currentActivity={message.isStreaming ? currentActivity : undefined}
                />
              ))}

              {/* Error Display */}
              {error && (
                <div className="flex items-center gap-3 p-4 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive">
                  <AlertCircle className="h-5 w-5 flex-shrink-0" />
                  <div className="flex-1">
                    <p className="font-medium">Error</p>
                    <p className="text-sm">{error}</p>
                  </div>
                  <Button variant="outline" size="sm" onClick={clearError}>
                    Dismiss
                  </Button>
                </div>
              )}

              {/* Scroll anchor */}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input Area */}
          {isAuthenticated ? (
            <ChatInput
              onSend={sendMessage}
              onCancel={cancelTask}
              isLoading={isLoading}
              isStreaming={isStreaming}
              placeholder="Type your request..."
            />
          ) : (
            <div className="border-t bg-background p-4">
              <div className="mx-auto max-w-3xl text-center">
                <p className="text-sm text-muted-foreground mb-3">
                  Sign in to start chatting
                </p>
                <Button onClick={() => login()} disabled={authLoading}>
                  <LogIn className="mr-2 h-4 w-4" />
                  Sign in with Keycloak
                </Button>
              </div>
            </div>
          )}

          {/* Floating Usage Indicator */}
          <FloatingUsageIndicator
            totalTokens={stats.totalTokens}
            totalCostUsd={stats.totalCostUsd}
            isVisible={stats.totalTokens > 0}
          />
        </div>

        {/* Right Panel Toggle */}
        <div className="flex flex-col border-l bg-muted/30">
          {/* Tab buttons */}
          <div className="flex flex-col gap-1 p-2 border-b">
            <Button
              variant={rightPanelOpen && rightPanelTab === 'monitor' ? 'secondary' : 'ghost'}
              size="icon"
              className="h-9 w-9"
              onClick={() => {
                if (rightPanelOpen && rightPanelTab === 'monitor') {
                  setRightPanelOpen(false);
                } else {
                  setRightPanelOpen(true);
                  setRightPanelTab('monitor');
                }
              }}
              title="Agent Monitor"
            >
              <Activity className="h-4 w-4" />
            </Button>
            <Button
              variant={rightPanelOpen && rightPanelTab === 'artifacts' ? 'secondary' : 'ghost'}
              size="icon"
              className="h-9 w-9 relative"
              onClick={() => {
                if (rightPanelOpen && rightPanelTab === 'artifacts') {
                  setRightPanelOpen(false);
                } else {
                  setRightPanelOpen(true);
                  setRightPanelTab('artifacts');
                }
              }}
              title="Artifacts"
            >
              <FileCode className="h-4 w-4" />
              {artifacts.length > 0 && (
                <span className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-primary text-primary-foreground text-[10px] flex items-center justify-center">
                  {artifacts.length}
                </span>
              )}
            </Button>
            <Button
              variant={rightPanelOpen && rightPanelTab === 'details' ? 'secondary' : 'ghost'}
              size="icon"
              className="h-9 w-9 relative"
              onClick={() => {
                if (rightPanelOpen && rightPanelTab === 'details') {
                  setRightPanelOpen(false);
                } else {
                  setRightPanelOpen(true);
                  setRightPanelTab('details');
                }
              }}
              title="Live Details"
            >
              <Gauge className="h-4 w-4" />
              {breakpoint && (
                <span className="absolute -top-1 -right-1 h-3 w-3 rounded-full bg-amber-500 animate-pulse" />
              )}
            </Button>
          </div>
          {/* Panel toggle */}
          <Button
            variant="ghost"
            size="icon"
            className="h-9 w-9 m-2"
            onClick={() => setRightPanelOpen(!rightPanelOpen)}
            title={rightPanelOpen ? 'Close panel' : 'Open panel'}
          >
            {rightPanelOpen ? (
              <PanelRightClose className="h-4 w-4" />
            ) : (
              <PanelRight className="h-4 w-4" />
            )}
          </Button>
        </div>

        {/* Right Panel Content */}
        {rightPanelOpen && (
          <div className={cn(
            'w-96 lg:w-[28rem] xl:w-[32rem] flex-shrink-0 transition-all duration-200',
            !rightPanelOpen && 'w-0 overflow-hidden'
          )}>
            {rightPanelTab === 'monitor' && (
              <AgentMonitorPanel
                milestones={currentMilestones}
                currentActivity={currentActivity}
                isStreaming={isStreaming}
                agentHistory={agentHistory}
              />
            )}
            {rightPanelTab === 'artifacts' && (
              <ArtifactPanel
                artifacts={versionArtifacts || artifacts}
                onClose={() => setRightPanelOpen(false)}
                sessionId={sessionId || undefined}
                tasks={completedTasks}
                selectedTaskId={selectedArtifactVersion}
                onVersionChange={handleVersionChange}
              />
            )}
            {rightPanelTab === 'details' && (
              <LiveDetailPanel
                milestones={currentMilestones}
                agentHistory={agentHistory}
                currentActivity={currentActivity}
                isStreaming={isStreaming}
                breakpoint={breakpoint}
                onResume={resumeFromBreakpoint}
                onReject={rejectAtBreakpoint}
                isBreakpointLoading={isBreakpointLoading}
                streamingChunks={streamingChunks}
                streamingAgent={streamingAgent}
                breakpointEnabled={breakpointEnabled}
                onBreakpointToggle={setBreakpointEnabled}
              />
            )}
          </div>
        )}
      </div>

      {/* Breakpoint Modal for Human-in-the-Loop */}
      <BreakpointModal
        open={!!breakpoint}
        breakpoint={breakpoint}
        onResume={resumeFromBreakpoint}
        onReject={rejectAtBreakpoint}
        isLoading={isBreakpointLoading}
      />
    </div>
  );
}

function FeatureCard({ title, description }: { title: string; description: string }) {
  return (
    <div className="p-4 rounded-lg border bg-card">
      <h3 className="font-medium mb-1">{title}</h3>
      <p className="text-xs text-muted-foreground">{description}</p>
    </div>
  );
}
