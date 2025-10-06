# Architecture Overview

## Design Principles

### 1. Separation of Concerns
The platform is divided into distinct layers, each with clear responsibilities:

- **Interfaces Layer**: HTTP/WebSocket APIs, MCP server
- **Core Layer**: Agent logic, planning, execution
- **Platform Layer**: Operational features (prompts, tracing, cost, experiments)
- **Infrastructure Layer**: Database, cache, messaging

### 2. Dependency Inversion
High-level modules don't depend on low-level modules. Both depend on abstractions.

Example: Agent orchestrator depends on `LLMProvider` interface, not specific implementations.

### 3. Asynchronous First
All I/O operations are async to maximize throughput and resource utilization.

### 4. Observability by Default
Every operation is traced, logged, and metered without additional instrumentation.

## Layer Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Interfaces Layer                       │
│   REST API │ WebSocket │ MCP Server │ CLI (future)      │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                    Core Layer                            │
│  Orchestrator │ Planner │ Executor │ Memory │ Tools    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                   LLM Abstraction                        │
│   Registry │ Providers (OpenAI, Claude, Gemini, ...)   │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                  Platform Layer                          │
│  Prompts │ Trace │ Cost │ Experiments │ Security        │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                Infrastructure Layer                      │
│    PostgreSQL │ Redis │ OTLP │ Prometheus               │
└─────────────────────────────────────────────────────────┘
```

## Data Flow

### Request Processing Flow

```
1. Client Request
   ↓
2. FastAPI Router (with middleware)
   ↓
3. Authentication & Authorization
   ↓
4. AgentOrchestrator.process_request()
   ↓
5. Load Context from Memory (Redis)
   ↓
6. TaskPlanner.plan()
   ├─→ Fetch Prompt from PromptStore
   └─→ Call LLM via Registry
   ↓
7. TaskExecutor.execute()
   ├─→ Call LLM(s)
   ├─→ Execute Tools
   └─→ Record Usage & Cost
   ↓
8. Store Results in Memory
   ↓
9. Return Response to Client
   ↓
10. Background: Persist Trace to DB
```

### Trace Context Propagation

```
Request → Middleware creates trace context
   ↓
Orchestrator propagates to Planner/Executor
   ↓
LLM calls inherit trace context
   ↓
All operations recorded as spans
   ↓
Trace persisted to database
```

## Scalability Strategy

### Horizontal Scaling
- **Stateless API servers**: Scale FastAPI instances behind load balancer
- **Shared state in Redis**: Session data accessible from any instance
- **PostgreSQL read replicas**: Scale read operations

### Vertical Scaling
- **Connection pooling**: Efficient database connection management
- **Async I/O**: Maximize CPU utilization
- **Caching**: Reduce repeated LLM calls and database queries

### Future: Distributed Processing
- **Message queue**: Celery for background tasks
- **Worker pool**: Dedicated workers for long-running agent tasks

## Security Model

### Authentication
- JWT-based token authentication
- API key support for programmatic access
- OAuth2 integration (planned)

### Authorization
- Role-based access control (RBAC)
- Resource-level permissions
- Audit logging for all operations

### Data Protection
- PII detection and masking
- Encrypted credentials storage
- TLS for all external communication

## Deployment Architecture

### Development
```
Single container:
  - FastAPI app
  - PostgreSQL (Docker)
  - Redis (Docker)
```

### Production (Kubernetes)
```
┌──────────────────────────────────────────┐
│            Ingress / Load Balancer        │
└──────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│         FastAPI Pods (3+ replicas)        │
└──────────────────────────────────────────┘
         ↓                          ↓
┌──────────────────┐    ┌──────────────────┐
│   PostgreSQL     │    │      Redis       │
│   (StatefulSet)  │    │  (StatefulSet)   │
└──────────────────┘    └──────────────────┘
         ↓
┌──────────────────────────────────────────┐
│    Observability Stack                   │
│  Prometheus │ Grafana │ Jaeger           │
└──────────────────────────────────────────┘
```

## Technology Choices

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Web Framework | FastAPI | Native async, auto-docs, type safety |
| Database | PostgreSQL | JSONB support, reliability, ACID |
| Cache | Redis | Performance, pub/sub support |
| Tracing | OpenTelemetry | Industry standard, vendor-neutral |
| Metrics | Prometheus | De facto standard, Kubernetes native |
| Logging | Structlog | Structured JSON logs, context binding |
| Testing | pytest | Rich ecosystem, async support |
| LLM SDK | litellm | Multi-provider abstraction |

## Extension Points

### Custom LLM Providers
Implement `LLMProvider` interface to add new vendors.

### Custom Tools
Register tools via `ToolRegistry` for agent capabilities.

### Custom Middleware
Add FastAPI middleware for cross-cutting concerns.

### Custom Metrics
Define Prometheus metrics for domain-specific monitoring.

## Migration Path

### Phase 1: MVP (Current)
- Core orchestration
- Basic prompt management
- Cost tracking
- Single-instance deployment

### Phase 2: Platform Features
- Full prompt versioning
- Experiment framework
- Advanced tracing
- Multi-tenant support

### Phase 3: Scale & Optimize
- Distributed processing
- Auto-scaling
- Advanced caching
- Performance optimization

### Phase 4: Enterprise
- SSO integration
- Advanced RBAC
- Compliance features
- SLA monitoring
