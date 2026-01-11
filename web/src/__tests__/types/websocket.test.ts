/**
 * @jest-environment node
 */
import {
  WSMessageType,
  WSMessage,
  TaskStartedPayload,
  TaskCompletedPayload,
  TaskProgressPayload,
  MilestoneProgressPayload,
  PreviousMilestoneInfo,
} from '@/types/websocket';

describe('WSMessageType enum', () => {
  it('has correct auth message types', () => {
    expect(WSMessageType.AUTH).toBe('auth');
    expect(WSMessageType.AUTH_SUCCESS).toBe('auth_success');
    expect(WSMessageType.AUTH_ERROR).toBe('auth_error');
  });

  it('has correct subscription message types', () => {
    expect(WSMessageType.SUBSCRIBE).toBe('subscribe');
    expect(WSMessageType.UNSUBSCRIBE).toBe('unsubscribe');
    expect(WSMessageType.SUBSCRIBED).toBe('subscribed');
    expect(WSMessageType.UNSUBSCRIBED).toBe('unsubscribed');
  });

  it('has correct task event types', () => {
    expect(WSMessageType.TASK_STARTED).toBe('task_started');
    expect(WSMessageType.TASK_PROGRESS).toBe('task_progress');
    expect(WSMessageType.TASK_COMPLETED).toBe('task_completed');
    expect(WSMessageType.TASK_FAILED).toBe('task_failed');
  });

  it('has correct milestone event types', () => {
    expect(WSMessageType.MILESTONE_STARTED).toBe('milestone_started');
    expect(WSMessageType.MILESTONE_PROGRESS).toBe('milestone_progress');
    expect(WSMessageType.MILESTONE_COMPLETED).toBe('milestone_completed');
    expect(WSMessageType.MILESTONE_FAILED).toBe('milestone_failed');
    expect(WSMessageType.MILESTONE_RETRY).toBe('milestone_retry');
  });

  it('has correct LLM streaming types', () => {
    expect(WSMessageType.LLM_CHUNK).toBe('llm_chunk');
    expect(WSMessageType.LLM_COMPLETE).toBe('llm_complete');
  });

  it('has correct session event types', () => {
    expect(WSMessageType.SESSION_PAUSED).toBe('session_paused');
    expect(WSMessageType.SESSION_RESUMED).toBe('session_resumed');
    expect(WSMessageType.CONTEXT_COMPRESSED).toBe('context_compressed');
  });

  it('has ping/pong types', () => {
    expect(WSMessageType.PING).toBe('ping');
    expect(WSMessageType.PONG).toBe('pong');
  });

  it('has error type', () => {
    expect(WSMessageType.ERROR).toBe('error');
  });
});

describe('Payload types with trace_url', () => {
  describe('TaskStartedPayload', () => {
    it('should accept trace_url as string', () => {
      const payload: TaskStartedPayload = {
        task_id: 'task-123',
        session_id: 'session-456',
        original_request: 'Test request',
        milestone_count: 5,
        trace_url: 'http://localhost:13001/trace/abc',
      };

      expect(payload.trace_url).toBe('http://localhost:13001/trace/abc');
    });

    it('should accept empty trace_url (tracing disabled)', () => {
      const payload: TaskStartedPayload = {
        task_id: 'task-123',
        session_id: 'session-456',
        original_request: 'Test request',
        milestone_count: 5,
        trace_url: '',
      };

      expect(payload.trace_url).toBe('');
    });

    it('should accept previous_milestones array', () => {
      const previousMilestone: PreviousMilestoneInfo = {
        id: 'milestone-1',
        sequence_number: 1,
        description: 'First milestone',
        complexity: 'low',
        status: 'passed',
        worker_output: 'Output from milestone 1',
      };

      const payload: TaskStartedPayload = {
        task_id: 'task-123',
        session_id: 'session-456',
        original_request: 'Test request',
        milestone_count: 5,
        previous_milestones: [previousMilestone],
        trace_url: 'http://localhost:13001/trace/abc',
      };

      expect(payload.previous_milestones).toHaveLength(1);
      expect(payload.previous_milestones?.[0].description).toBe('First milestone');
    });
  });

  describe('TaskCompletedPayload', () => {
    it('should accept trace_url as string', () => {
      const payload: TaskCompletedPayload = {
        task_id: 'task-123',
        final_result: 'Task completed successfully',
        total_tokens: 1500,
        total_cost_usd: '0.05',
        duration_seconds: 45.5,
        trace_url: 'http://localhost:13001/trace/xyz',
      };

      expect(payload.trace_url).toBe('http://localhost:13001/trace/xyz');
    });

    it('should accept empty trace_url (tracing disabled)', () => {
      const payload: TaskCompletedPayload = {
        task_id: 'task-123',
        final_result: 'Task completed successfully',
        total_tokens: 1500,
        total_cost_usd: '0.05',
        duration_seconds: 45.5,
        trace_url: '',
      };

      expect(payload.trace_url).toBe('');
    });
  });

  describe('TaskProgressPayload', () => {
    it('should have correct structure', () => {
      const payload: TaskProgressPayload = {
        task_id: 'task-123',
        current_milestone: 2,
        total_milestones: 5,
        progress: 0.4,
        current_milestone_title: 'Processing data',
      };

      expect(payload.current_milestone).toBe(2);
      expect(payload.total_milestones).toBe(5);
      expect(payload.progress).toBe(0.4);
    });
  });

  describe('MilestoneProgressPayload', () => {
    it('should have correct structure', () => {
      const payload: MilestoneProgressPayload = {
        milestone_id: 'milestone-1',
        task_id: 'task-123',
        sequence_number: 1,
        status: 'in_progress',
        agent: 'worker',
        message: 'Processing milestone',
        details: {
          output: 'Worker output',
          output_preview: 'Worker...',
          output_length: 100,
          tokens_used: 50,
          input_tokens: 30,
          output_tokens: 20,
          model: 'gpt-4',
          cost_usd: 0.01,
          is_retry: false,
        },
      };

      expect(payload.agent).toBe('worker');
      expect(payload.status).toBe('in_progress');
    });
  });
});

describe('WSMessage generic type', () => {
  it('should work with TaskStartedPayload', () => {
    const message: WSMessage<TaskStartedPayload> = {
      type: WSMessageType.TASK_STARTED,
      payload: {
        task_id: 'task-123',
        session_id: 'session-456',
        original_request: 'Test request',
        milestone_count: 5,
        trace_url: 'http://localhost:13001/trace/abc',
      },
      timestamp: '2026-01-11T00:00:00Z',
    };

    expect(message.type).toBe(WSMessageType.TASK_STARTED);
    expect(message.payload.trace_url).toBe('http://localhost:13001/trace/abc');
  });

  it('should support optional request_id', () => {
    const message: WSMessage<TaskStartedPayload> = {
      type: WSMessageType.TASK_STARTED,
      payload: {
        task_id: 'task-123',
        session_id: 'session-456',
        original_request: 'Test request',
        milestone_count: 5,
        trace_url: '',
      },
      timestamp: '2026-01-11T00:00:00Z',
      request_id: 'req-789',
    };

    expect(message.request_id).toBe('req-789');
  });
});
