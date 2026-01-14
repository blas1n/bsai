# BSAI Frontend - Claude Development Guide

## Overview

Next.js 16 React 19 dashboard application. Communicates with BSAI backend API via REST and WebSocket for real-time updates.

## Tech Stack

- **Next.js 16** - App Router
- **React 19** - Latest React features
- **TypeScript** - Strict mode enabled
- **Tailwind CSS** - Utility-first styling
- **Radix UI** - Accessible component primitives
- **Zustand** - Lightweight state management
- **SWR** - Data fetching and caching
- **NextAuth.js** - OAuth authentication

## Directory Structure

```
web/src/
├── app/                    # Next.js App Router
│   ├── (dashboard)/       # Dashboard layout group
│   ├── chat/              # Chat interface
│   ├── login/             # Login page
│   └── api/auth/          # NextAuth API routes
├── components/            # React components
│   ├── ui/               # Base UI components (Button, Card, etc.)
│   ├── chat/             # Chat-related components
│   ├── sessions/         # Session management components
│   ├── tasks/            # Task view components
│   └── monitoring/       # Monitoring dashboard
├── hooks/                 # Custom React hooks
├── stores/                # Zustand stores
├── providers/             # React Context providers
├── lib/                   # Utility functions
└── types/                 # TypeScript type definitions
```

## Coding Conventions

### 1. Component Structure

```tsx
'use client';  // Required for client components

import { useState, useCallback } from 'react';
import { cn } from '@/lib/utils';

interface ComponentProps {
  title: string;
  onAction?: () => void;
  className?: string;
}

export function Component({ title, onAction, className }: ComponentProps) {
  const [state, setState] = useState(false);

  const handleClick = useCallback(() => {
    setState(true);
    onAction?.();
  }, [onAction]);

  return (
    <div className={cn('base-styles', className)}>
      {title}
    </div>
  );
}
```

### 2. Path Aliases

Use `@/` alias for imports:

```tsx
// Good
import { Button } from '@/components/ui/button';
import { useSessionStore } from '@/stores/sessionStore';
import { Session } from '@/types/session';

// Bad
import { Button } from '../../../components/ui/button';
```

### 3. Styling with Tailwind

Use `cn()` utility for conditional class merging:

```tsx
import { cn } from '@/lib/utils';

<div className={cn(
  'base-class',
  isActive && 'active-class',
  className
)} />
```

### 4. UI Components (Radix + CVA)

Use class-variance-authority for variant components:

```tsx
import { cva, type VariantProps } from 'class-variance-authority';

const buttonVariants = cva(
  'base-styles',
  {
    variants: {
      variant: {
        default: 'bg-primary',
        destructive: 'bg-destructive',
      },
      size: {
        default: 'h-10 px-4',
        sm: 'h-9 px-3',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}
```

### 5. State Management (Zustand)

```tsx
import { create } from 'zustand';

interface StoreState {
  items: Item[];
  isLoading: boolean;

  // Actions
  setItems: (items: Item[]) => void;
  addItem: (item: Item) => void;
  reset: () => void;
}

export const useStore = create<StoreState>((set) => ({
  items: [],
  isLoading: false,

  setItems: (items) => set({ items }),
  addItem: (item) => set((state) => ({
    items: [...state.items, item]
  })),
  reset: () => set({ items: [], isLoading: false }),
}));
```

### 6. Custom Hooks

```tsx
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

interface UseCustomHookOptions {
  onSuccess?: () => void;
  autoConnect?: boolean;
}

interface UseCustomHookReturn {
  isConnected: boolean;
  connect: () => void;
  disconnect: () => void;
}

export function useCustomHook(
  options: UseCustomHookOptions = {}
): UseCustomHookReturn {
  const { onSuccess, autoConnect = true } = options;
  const [isConnected, setIsConnected] = useState(false);

  // Use refs for callbacks to avoid effect reruns
  const onSuccessRef = useRef(onSuccess);
  useEffect(() => {
    onSuccessRef.current = onSuccess;
  }, [onSuccess]);

  const connect = useCallback(() => {
    setIsConnected(true);
    onSuccessRef.current?.();
  }, []);

  const disconnect = useCallback(() => {
    setIsConnected(false);
  }, []);

  return { isConnected, connect, disconnect };
}
```

### 7. API Client

```tsx
import { api } from '@/lib/api';

// Set token
api.setToken(accessToken);

// API calls
const sessions = await api.getSessions();
const session = await api.createSession();
const task = await api.createTask(sessionId, 'Request text');
```

### 8. Type Definitions

```tsx
// types/session.ts
export type SessionStatus = 'active' | 'paused' | 'completed' | 'failed';

export interface Session {
  id: string;
  user_id: string;
  status: string;  // API returns string
  title: string | null;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: string;  // Decimal passed as string
  created_at: string;
  updated_at: string;
}
```

## Quick Reference

### Commands

```bash
npm run dev          # Dev server (port 3000)
npm run build        # Production build
npm run lint         # Run ESLint
npm run type-check   # TypeScript type check
```

### Environment Variables

```bash
NEXT_PUBLIC_API_URL=http://localhost:18000
NEXT_PUBLIC_WS_URL=ws://localhost:18000
NEXTAUTH_URL=http://localhost:13000
NEXTAUTH_SECRET=your-secret
```

## MCP (Model Context Protocol) Integration

The frontend includes MCP server management for tool calling:

### Key Files

- `components/mcp/` - MCP server management UI
  - `McpServerForm.tsx` - Server creation/edit form with OAuth support
  - `McpServerCard.tsx` - Server display card with status
  - `McpServerList.tsx` - Server listing with actions
- `stores/mcpStore.ts` - Zustand store for MCP state
- `types/mcp.ts` - TypeScript types for MCP
- `app/(dashboard)/settings/mcp/` - MCP settings page
- `app/settings/mcp/oauth-callback/` - OAuth callback handler

### MCP Store Usage

```tsx
import { useMcpStore } from '@/stores/mcpStore';

function McpServersPage() {
  const { servers, loading, fetchServers, deleteServer } = useMcpStore();

  useEffect(() => {
    fetchServers();
  }, [fetchServers]);

  return <McpServerList servers={servers} onDelete={deleteServer} />;
}
```

## Component Patterns

### 1. Barrel Exports

Use index.ts in each component directory:

```tsx
// components/chat/index.ts
export { ChatContainer } from './ChatContainer';
export { ChatInput } from './ChatInput';
export { MessageBubble } from './MessageBubble';
```

### 2. Server vs Client Components

- **Server Component** (default): Data fetching, static rendering
- **Client Component** (`'use client'`): State, event handlers, browser APIs

```tsx
// Server Component (default)
async function ServerPage() {
  const data = await fetchData();
  return <ClientComponent data={data} />;
}

// Client Component
'use client';
function ClientComponent({ data }: { data: Data }) {
  const [state, setState] = useState(data);
  return <div onClick={() => setState(...)}>...</div>;
}
```

### 3. WebSocket Integration

```tsx
import { useWebSocket } from '@/hooks/useWebSocket';

function Component() {
  const { isConnected, send, lastMessage } = useWebSocket({
    sessionId: 'xxx',
    token: accessToken,
    onMessage: (msg) => console.log(msg),
    autoReconnect: true,
  });

  return <div>Connected: {isConnected ? 'Yes' : 'No'}</div>;
}
```

### 4. Event-Driven WebSocket Handling

The frontend uses explicit status from backend events (no heuristic-based detection):

```tsx
// hooks/chatEventHandlers.ts - Separated event handlers

// Backend sends explicit status values:
// AgentStatus: 'started' | 'completed' | 'failed'
// MilestoneStatus: 'pending' | 'in_progress' | 'passed' | 'failed'

export function handleMilestoneProgress(
  payload: MilestoneProgressPayload,
  ctx: ChatEventContext
): void {
  // Use EXPLICIT status from payload - no keyword detection needed
  const isCompletion =
    payload.status === 'completed' ||
    payload.status === 'passed' ||
    payload.status === 'failed';

  // Update UI based on explicit status
  const activity: AgentActivity = {
    agent: payload.agent as AgentType,
    status: isCompletion ? 'completed' : 'running',
    message: payload.message,
    // ...
  };
}

// useChat.ts - Uses handler map pattern
const handleWebSocketMessage = useCallback((message: WSMessage) => {
  const handlers: Record<string, (payload: unknown, ctx: ChatEventContext) => void> = {
    [WSMessageType.TASK_STARTED]: (p, c) => handleTaskStarted(p as TaskStartedPayload, c),
    [WSMessageType.MILESTONE_PROGRESS]: (p, c) => handleMilestoneProgress(p as MilestoneProgressPayload, c),
    [WSMessageType.TASK_COMPLETED]: (p, c) => handleTaskCompleted(p as TaskCompletedPayload, c),
    // ... other handlers
  };

  const handler = handlers[message.type];
  if (handler) handler(message.payload, eventContext);
}, [eventContext]);
```

## File Naming

- Components: `PascalCase.tsx` (e.g., `ChatInput.tsx`)
- Hooks: `camelCase.ts` (e.g., `useWebSocket.ts`)
- Utilities: `camelCase.ts` (e.g., `utils.ts`)
- Types: `camelCase.ts` (e.g., `session.ts`)
- Pages: `page.tsx` (Next.js App Router convention)
