# Database Schema Design

## Prompt Store Version Management

### Design Philosophy
- **Git-style Version Control**: Store each change as an immutable version
- **Complete History Tracking**: Track who, when, what, and why changes were made
- **Rollback Capability**: Restore to any previous version with all versions retained
- **Comparison Feature**: Support diff between versions

---

## Table Structure

### 1. prompts - Prompt Metadata
```sql
CREATE TABLE prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) UNIQUE NOT NULL,  -- Prompt identifier (e.g., "customer_support_greeting")
    description TEXT,
    category VARCHAR(100),  -- Classification (e.g., "agent", "tool", "system")
    tags JSONB,  -- Tags for search/filtering
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by VARCHAR(255),  -- Creator ID
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Indexes
    INDEX idx_prompts_name (name),
    INDEX idx_prompts_category (category),
    INDEX idx_prompts_tags USING GIN (tags)
);
```

### 2. prompt_versions - Prompt Version History
```sql
CREATE TABLE prompt_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_id UUID NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,  -- Sequential version number (1, 2, 3, ...)
    content TEXT NOT NULL,  -- Actual prompt content
    template_variables JSONB,  -- Variable definitions required by template (e.g., {"user_name": "string", "context": "string"})

    -- Metadata
    commit_message VARCHAR(500),  -- Reason for change (Git commit message style)
    author VARCHAR(255) NOT NULL,  -- Person who made the change
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Performance metrics (linked to experiment results)
    avg_tokens INTEGER,  -- Average token count
    avg_cost DECIMAL(10, 6),  -- Average cost
    success_rate DECIMAL(5, 2),  -- Success rate (based on experiment results)

    -- Composite unique constraint
    UNIQUE (prompt_id, version_number),

    -- Indexes
    INDEX idx_prompt_versions_prompt_id (prompt_id),
    INDEX idx_prompt_versions_created_at (created_at DESC)
);
```

### 3. prompt_deployments - Prompt Deployment History
```sql
CREATE TABLE prompt_deployments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_id UUID NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    version_id UUID NOT NULL REFERENCES prompt_versions(id),
    environment VARCHAR(50) NOT NULL,  -- "development", "staging", "production"

    deployed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deployed_by VARCHAR(255) NOT NULL,

    -- A/B testing support
    traffic_percentage INTEGER DEFAULT 100 CHECK (traffic_percentage BETWEEN 0 AND 100),
    is_active BOOLEAN DEFAULT true,

    -- Indexes
    INDEX idx_deployments_prompt_env (prompt_id, environment, is_active)
);
```

---

## Trace Logging Schema

### 4. traces - Request Tracking (OpenTelemetry-based)
```sql
CREATE TABLE traces (
    trace_id UUID PRIMARY KEY,
    request_id VARCHAR(255) UNIQUE,

    -- Request information
    user_id VARCHAR(255),
    session_id VARCHAR(255),

    -- Timing
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,

    -- Status
    status VARCHAR(50),  -- "success", "error", "timeout"
    error_message TEXT,

    -- Metadata
    metadata JSONB,  -- Request source, client info, etc.

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Indexes
    INDEX idx_traces_user_id (user_id),
    INDEX idx_traces_session_id (session_id),
    INDEX idx_traces_start_time (start_time DESC),
    INDEX idx_traces_status (status)
);
```

### 5. trace_spans - Detailed Execution Steps
```sql
CREATE TABLE trace_spans (
    span_id UUID PRIMARY KEY,
    trace_id UUID NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
    parent_span_id UUID REFERENCES trace_spans(span_id),

    -- Span information
    name VARCHAR(255) NOT NULL,  -- "llm_call", "tool_execution", "planning"
    span_type VARCHAR(100),  -- "llm", "database", "http", "internal"

    -- Timing
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,

    -- Status
    status VARCHAR(50),
    error_message TEXT,

    -- Span detailed data
    attributes JSONB,  -- Additional attributes (e.g., LLM model name, parameters)

    -- Indexes
    INDEX idx_spans_trace_id (trace_id),
    INDEX idx_spans_parent_id (parent_span_id),
    INDEX idx_spans_type (span_type)
);
```

---

## Cost Tracking Schema

### 6. llm_usage_records - LLM Call Records
```sql
CREATE TABLE llm_usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id UUID REFERENCES traces(trace_id),
    span_id UUID REFERENCES trace_spans(span_id),

    -- LLM information
    provider VARCHAR(100) NOT NULL,  -- "openai", "anthropic", "google"
    model VARCHAR(255) NOT NULL,  -- "gpt-4", "claude-3-opus", "gemini-pro"

    -- Usage
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    total_tokens INTEGER GENERATED ALWAYS AS (input_tokens + output_tokens) STORED,

    -- Cost
    input_cost DECIMAL(10, 6) NOT NULL,
    output_cost DECIMAL(10, 6) NOT NULL,
    total_cost DECIMAL(10, 6) GENERATED ALWAYS AS (input_cost + output_cost) STORED,

    -- Performance
    latency_ms INTEGER,

    -- Context
    user_id VARCHAR(255),
    prompt_id UUID REFERENCES prompts(id),
    prompt_version_id UUID REFERENCES prompt_versions(id),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Indexes
    INDEX idx_usage_provider_model (provider, model),
    INDEX idx_usage_user_id (user_id),
    INDEX idx_usage_created_at (created_at DESC),
    INDEX idx_usage_prompt_id (prompt_id)
);
```

### 7. cost_aggregations - Cost Aggregation (Materialized View)
```sql
CREATE MATERIALIZED VIEW cost_aggregations AS
SELECT
    DATE_TRUNC('hour', created_at) as time_bucket,
    provider,
    model,
    user_id,
    COUNT(*) as call_count,
    SUM(total_tokens) as total_tokens,
    SUM(total_cost) as total_cost,
    AVG(latency_ms) as avg_latency_ms
FROM llm_usage_records
GROUP BY time_bucket, provider, model, user_id;

CREATE UNIQUE INDEX idx_cost_agg_unique
ON cost_aggregations (time_bucket, provider, model, COALESCE(user_id, 'null'));

-- Auto-refresh (hourly)
CREATE INDEX idx_cost_agg_time ON cost_aggregations (time_bucket DESC);
```

---

## Experiment Management Schema

### 8. experiments - Prompt Experiments
```sql
CREATE TABLE experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Experiment configuration
    experiment_type VARCHAR(50),  -- "ab_test", "multi_variant", "evaluation"
    status VARCHAR(50) DEFAULT 'draft',  -- "draft", "running", "completed", "archived"

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE,
    created_by VARCHAR(255),

    -- Metadata
    metadata JSONB,

    INDEX idx_experiments_status (status),
    INDEX idx_experiments_created_at (created_at DESC)
);
```

### 9. experiment_variants - Experiment Variants (Prompt Versions)
```sql
CREATE TABLE experiment_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,

    variant_name VARCHAR(100) NOT NULL,  -- "control", "variant_a", "variant_b"
    prompt_version_id UUID REFERENCES prompt_versions(id),

    traffic_weight INTEGER DEFAULT 50,  -- Traffic distribution ratio

    -- Performance metrics (aggregated)
    total_runs INTEGER DEFAULT 0,
    avg_latency_ms DECIMAL(10, 2),
    avg_cost DECIMAL(10, 6),
    success_count INTEGER DEFAULT 0,

    UNIQUE (experiment_id, variant_name),
    INDEX idx_variants_experiment (experiment_id)
);
```

### 10. experiment_runs - Experiment Execution Records
```sql
CREATE TABLE experiment_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    variant_id UUID NOT NULL REFERENCES experiment_variants(id),
    trace_id UUID REFERENCES traces(trace_id),

    -- Input/Output
    input_data JSONB NOT NULL,
    output_data JSONB,

    -- Evaluation results
    evaluation_scores JSONB,  -- {"accuracy": 0.95, "relevance": 0.88}
    human_feedback INTEGER CHECK (human_feedback BETWEEN 1 AND 5),

    -- Metadata
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    INDEX idx_runs_experiment (experiment_id),
    INDEX idx_runs_variant (variant_id),
    INDEX idx_runs_created_at (created_at DESC)
);
```

---

## User and Security Schema

### 11. users - Users
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,

    is_active BOOLEAN DEFAULT true,
    is_superuser BOOLEAN DEFAULT false,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    INDEX idx_users_email (email),
    INDEX idx_users_username (username)
);
```

### 12. api_keys - API Key Management
```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    key_hash VARCHAR(255) UNIQUE NOT NULL,  -- API key hash
    name VARCHAR(255),  -- Key alias (e.g., "production_key")

    scopes JSONB,  -- Permission scope (e.g., ["read:prompts", "write:experiments"])

    is_active BOOLEAN DEFAULT true,
    expires_at TIMESTAMP WITH TIME ZONE,
    last_used_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    INDEX idx_api_keys_user (user_id),
    INDEX idx_api_keys_hash (key_hash)
);
```

### 13. audit_logs - Security Audit Logs
```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Who
    user_id UUID REFERENCES users(id),
    api_key_id UUID REFERENCES api_keys(id),
    ip_address INET,

    -- What
    action VARCHAR(255) NOT NULL,  -- "create_prompt", "delete_experiment", "access_trace"
    resource_type VARCHAR(100),  -- "prompt", "experiment", "trace"
    resource_id UUID,

    -- When
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Details
    details JSONB,
    result VARCHAR(50),  -- "success", "failure", "denied"

    INDEX idx_audit_user (user_id),
    INDEX idx_audit_timestamp (timestamp DESC),
    INDEX idx_audit_action (action)
);
```

---

## Data Retention Policy

```sql
-- Auto-cleanup of old trace data (90+ days)
CREATE OR REPLACE FUNCTION cleanup_old_traces()
RETURNS void AS $$
BEGIN
    DELETE FROM traces
    WHERE created_at < NOW() - INTERVAL '90 days';
END;
$$ LANGUAGE plpgsql;

-- Run daily at midnight
-- (In practice, use pg_cron or external scheduler)
```

---

## Index Optimization Strategy

1. **Prompt Queries**: Frequent searches by name, category
2. **Version History**: Combined queries by prompt_id + version_number
3. **Trace Analysis**: Time-range query optimization (consider BRIN indexes)
4. **Cost Aggregation**: Materialized View for real-time dashboard support
5. **Experiment Results**: Composite index on experiment_id + created_at

---

## Migration Strategy

- Use **Alembic** for version control
- Initial migration file: `migrations/versions/001_initial_schema.py`
- Always create migration files for schema changes
- Ensure rollback capability by writing downgrade functions
