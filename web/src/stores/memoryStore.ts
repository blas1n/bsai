import { create } from 'zustand';
import type { Memory, MemoryDetail, MemorySearchResult, MemoryStats } from '@/types/memory';
import { api, MemoryListResponse } from '@/lib/api';

interface MemoryState {
  memories: Memory[];
  currentMemory: MemoryDetail | null;
  searchResults: MemorySearchResult[];
  stats: MemoryStats | null;
  total: number;
  isLoading: boolean;
  isSearching: boolean;
  error: string | null;

  // Actions
  fetchMemories: (limit?: number, offset?: number, memoryType?: string) => Promise<void>;
  fetchMemory: (memoryId: string) => Promise<void>;
  deleteMemory: (memoryId: string) => Promise<void>;
  searchMemories: (query: string, limit?: number) => Promise<void>;
  fetchStats: () => Promise<void>;
  consolidate: () => Promise<{ consolidated_count: number; remaining_count: number }>;
  decay: () => Promise<{ decayed_count: number }>;
  setCurrentMemory: (memory: MemoryDetail | null) => void;
  clearSearchResults: () => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const initialState = {
  memories: [],
  currentMemory: null,
  searchResults: [],
  stats: null,
  total: 0,
  isLoading: false,
  isSearching: false,
  error: null,
};

export const useMemoryStore = create<MemoryState>((set, get) => ({
  ...initialState,

  fetchMemories: async (limit = 20, offset = 0, memoryType?: string) => {
    set({ isLoading: true, error: null });
    try {
      const response: MemoryListResponse = await api.getMemories(limit, offset, memoryType);
      set({
        memories: response.items,
        total: response.total,
        isLoading: false,
      });
    } catch (err) {
      console.error('Failed to fetch memories:', err);
      set({
        error: 'Failed to fetch memories',
        isLoading: false,
      });
    }
  },

  fetchMemory: async (memoryId: string) => {
    set({ isLoading: true, error: null });
    try {
      const memory = await api.getMemory(memoryId);
      set({ currentMemory: memory, isLoading: false });
    } catch (err) {
      console.error('Failed to fetch memory:', err);
      set({
        error: 'Failed to fetch memory details',
        isLoading: false,
      });
    }
  },

  deleteMemory: async (memoryId: string) => {
    try {
      await api.deleteMemory(memoryId);
      set((state) => ({
        memories: state.memories.filter((m) => m.id !== memoryId),
        total: state.total - 1,
        currentMemory:
          state.currentMemory?.id === memoryId ? null : state.currentMemory,
      }));
    } catch (err) {
      console.error('Failed to delete memory:', err);
      set({ error: 'Failed to delete memory' });
      throw err;
    }
  },

  searchMemories: async (query: string, limit = 5) => {
    set({ isSearching: true, error: null });
    try {
      const results = await api.searchMemories({ query, limit });
      set({ searchResults: results, isSearching: false });
    } catch (err) {
      console.error('Failed to search memories:', err);
      set({
        error: 'Failed to search memories',
        isSearching: false,
      });
    }
  },

  fetchStats: async () => {
    try {
      const stats = await api.getMemoryStats();
      set({ stats });
    } catch (err) {
      console.error('Failed to fetch memory stats:', err);
    }
  },

  consolidate: async () => {
    try {
      const result = await api.consolidateMemories();
      // Refresh memories after consolidation
      await get().fetchMemories();
      await get().fetchStats();
      return result;
    } catch (err) {
      console.error('Failed to consolidate memories:', err);
      set({ error: 'Failed to consolidate memories' });
      throw err;
    }
  },

  decay: async () => {
    try {
      const result = await api.decayMemories();
      // Refresh memories after decay
      await get().fetchMemories();
      await get().fetchStats();
      return result;
    } catch (err) {
      console.error('Failed to decay memories:', err);
      set({ error: 'Failed to apply memory decay' });
      throw err;
    }
  },

  setCurrentMemory: (memory) => set({ currentMemory: memory }),

  clearSearchResults: () => set({ searchResults: [] }),

  setError: (error) => set({ error }),

  reset: () => set(initialState),
}));
