# Core Module Design

## 1. Core Modules

### 1.1 LLM Abstraction Layer (`src/agent_platform/core/llm/`)

#### `base.py` - Base Interface
```python
class LLMProvider(Protocol):
    """LLM vendor abstraction interface"""
    async def chat_completion(request: ChatRequest) -> ChatResponse
    async def stream_completion(request: ChatRequest) -> AsyncIterator[ChatChunk]
    def get_token_count(text: str) -> int
    def get_model_info() -> ModelInfo
```

#### `registry.py` - Multi-vendor Registry
```python
class LLMRegistry:
    """LLM vendor management and routing"""
    def register_provider(name: str, provider: LLMProvider)
    def get_provider(name: str) -> LLMProvider
    def list_models() -> List[ModelInfo]
```

#### `providers/` - Vendor-specific Implementations
- `openai_provider.py` - OpenAI GPT
- `anthropic_provider.py` - Anthropic Claude
- `google_provider.py` - Google Gemini
- `litellm_provider.py` - LiteLLM integration (fallback)

#### `middleware.py` - Common Middleware
```python
class LLMMiddleware:
    """Request/response processing middleware"""
    async def pre_process(request: ChatRequest) -> ChatRequest
    async def post_process(response: ChatResponse) -> ChatResponse
    # PII filtering, retry, caching, etc.
```

---

### 1.2 Orchestrator (`src/agent_platform/core/orchestrator/`)

#### `planner.py` - Task Planning
```python
class TaskPlanner:
    """Decompose complex requests into executable subtasks"""
    async def plan(user_request: str, context: Context) -> ExecutionPlan
    async def replan(plan: ExecutionPlan, feedback: Feedback) -> ExecutionPlan
```

#### `executor.py` - Task Execution
```python
class TaskExecutor:
    """Execute planned tasks sequentially/in parallel"""
    async def execute(plan: ExecutionPlan) -> ExecutionResult
    async def execute_step(step: TaskStep) -> StepResult
```

#### `orchestrator.py` - Overall Coordination
```python
class AgentOrchestrator:
    """Integrated management of Planner + Executor + Memory"""
    async def process_request(request: AgentRequest) -> AgentResponse
    async def handle_streaming(request: AgentRequest) -> AsyncIterator[AgentEvent]
```

---

### 1.3 Memory (`src/agent_platform/core/memory/`)

#### `short_term.py` - Short-term Memory (Session)
```python
class ShortTermMemory:
    """Conversation context management (Redis-based)"""
    async def add_message(session_id: str, message: Message)
    async def get_context(session_id: str, limit: int) -> List[Message]
    async def clear_session(session_id: str)
```

#### `long_term.py` - Long-term Memory (Vector DB)
```python
class LongTermMemory:
    """Knowledge storage and retrieval (future expansion)"""
    async def store(content: str, metadata: dict)
    async def search(query: str, limit: int) -> List[SearchResult]
```

---

### 1.4 Tool Registry (`src/agent_platform/core/tools/`)

#### `registry.py` - Tool Management
```python
class ToolRegistry:
    """Manage tools available to agents"""
    def register_tool(tool: Tool)
    def get_tool(name: str) -> Tool
    def list_tools() -> List[ToolDefinition]
```

#### `base.py` - Tool Interface
```python
class Tool(Protocol):
    name: str
    description: str
    schema: dict
    async def execute(parameters: dict) -> ToolResult
```

---

## 2. Platform Modules

### 2.1 Prompt Store (`src/agent_platform/platform/prompt_store/`)

#### `store.py` - Store Management
```python
class PromptStore:
    """Prompt CRUD and version management"""
    async def create_prompt(prompt: PromptCreate) -> Prompt
    async def get_prompt(name: str, version: Optional[int]) -> Prompt
    async def update_prompt(name: str, content: str) -> Prompt
    async def list_versions(name: str) -> List[PromptVersion]
    async def rollback(name: str, version: int) -> Prompt
```

#### `versioning.py` - Version Management
```python
class PromptVersionManager:
    """Track prompt change history"""
    async def create_version(prompt_id: str, content: str, author: str)
    async def compare_versions(v1: int, v2: int) -> VersionDiff
    async def get_history(prompt_id: str) -> List[VersionHistory]
```

#### `template.py` - Template Rendering
```python
class PromptTemplate:
    """Variable substitution and template processing (Jinja2-based)"""
    def render(template: str, variables: dict) -> str
    def validate(template: str) -> ValidationResult
```

---

### 2.2 Trace Logging (`src/agent_platform/platform/trace/`)

#### `tracer.py` - Trace Management
```python
class TraceManager:
    """Track entire request lifecycle (OpenTelemetry-based)"""
    async def start_trace(request_id: str, metadata: dict) -> Trace
    async def add_span(trace_id: str, span: Span)
    async def end_trace(trace_id: str, result: dict)
    async def get_trace(trace_id: str) -> TraceData
```

#### `logger.py` - Structured Logging
```python
class StructuredLogger:
    """Structlog-based JSON logging"""
    def log_llm_call(provider: str, model: str, tokens: int, latency: float)
    def log_error(error: Exception, context: dict)
    def log_user_action(action: str, user_id: str, metadata: dict)
```

---

### 2.3 Cost Tracking (`src/agent_platform/platform/cost/`)

#### `tracker.py` - Cost Calculation
```python
class CostTracker:
    """LLM call cost calculation and aggregation"""
    async def record_usage(
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int
    ) -> CostRecord
    async def get_usage_report(
        start_date: datetime,
        end_date: datetime,
        group_by: str
    ) -> UsageReport
```

#### `pricing.py` - Pricing Information Management
```python
class PricingManager:
    """Maintain model-specific pricing information"""
    def get_price(provider: str, model: str) -> ModelPricing
    def update_pricing(pricing_data: dict)
```

---

### 2.4 Experiment Management (`src/agent_platform/platform/experiments/`)

#### `runner.py` - Experiment Execution
```python
class ExperimentRunner:
    """A/B testing and prompt experiments"""
    async def create_experiment(config: ExperimentConfig) -> Experiment
    async def run_experiment(exp_id: str, test_cases: List[TestCase]) -> ExperimentResult
    async def compare_results(exp_id: str) -> ComparisonReport
```

#### `evaluator.py` - Evaluation
```python
class PromptEvaluator:
    """Prompt quality evaluation"""
    async def evaluate(
        prompt: str,
        test_data: List[dict],
        metrics: List[Metric]
    ) -> EvaluationResult
```

---

### 2.5 Security (`src/agent_platform/platform/security/`)

#### `auth.py` - Authentication/Authorization
```python
class AuthManager:
    """JWT-based authentication"""
    def create_token(user_id: str, scopes: List[str]) -> str
    def verify_token(token: str) -> TokenPayload
    def check_permission(user: User, resource: str, action: str) -> bool
```

#### `pii_filter.py` - PII Filtering
```python
class PIIFilter:
    """PII detection and masking"""
    def detect_pii(text: str) -> List[PIIMatch]
    def mask_pii(text: str) -> str
    def anonymize(text: str) -> str
```

#### `credentials.py` - Credential Management
```python
class CredentialManager:
    """Centralized API key management (environment variables/Vault integration)"""
    def get_credential(provider: str) -> str
    def rotate_credential(provider: str, new_key: str)
```

---

## 3. Interfaces

### 3.1 REST/WebSocket API (`src/agent_platform/interfaces/api/`)

#### `routers/`
- `agents.py` - Agent request handling
- `prompts.py` - Prompt management
- `experiments.py` - Experiment management
- `traces.py` - Trace queries
- `admin.py` - Admin functions

#### `websocket.py` - Streaming Responses
```python
class AgentWebSocket:
    """Real-time agent response streaming"""
    async def handle_connection(websocket: WebSocket)
    async def stream_response(request: AgentRequest) -> AsyncIterator[Event]
```

---

### 3.2 MCP Adapter (`src/agent_platform/interfaces/mcp/`)

#### `server.py` - MCP Server
```python
class MCPServer:
    """Model Context Protocol server implementation"""
    async def handle_mcp_request(request: MCPRequest) -> MCPResponse
```

#### `resources.py` - Resource Exposure
```python
# Expose Agent as MCP Resource
def register_agent_resources(registry: ResourceRegistry)
```

---

## 4. Domain Layer

### 4.1 Models (`src/agent_platform/domain/models/`)
- `agent.py` - Agent-related domain models
- `prompt.py` - Prompt domain models
- `trace.py` - Trace domain models
- `user.py` - User domain models

### 4.2 Repositories (`src/agent_platform/domain/repositories/`)
- `prompt_repository.py`
- `trace_repository.py`
- `experiment_repository.py`

### 4.3 Services (`src/agent_platform/domain/services/`)
- `agent_service.py` - Agent business logic
- `prompt_service.py` - Prompt business logic

---

## 5. Infrastructure

### 5.1 Database (`src/agent_platform/infrastructure/database/`)
- `postgres.py` - PostgreSQL connection
- `models.py` - SQLAlchemy ORM models
- `migrations/` - Alembic migrations

### 5.2 Cache (`src/agent_platform/infrastructure/cache/`)
- `redis.py` - Redis client

### 5.3 Messaging (`src/agent_platform/infrastructure/messaging/`)
- `pubsub.py` - Event publish/subscribe (future expansion)
