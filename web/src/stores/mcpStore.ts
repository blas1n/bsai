import { create } from 'zustand';
import { api } from '@/lib/api';
import type {
  McpServerResponse,
  McpServerDetailResponse,
  McpServerCreateRequest,
  McpServerUpdateRequest,
  McpServerTestResponse,
  McpToolSchema,
} from '@/types/mcp';

interface McpState {
  // Server list
  servers: McpServerResponse[];
  currentServer: McpServerDetailResponse | null;
  serverTools: Record<string, McpToolSchema[]>;

  // Test results
  testResults: Record<string, McpServerTestResponse>;

  // UI state
  isLoading: boolean;
  isCreating: boolean;
  isTesting: Record<string, boolean>;
  error: string | null;

  // Actions
  fetchServers: (isActiveOnly?: boolean) => Promise<void>;
  fetchServer: (serverId: string) => Promise<void>;
  createServer: (request: McpServerCreateRequest) => Promise<McpServerResponse>;
  updateServer: (serverId: string, request: McpServerUpdateRequest) => Promise<McpServerResponse>;
  deleteServer: (serverId: string) => Promise<void>;
  testServer: (serverId: string) => Promise<McpServerTestResponse>;
  fetchServerTools: (serverId: string) => Promise<McpToolSchema[]>;
  setCurrentServer: (server: McpServerDetailResponse | null) => void;
  clearError: () => void;
}

export const useMcpStore = create<McpState>((set, get) => ({
  servers: [],
  currentServer: null,
  serverTools: {},
  testResults: {},
  isLoading: false,
  isCreating: false,
  isTesting: {},
  error: null,

  fetchServers: async (isActiveOnly = false) => {
    set({ isLoading: true, error: null });
    try {
      const servers = await api.getMcpServers(isActiveOnly);
      set({ servers, isLoading: false });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to fetch MCP servers',
        isLoading: false,
      });
    }
  },

  fetchServer: async (serverId: string) => {
    set({ isLoading: true, error: null });
    try {
      const server = await api.getMcpServer(serverId);
      set({ currentServer: server, isLoading: false });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to fetch MCP server',
        isLoading: false,
      });
    }
  },

  createServer: async (request: McpServerCreateRequest) => {
    set({ isCreating: true, error: null });
    try {
      const server = await api.createMcpServer(request);
      set((state) => ({
        servers: [...state.servers, server],
        isCreating: false,
      }));
      return server;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to create MCP server';
      set({ error: errorMessage, isCreating: false });
      throw new Error(errorMessage);
    }
  },

  updateServer: async (serverId: string, request: McpServerUpdateRequest) => {
    set({ error: null });
    try {
      const server = await api.updateMcpServer(serverId, request);
      set((state) => ({
        servers: state.servers.map((s) => (s.id === serverId ? server : s)),
        currentServer: state.currentServer?.id === serverId
          ? { ...state.currentServer, ...server }
          : state.currentServer,
      }));
      return server;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to update MCP server';
      set({ error: errorMessage });
      throw new Error(errorMessage);
    }
  },

  deleteServer: async (serverId: string) => {
    set({ error: null });
    try {
      await api.deleteMcpServer(serverId);
      set((state) => ({
        servers: state.servers.filter((s) => s.id !== serverId),
        currentServer: state.currentServer?.id === serverId ? null : state.currentServer,
      }));
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to delete MCP server';
      set({ error: errorMessage });
      throw new Error(errorMessage);
    }
  },

  testServer: async (serverId: string) => {
    set((state) => ({
      isTesting: { ...state.isTesting, [serverId]: true },
      error: null,
    }));
    try {
      const result = await api.testMcpServer(serverId);
      set((state) => ({
        testResults: { ...state.testResults, [serverId]: result },
        isTesting: { ...state.isTesting, [serverId]: false },
      }));
      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to test MCP server';
      set((state) => ({
        error: errorMessage,
        isTesting: { ...state.isTesting, [serverId]: false },
      }));
      throw new Error(errorMessage);
    }
  },

  fetchServerTools: async (serverId: string) => {
    try {
      const tools = await api.getMcpServerTools(serverId);
      set((state) => ({
        serverTools: { ...state.serverTools, [serverId]: tools },
      }));
      return tools;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch server tools';
      set({ error: errorMessage });
      throw new Error(errorMessage);
    }
  },

  setCurrentServer: (server) => {
    set({ currentServer: server });
  },

  clearError: () => {
    set({ error: null });
  },
}));
