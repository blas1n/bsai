/**
 * @jest-environment node
 */
import {
  extractUserMessage,
  handleTaskStarted,
  handleTaskProgress,
  handleMilestoneProgress,
  handleMilestoneCompleted,
  handleMilestoneRetry,
  handleLLMChunk,
  handleLLMComplete,
  handleTaskCompleted,
  handleTaskFailed,
  handleContextCompressed,
  handleBreakpointHit,
  ChatEventContext,
} from '@/hooks/chatEventHandlers';
import {
  TaskStartedPayload,
  TaskProgressPayload,
  MilestoneProgressPayload,
  LLMChunkPayload,
  LLMCompletePayload,
  TaskCompletedPayload,
  TaskFailedPayload,
  BreakpointHitPayload,
} from '@/types/websocket';

// Mock context factory
function createMockContext(): ChatEventContext {
  return {
    setMessages: jest.fn(),
    setStreaming: jest.fn(),
    setCurrentActivity: jest.fn(),
    setCompletedAgents: jest.fn(),
    setAgentHistory: jest.fn(),
    setStats: jest.fn(),
    setIsLoading: jest.fn(),
    setError: jest.fn(),
    setBreakpoint: jest.fn(),
    currentTaskIdRef: { current: null },
    streamingMessageIdRef: { current: null },
    updateSessionTitle: jest.fn(),
    onError: jest.fn(),
  };
}

describe('extractUserMessage', () => {
  it('should return empty string for falsy input', () => {
    expect(extractUserMessage('')).toBe('');
  });

  it('should remove code blocks', () => {
    const input = 'Hello\n```javascript\nconst x = 1;\n```\nWorld';
    expect(extractUserMessage(input)).toBe('Hello\n\nWorld');
  });

  it('should remove file path inline code', () => {
    const input = 'Check file `/path/to/file.ts` for details';
    expect(extractUserMessage(input)).toBe('Check file  for details');
  });

  it('should keep short inline code', () => {
    const input = 'Use `useState` hook';
    expect(extractUserMessage(input)).toBe('Use `useState` hook');
  });

  it('should provide default message when content is empty after cleanup', () => {
    const input = '```\ncode only\n```';
    expect(extractUserMessage(input)).toBe(
      'Task completed. Check the Artifacts panel for generated code and files.'
    );
  });

  it('should trim multiple newlines', () => {
    const input = 'Hello\n\n\n\n\nWorld';
    expect(extractUserMessage(input)).toBe('Hello\n\nWorld');
  });
});

describe('handleTaskStarted', () => {
  it('should create new assistant message', () => {
    const ctx = createMockContext();
    const payload: TaskStartedPayload = {
      task_id: 'task-123',
      session_id: 'session-456',
      original_request: 'Test request',
      milestone_count: 3,
      trace_url: 'http://localhost:13001/trace/abc',
    };

    handleTaskStarted(payload, ctx);

    expect(ctx.setMessages).toHaveBeenCalled();
    expect(ctx.setStreaming).toHaveBeenCalledWith(
      expect.objectContaining({
        isStreaming: true,
        totalMilestones: 3,
      })
    );
    expect(ctx.currentTaskIdRef.current).toBe('task-123');
    expect(ctx.streamingMessageIdRef.current).toBeTruthy();
  });

  it('should update session title', () => {
    const ctx = createMockContext();
    const payload: TaskStartedPayload = {
      task_id: 'task-123',
      session_id: 'session-456',
      original_request: 'A very long request that should be truncated to fit in the title bar',
      milestone_count: 2,
      trace_url: '',
    };

    handleTaskStarted(payload, ctx);

    expect(ctx.updateSessionTitle).toHaveBeenCalledWith(
      'session-456',
      expect.stringContaining('...')
    );
  });

  it('should handle previous milestones', () => {
    const ctx = createMockContext();
    const payload: TaskStartedPayload = {
      task_id: 'task-123',
      session_id: 'session-456',
      original_request: 'Test',
      milestone_count: 2,
      previous_milestones: [
        {
          id: 'ms-1',
          sequence_number: 1,
          description: 'First milestone',
          complexity: 'simple',
          status: 'passed',
        },
      ],
      trace_url: '',
    };

    handleTaskStarted(payload, ctx);

    expect(ctx.setMessages).toHaveBeenCalled();
    // Total milestones should include previous ones
    expect(ctx.setStreaming).toHaveBeenCalledWith(
      expect.objectContaining({
        totalMilestones: 3, // 2 + 1 previous
        currentMilestone: 1, // previous milestone count
      })
    );
  });
});

describe('handleTaskProgress', () => {
  it('should update streaming state', () => {
    const ctx = createMockContext();
    const payload: TaskProgressPayload = {
      task_id: 'task-123',
      current_milestone: 2,
      total_milestones: 5,
      progress: 0.4,
      current_milestone_title: 'Processing',
    };

    handleTaskProgress(payload, ctx);

    expect(ctx.setStreaming).toHaveBeenCalled();
  });
});

describe('handleMilestoneProgress', () => {
  it('should use explicit status from payload (started)', () => {
    const ctx = createMockContext();
    ctx.streamingMessageIdRef.current = 'msg-123';
    ctx.currentTaskIdRef.current = 'task-123';

    const payload: MilestoneProgressPayload = {
      milestone_id: 'ms-1',
      task_id: 'task-123',
      sequence_number: 1,
      status: 'started', // Explicit AgentStatus
      agent: 'worker',
      message: 'Starting work',
    };

    handleMilestoneProgress(payload, ctx);

    // Should NOT add to completed agents since status is 'started'
    const setCompletedFn = ctx.setCompletedAgents as jest.Mock;
    // The function is called with an updater, need to check the logic
    expect(ctx.setCurrentActivity).toHaveBeenCalledWith(
      expect.objectContaining({
        agent: 'worker',
        status: 'running', // 'started' maps to 'running'
      })
    );
  });

  it('should use explicit status from payload (completed)', () => {
    const ctx = createMockContext();
    ctx.streamingMessageIdRef.current = 'msg-123';
    ctx.currentTaskIdRef.current = 'task-123';

    const payload: MilestoneProgressPayload = {
      milestone_id: 'ms-1',
      task_id: 'task-123',
      sequence_number: 1,
      status: 'completed', // Explicit AgentStatus
      agent: 'worker',
      message: 'Work completed',
      details: {
        output: 'Result',
        output_preview: 'Result',
        output_length: 6,
        tokens_used: 100,
        input_tokens: 50,
        output_tokens: 50,
        model: 'gpt-4',
        cost_usd: 0.01,
        is_retry: false,
      },
    };

    handleMilestoneProgress(payload, ctx);

    expect(ctx.setCompletedAgents).toHaveBeenCalled();
    expect(ctx.setCurrentActivity).toHaveBeenCalledWith(
      expect.objectContaining({
        agent: 'worker',
        status: 'completed',
      })
    );
  });

  it('should handle conductor with milestones', () => {
    const ctx = createMockContext();
    ctx.streamingMessageIdRef.current = 'msg-123';
    ctx.currentTaskIdRef.current = 'task-123';

    const payload: MilestoneProgressPayload = {
      milestone_id: 'ms-1',
      task_id: 'task-123',
      sequence_number: 1,
      status: 'completed',
      agent: 'conductor',
      message: 'Plan created',
      details: {
        milestones: [
          {
            index: 0,
            description: 'Setup',
            complexity: 'simple',
            acceptance_criteria: 'Must be set up',
          },
          {
            index: 1,
            description: 'Implement',
            complexity: 'moderate',
            acceptance_criteria: 'Must work',
          },
        ],
      },
    };

    handleMilestoneProgress(payload, ctx);

    expect(ctx.setMessages).toHaveBeenCalled();
    expect(ctx.setStreaming).toHaveBeenCalled();
  });
});

describe('handleMilestoneCompleted', () => {
  it('should update milestone status to passed', () => {
    const ctx = createMockContext();
    ctx.streamingMessageIdRef.current = 'msg-123';

    const payload: MilestoneProgressPayload = {
      milestone_id: 'ms-1',
      task_id: 'task-123',
      sequence_number: 1,
      status: 'passed',
      agent: 'qa',
      message: 'QA passed',
    };

    handleMilestoneCompleted(payload, ctx);

    expect(ctx.setCompletedAgents).toHaveBeenCalled();
    expect(ctx.setCurrentActivity).toHaveBeenCalled();
    expect(ctx.setMessages).toHaveBeenCalled();
  });
});

describe('handleMilestoneRetry', () => {
  it('should update QA result with retry info', () => {
    const ctx = createMockContext();
    ctx.streamingMessageIdRef.current = 'msg-123';

    const payload: MilestoneProgressPayload = {
      milestone_id: 'ms-1',
      task_id: 'task-123',
      sequence_number: 1,
      status: 'in_progress',
      agent: 'qa',
      message: 'Retry 1/3: Fix formatting',
    };

    handleMilestoneRetry(payload, ctx);

    expect(ctx.setMessages).toHaveBeenCalled();
  });
});

describe('handleLLMChunk', () => {
  it('should accumulate streaming chunks', () => {
    const ctx = createMockContext();
    ctx.streamingMessageIdRef.current = 'msg-123';

    const payload: LLMChunkPayload = {
      task_id: 'task-123',
      milestone_id: 'ms-1',
      chunk: 'Hello ',
      chunk_index: 0,
      agent: 'worker',
    };

    handleLLMChunk(payload, ctx);

    expect(ctx.setStreaming).toHaveBeenCalled();
    expect(ctx.setMessages).toHaveBeenCalled();
  });
});

describe('handleLLMComplete', () => {
  it('should finalize streaming and update usage', () => {
    const ctx = createMockContext();
    ctx.streamingMessageIdRef.current = 'msg-123';

    const payload: LLMCompletePayload = {
      task_id: 'task-123',
      milestone_id: 'ms-1',
      full_content: 'Hello world!',
      tokens_used: 10,
      agent: 'worker',
    };

    handleLLMComplete(payload, ctx);

    expect(ctx.setCurrentActivity).toHaveBeenCalledWith(null);
    expect(ctx.setMessages).toHaveBeenCalled();
  });
});

describe('handleTaskCompleted', () => {
  it('should finalize message and update stats', () => {
    const ctx = createMockContext();
    ctx.streamingMessageIdRef.current = 'msg-123';

    const payload: TaskCompletedPayload = {
      task_id: 'task-123',
      final_result: 'Task completed successfully',
      total_tokens: 1000,
      total_cost_usd: '0.05',
      duration_seconds: 30,
      trace_url: 'http://localhost:13001/trace/abc',
    };

    handleTaskCompleted(payload, ctx);

    expect(ctx.setMessages).toHaveBeenCalled();
    expect(ctx.setStats).toHaveBeenCalled();
    expect(ctx.setStreaming).toHaveBeenCalledWith({ isStreaming: false, chunks: [] });
    expect(ctx.setIsLoading).toHaveBeenCalledWith(false);
    expect(ctx.setCurrentActivity).toHaveBeenCalledWith(null);
    expect(ctx.currentTaskIdRef.current).toBeNull();
    expect(ctx.streamingMessageIdRef.current).toBeNull();
  });
});

describe('handleTaskFailed', () => {
  it('should set error and clean up state', () => {
    const ctx = createMockContext();
    ctx.streamingMessageIdRef.current = 'msg-123';

    const payload: TaskFailedPayload = {
      task_id: 'task-123',
      error: 'Something went wrong',
      failed_milestone: 2,
    };

    handleTaskFailed(payload, ctx);

    expect(ctx.setMessages).toHaveBeenCalled();
    expect(ctx.setError).toHaveBeenCalledWith('Something went wrong');
    expect(ctx.onError).toHaveBeenCalledWith('Something went wrong');
    expect(ctx.setStreaming).toHaveBeenCalledWith({ isStreaming: false, chunks: [] });
    expect(ctx.setIsLoading).toHaveBeenCalledWith(false);
  });
});

describe('handleContextCompressed', () => {
  it('should add system message', () => {
    const ctx = createMockContext();

    handleContextCompressed(ctx);

    expect(ctx.setMessages).toHaveBeenCalled();
  });
});

describe('handleBreakpointHit', () => {
  it('should set breakpoint and update activity', () => {
    const ctx = createMockContext();

    const payload: BreakpointHitPayload = {
      task_id: 'task-123',
      session_id: 'session-456',
      node_name: 'execute_worker',
      agent_type: 'worker',
      current_state: {
        current_milestone_index: 1,
        total_milestones: 3,
        milestones: [
          { description: 'Setup', status: 'passed' },
          { description: 'Implement', status: 'in_progress' },
        ],
        last_worker_output: 'Previous output',
      },
      timestamp: '2026-01-13T00:00:00Z',
    };

    handleBreakpointHit(payload, ctx);

    expect(ctx.setBreakpoint).toHaveBeenCalledWith(payload);
    expect(ctx.setCurrentActivity).toHaveBeenCalledWith(
      expect.objectContaining({
        agent: 'worker',
        status: 'running',
        message: expect.stringContaining('execute_worker'),
      })
    );
  });
});

describe('Explicit status handling', () => {
  it('should treat "passed" as completion', () => {
    const ctx = createMockContext();
    ctx.streamingMessageIdRef.current = 'msg-123';
    ctx.currentTaskIdRef.current = 'task-123';

    const payload: MilestoneProgressPayload = {
      milestone_id: 'ms-1',
      task_id: 'task-123',
      sequence_number: 1,
      status: 'passed', // MilestoneStatus.PASSED
      agent: 'qa',
      message: 'Milestone passed',
    };

    handleMilestoneProgress(payload, ctx);

    expect(ctx.setCurrentActivity).toHaveBeenCalledWith(
      expect.objectContaining({
        status: 'completed', // Should map to completed
      })
    );
  });

  it('should treat "failed" as completion', () => {
    const ctx = createMockContext();
    ctx.streamingMessageIdRef.current = 'msg-123';
    ctx.currentTaskIdRef.current = 'task-123';

    const payload: MilestoneProgressPayload = {
      milestone_id: 'ms-1',
      task_id: 'task-123',
      sequence_number: 1,
      status: 'failed', // MilestoneStatus.FAILED
      agent: 'qa',
      message: 'Milestone failed',
    };

    handleMilestoneProgress(payload, ctx);

    expect(ctx.setCurrentActivity).toHaveBeenCalledWith(
      expect.objectContaining({
        status: 'completed', // Should map to completed (failed is also a terminal state)
      })
    );
  });
});
