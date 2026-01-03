import { create } from 'zustand';
import { Session, Task } from '@/types/session';
import { api } from '@/lib/api';

interface SessionState {
  sessions: Session[];
  currentSession: Session | null;
  tasks: Record<string, Task[]>;
  isLoading: boolean;
  error: string | null;

  // Actions
  fetchSessions: () => Promise<void>;
  setSessions: (sessions: Session[]) => void;
  addSession: (session: Session) => void;
  updateSession: (sessionId: string, updates: Partial<Session>) => void;
  updateSessionTitle: (sessionId: string, title: string) => void;
  removeSession: (sessionId: string) => void;
  setCurrentSession: (session: Session | null) => void;
  setTasks: (sessionId: string, tasks: Task[]) => void;
  addTask: (sessionId: string, task: Task) => void;
  updateTask: (sessionId: string, taskId: string, updates: Partial<Task>) => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const initialState = {
  sessions: [],
  currentSession: null,
  tasks: {},
  isLoading: false,
  error: null,
};

export const useSessionStore = create<SessionState>((set) => ({
  ...initialState,

  fetchSessions: async () => {
    set({ isLoading: true });
    try {
      const response = await api.getSessions(50, 0);
      set({ sessions: response.items, isLoading: false });
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
      set({ isLoading: false });
    }
  },

  setSessions: (sessions) => set({ sessions }),

  addSession: (session) =>
    set((state) => ({
      sessions: [session, ...state.sessions],
    })),

  updateSession: (sessionId, updates) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sessionId ? { ...s, ...updates } : s
      ),
      currentSession:
        state.currentSession?.id === sessionId
          ? { ...state.currentSession, ...updates }
          : state.currentSession,
    })),

  updateSessionTitle: (sessionId, title) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        // Only update if title is not already set (preserve first task's title)
        s.id === sessionId && !s.title ? { ...s, title } : s
      ),
    })),

  removeSession: (sessionId) =>
    set((state) => ({
      sessions: state.sessions.filter((s) => s.id !== sessionId),
      currentSession:
        state.currentSession?.id === sessionId ? null : state.currentSession,
    })),

  setCurrentSession: (session) => set({ currentSession: session }),

  setTasks: (sessionId, tasks) =>
    set((state) => ({
      tasks: { ...state.tasks, [sessionId]: tasks },
    })),

  addTask: (sessionId, task) =>
    set((state) => ({
      tasks: {
        ...state.tasks,
        [sessionId]: [...(state.tasks[sessionId] || []), task],
      },
    })),

  updateTask: (sessionId, taskId, updates) =>
    set((state) => ({
      tasks: {
        ...state.tasks,
        [sessionId]: (state.tasks[sessionId] || []).map((t) =>
          t.id === taskId ? { ...t, ...updates } : t
        ),
      },
    })),

  setLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),

  reset: () => set(initialState),
}));
