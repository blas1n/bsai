# Observability & Cost Tracking Architecture

## Design Philosophy

1. **Full Traceability**: Complete tracking of every request lifecycle
2. **Real-time Monitoring**: Immediate detection and response to performance issues
3. **Accurate Cost Calculation**: Token-level cost tracking and budget management
4. **Standards Compliance**: Tool compatibility through OpenTelemetry standards

---

## 1. Trace Logging Architecture

### 1.1 OpenTelemetry-based Structure

```
User Request
    ↓
[FastAPI Middleware] → Create Trace Context
    ↓
[TraceManager] → Start Root Span
    ↓
[AgentOrchestrator]
    ├─→ [Planner Span]
    │     └─→ [LLM Call Span] → Record tokens/cost
    ├─→ [Executor Span]
    │     ├─→ [Tool Call Span]
    │     └─→ [LLM Call Span] → Record tokens/cost
    └─→ [Memory Span]
          └─→ [Redis Operation Span]
    ↓
[TraceManager] → End Trace & Persist
    ↓
[Database + OTLP Collector]
```

### 1.2 Trace Context Propagation

Propagate trace context across all async operations:

```python
from opentelemetry import trace
from opentelemetry.context import attach, detach

# Create and propagate context
tracer = trace.get_tracer(__name__)

async def process_request(request: AgentRequest):
    with tracer.start_as_current_span("agent.process") as span:
        span.set_attribute("user.id", request.user_id)
        span.set_attribute("request.id", request.request_id)

        # Automatically recorded as child span
        await orchestrator.execute(request)
```

### 1.3 Span Types and Attributes

#### Agent Execution Span
```python
span_name: "agent.execute"
attributes:
    - agent.type: "orchestrator"
    - request.id: UUID
    - user.id: string
    - session.id: UUID
```

#### LLM Call Span
```python
span_name: "llm.chat_completion"
attributes:
    - llm.provider: "openai" | "anthropic" | "google"
    - llm.model: "gpt-4" | "claude-3-opus"
    - llm.input_tokens: int
    - llm.output_tokens: int
    - llm.total_tokens: int
    - llm.cost: Decimal
    - llm.latency_ms: int
    - llm.temperature: float
    - llm.max_tokens: int
    - prompt.id: UUID (optional)
    - prompt.version: int (optional)
```

#### Tool Execution Span
```python
span_name: "tool.execute"
attributes:
    - tool.name: string
    - tool.parameters: JSON
    - tool.result_status: "success" | "error"
```

### 1.4 Structured Logging

**Structlog-based JSON logging**:

```python
import structlog

logger = structlog.get_logger()

# Automatically includes trace_id, span_id
logger.info(
    "llm_call_completed",
    provider="openai",
    model="gpt-4",
    tokens=1234,
    cost=0.0246,
    latency_ms=850
)
```

Output example:
```json
{
  "event": "llm_call_completed",
  "timestamp": "2025-10-05T12:34:56.789Z",
  "level": "info",
  "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "span_id": "12345678-90ab-cdef",
  "provider": "openai",
  "model": "gpt-4",
  "tokens": 1234,
  "cost": 0.0246,
  "latency_ms": 850,
  "user_id": "user_123"
}
```

---

## 2. Cost Tracking Architecture

### 2.1 Real-time Cost Recording

**Record immediately after LLM call**:

```python
class LLMCostMiddleware:
    async def __call__(self, request: ChatRequest) -> ChatResponse:
        start_time = time.time()

        # LLM call
        response = await self.next_provider.chat_completion(request)

        # Calculate and record cost
        cost_record = await self.cost_tracker.record_usage(
            provider=request.provider,
            model=request.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=int((time.time() - start_time) * 1000),
            trace_id=current_trace_id(),
            user_id=request.user_id,
        )

        return response
```

### 2.2 Pricing Information Management

**Model-specific pricing table (auto-updatable)**:

```python
# src/agent_platform/platform/cost/pricing.py

PRICING_TABLE = {
    "openai": {
        "gpt-4-turbo": {
            "input": 0.01 / 1000,   # $0.01 per 1K tokens
            "output": 0.03 / 1000,
        },
        "gpt-3.5-turbo": {
            "input": 0.0005 / 1000,
            "output": 0.0015 / 1000,
        },
    },
    "anthropic": {
        "claude-3-opus": {
            "input": 0.015 / 1000,
            "output": 0.075 / 1000,
        },
        "claude-3-sonnet": {
            "input": 0.003 / 1000,
            "output": 0.015 / 1000,
        },
    },
    "google": {
        "gemini-pro": {
            "input": 0.00025 / 1000,
            "output": 0.0005 / 1000,
        },
    },
}

class PricingManager:
    def calculate_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int
    ) -> Decimal:
        pricing = PRICING_TABLE[provider][model]
        input_cost = Decimal(str(pricing["input"])) * input_tokens
        output_cost = Decimal(str(pricing["output"])) * output_tokens
        return input_cost + output_cost
```

### 2.3 Cost Aggregation and Alerts

**Real-time dashboard aggregation**:

```python
class CostAggregator:
    async def get_daily_cost(
        self,
        date: datetime.date,
        group_by: List[str] = ["provider", "model"]
    ) -> Dict:
        """Daily cost aggregation"""
        query = """
        SELECT
            provider,
            model,
            SUM(total_cost) as total_cost,
            SUM(total_tokens) as total_tokens,
            COUNT(*) as call_count
        FROM llm_usage_records
        WHERE DATE(created_at) = $1
        GROUP BY provider, model
        ORDER BY total_cost DESC
        """
        return await self.db.fetch(query, date)

    async def check_budget_alert(self, user_id: str):
        """Check budget overrun"""
        monthly_cost = await self.get_user_monthly_cost(user_id)
        budget = await self.get_user_budget(user_id)

        if monthly_cost >= budget * 0.8:  # 80% reached
            await self.send_alert(
                user_id,
                f"Budget 80% reached: ${monthly_cost:.2f} / ${budget:.2f}"
            )
```

---

## 3. Integrated Observability Stack

### 3.1 Data Flow

```
Application
    ↓
[Structlog] → JSON Logs → File/Stdout
    ↓
[OpenTelemetry SDK]
    ├─→ Traces → OTLP Collector → Jaeger/Tempo
    ├─→ Metrics → Prometheus
    └─→ Logs → Loki
    ↓
[Database]
    ├─→ PostgreSQL (Traces, Costs)
    └─→ TimescaleDB (Time-series optimization)
    ↓
[Visualization]
    ├─→ Grafana (Unified dashboard)
    └─→ Custom Admin UI
```

### 3.2 Prometheus Metrics

**Metrics to expose**:

```python
from prometheus_client import Counter, Histogram, Gauge

# LLM call count
llm_calls_total = Counter(
    'llm_calls_total',
    'Total LLM API calls',
    ['provider', 'model', 'status']
)

# LLM call latency
llm_latency_seconds = Histogram(
    'llm_latency_seconds',
    'LLM API call latency',
    ['provider', 'model'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Token usage
llm_tokens_used = Counter(
    'llm_tokens_used',
    'Total tokens consumed',
    ['provider', 'model', 'token_type']  # input/output
)

# Cost
llm_cost_total = Counter(
    'llm_cost_total',
    'Total cost in USD',
    ['provider', 'model']
)

# Currently active requests
active_requests = Gauge(
    'active_requests',
    'Currently active agent requests'
)
```

### 3.3 FastAPI Instrumentation

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()

# OpenTelemetry auto-instrumentation
FastAPIInstrumentor.instrument_app(app)

# Prometheus metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

---

## 4. Error Tracking and Alerts

### 4.1 Sentry Integration (Optional)

```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

sentry_sdk.init(
    dsn=settings.SENTRY_DSN,
    integrations=[FastApiIntegration()],
    traces_sample_rate=0.1,  # 10% sampling
    environment=settings.ENVIRONMENT,
)
```

### 4.2 Custom Alert Rules

```python
class AlertManager:
    async def check_anomalies(self):
        """Anomaly detection rules"""

        # 1. Cost spike (2x or more vs previous hour)
        current_hour_cost = await self.get_hourly_cost()
        prev_hour_cost = await self.get_hourly_cost(offset=1)
        if current_hour_cost > prev_hour_cost * 2:
            await self.send_alert("cost_spike", current_hour_cost)

        # 2. Error rate increase (over 10%)
        error_rate = await self.get_error_rate()
        if error_rate > 0.1:
            await self.send_alert("high_error_rate", error_rate)

        # 3. Latency increase (P95 > 5 seconds)
        p95_latency = await self.get_latency_percentile(95)
        if p95_latency > 5000:
            await self.send_alert("high_latency", p95_latency)
```

---

## 5. Dashboard Design

### 5.1 Core Metrics Dashboard

**Grafana panel composition**:

1. **Real-time Monitoring**
   - Requests per second (RPS)
   - Average/P95/P99 latency
   - Error rate

2. **Cost Tracking**
   - Hourly cost trends
   - Cost distribution by model
   - Top 10 users by cost

3. **LLM Usage Status**
   - Call distribution by provider
   - Token usage trends
   - Average token count

4. **System Status**
   - Active session count
   - Cache hit rate
   - DB connection pool status

### 5.2 Trace Viewer

**Distributed tracing via Jaeger UI**:
- Track entire flow by Request ID
- Visualize performance bottlenecks in each span
- Immediately identify error occurrence points

---

## 6. Implementation Priorities

### Phase 1: Basic Tracking (MVP)
- [x] Structlog-based JSON logging
- [ ] Basic TraceManager implementation
- [ ] Basic CostTracker implementation
- [ ] PostgreSQL storage

### Phase 2: Standardization
- [ ] OpenTelemetry integration
- [ ] Prometheus metrics
- [ ] OTLP Collector configuration

### Phase 3: Advanced Features
- [ ] Grafana dashboards
- [ ] Real-time alerts
- [ ] Anomaly detection

### Phase 4: Optimization
- [ ] TimescaleDB migration
- [ ] Data retention policies
- [ ] Cost prediction models
