# BSAI - LangGraph-based Multi-Agent LLM Orchestration System

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.0.20+-orange.svg)](https://github.com/langchain-ai/langgraph)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**BSAI** is a production-ready multi-agent LLM orchestration system built with LangGraph. It automatically optimizes costs, validates outputs, and preserves context across sessions.

## Key Features

### 1. Token Cost Optimization
- **Automatic LLM Selection**: Choose the cheapest LLM based on task complexity
- **5 Complexity Levels**: TRIVIAL, SIMPLE, MODERATE, COMPLEX, CONTEXT_HEAVY
- **Real-time Cost Tracking**: Monitor token usage and costs per session

### 2. Quality Assurance
- **Independent QA Agent**: Validates all Worker outputs
- **Automatic Retries**: Max 3 attempts with structured feedback
- **Acceptance Criteria**: Task-specific validation rules

### 3. Context Preservation
- **Memory System**: Automatic context compression when capacity reached
- **Session Snapshots**: Pause and resume sessions seamlessly
- **Key Decision Tracking**: Extract and store critical information

### 4. Production-Ready Architecture
- **100% Async**: FastAPI + SQLAlchemy async + asyncpg
- **PostgreSQL + Redis**: Robust data and cache layer
- **Docker Compose**: Single-command deployment
- **Type-Safe**: Full type hints with mypy strict mode

## Architecture Overview

### 5 Specialized Agents

```
┌─────────────────────────────────────────────────────────────┐
│                      User Request                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Conductor Agent (Lightweight LLM)                          │
│  - Break request into milestones                            │
│  - Select optimal LLM per milestone                         │
│  - Monitor context usage                                    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Meta Prompter Agent (Medium LLM, if complexity >= MODERATE)│
│  - Generate optimized prompts for Worker                    │
│  - Apply task-type-specific strategies                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Worker Agent (Dynamic LLM based on Conductor's selection)  │
│  - Execute actual task                                      │
│  - Use generated prompt from Meta Prompter                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  QA Agent (Medium LLM)                                      │
│  - Validate Worker output                                   │
│  - Provide structured feedback                              │
│  - Decide: pass/fail/retry                                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Summarizer Agent (Medium LLM, when memory pressure)        │
│  - Compress context to free memory                          │
│  - Preserve key decisions and artifacts                     │
└─────────────────────────────────────────────────────────────┘
```

### LangGraph Workflow

```python
Entry → analyze_task → select_llm → [generate_prompt?] → execute_worker
         → verify_qa → [retry/fail/next]
         → check_context → [summarize?]
         → advance → [next_milestone/complete]
```

### Database Schema (9 Tables)

1. **user_settings**: QA retries, preferred LLM, cost limits
2. **sessions**: Session tracking with total tokens/cost
3. **tasks**: User requests and final results
4. **milestones**: Individual task steps with complexity
5. **memory_snapshots**: Compressed context summaries
6. **llm_usage_logs**: Detailed LLM call tracking
7. **system_prompts**: Versioned agent prompts
8. **generated_prompts**: Meta Prompter outputs
9. **prompt_usage_history**: Prompt performance tracking

## Quick Start

### Prerequisites

- Docker Desktop
- Python 3.11+ (for local development)

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/bsai.git
cd bsai
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your API keys:
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Start with Docker Compose

```bash
# Start PostgreSQL and Redis
docker-compose up -d

# Run database migrations
alembic upgrade head

# Start API server
uvicorn src.agent.main:app --reload
```

API will be available at: http://localhost:8000

API Documentation: http://localhost:8000/docs

### 4. VS Code Dev Container (Recommended)

**Prerequisites**: VS Code + Docker + Dev Containers extension

1. Open project in VS Code
2. Press `F1` → "Dev Containers: Reopen in Container"
3. Wait for container build (automatic)
4. All services start automatically

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Orchestration** | LangGraph | State machine workflow |
| **Framework** | FastAPI | Async web framework |
| **Database** | PostgreSQL 16 | Primary datastore |
| **Cache** | Redis | Session & caching |
| **LLM Client** | LiteLLM | Unified multi-provider interface |
| **ORM** | SQLAlchemy 2.0 | Async database access |
| **Migrations** | Alembic | Database schema versioning |
| **Templates** | Jinja2 | Prompt template system |
| **Token Counting** | tiktoken | Cost estimation |
| **Retry Logic** | Tenacity | Exponential backoff |
| **Logging** | Structlog | Structured JSON logs |
| **Testing** | pytest | Test framework |
| **Type Checking** | mypy | Static type analysis |
| **Docs** | MkDocs Material | Documentation |

## Directory Structure

```
bsai/
├── src/agent/                  # Main source code
│   ├── db/                    # Database layer
│   │   ├── base.py           # SQLAlchemy declarative base
│   │   ├── session.py        # Async session factory
│   │   ├── models/           # 9 SQLAlchemy models
│   │   └── repository/       # Data access layer
│   ├── llm/                  # LLM layer
│   │   ├── client.py         # LiteLLM wrapper
│   │   ├── router.py         # LLM selection logic
│   │   ├── models.py         # Model definitions with pricing
│   │   └── logger.py         # Usage logging
│   ├── core/                 # Agent implementations
│   │   ├── conductor.py
│   │   ├── meta_prompter.py
│   │   ├── worker.py
│   │   ├── qa_agent.py
│   │   └── summarizer.py
│   ├── graph/                # LangGraph workflow
│   │   ├── state.py          # AgentState TypedDict
│   │   ├── nodes.py          # Graph node functions
│   │   └── workflow.py       # StateGraph composition
│   ├── memory/               # Memory management
│   │   ├── context.py        # Context buffer
│   │   ├── snapshot.py       # Snapshot manager
│   │   └── compressor.py     # Context compression
│   ├── prompts/              # Prompt system
│   │   ├── loader.py         # Jinja2 template loader
│   │   ├── version.py        # Prompt versioning
│   │   └── templates/        # Agent prompt templates
│   ├── api/                  # FastAPI layer
│   │   ├── dependencies.py   # FastAPI dependencies
│   │   └── routes/           # API endpoints
│   ├── schemas/              # Pydantic models
│   └── utils/                # Utilities
│       ├── tokens.py         # Token counting
│       └── logger.py         # Structured logging
├── tests/                    # Tests
│   ├── unit/                # Unit tests
│   ├── integration/         # Integration tests
│   └── e2e/                 # E2E tests
├── docs/                    # MkDocs documentation
├── migrations/              # Alembic migrations
└── docker-compose.yml       # Docker services
```

## Development

### Setup Development Environment

```bash
# Install dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Type check
mypy src/

# Lint
ruff check src/
black src/
```

### Development Philosophy

#### 1. Type Safety First
- Full type hints on all functions
- mypy strict mode enabled
- Type stubs for all dependencies

#### 2. Test-Driven Development
- Write tests before implementation
- 80%+ test coverage target
- Mock LLM responses in tests

#### 3. Database-First Design
- All state persisted to PostgreSQL
- Async operations throughout
- Repository pattern for data access

## API Usage

### Create Task

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "original_request": "Analyze this codebase and suggest improvements",
    "session_id": "optional-session-id"
  }'
```

### Get Task Status

```bash
curl http://localhost:8000/api/v1/tasks/{task_id}
```

### Stream Task Progress (WebSocket)

```python
import asyncio
import websockets

async def stream_task():
    uri = "ws://localhost:8000/api/v1/tasks/{task_id}/stream"
    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            print(message)

asyncio.run(stream_task())
```

### Pause Session

```bash
curl -X POST http://localhost:8000/api/v1/sessions/{session_id}/pause
```

### Resume Session

```bash
curl -X POST http://localhost:8000/api/v1/sessions/{session_id}/resume
```

## Configuration

### Environment Variables

```bash
# LLM API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_AI_API_KEY=...

# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/bsai

# Redis
REDIS_URL=redis://localhost:6379/0

# Workflow Configuration
DEFAULT_QA_MAX_RETRIES=3
CONTEXT_WARNING_THRESHOLD=0.8
SUMMARIZATION_THRESHOLD=0.85

# Cost Limits
DAILY_COST_LIMIT_USD=50.0

# LiteLLM
LITELLM_LOG_LEVEL=INFO
LITELLM_DROP_PARAMS=true
```

## Cost Optimization Example

```python
# TRIVIAL task uses GPT-4o-mini ($0.00015/1k tokens)
task1 = "What is 2+2?"

# MODERATE task uses Claude 3.5 Sonnet ($0.003/1k tokens)
task2 = "Analyze this 50-line Python function for bugs"

# COMPLEX task uses GPT-4o ($0.005/1k tokens)
task3 = "Design a microservices architecture for e-commerce"

# System automatically selects optimal LLM for each milestone
```

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/llm/test_router.py

# Run with coverage
pytest --cov=src --cov-report=html

# Run integration tests only
pytest tests/integration/

# Run fast tests only
pytest -m "not slow"
```

## Documentation

### Build Documentation Locally

```bash
pip install -e ".[docs]"
mkdocs serve
# Open http://localhost:8001
```

### Full Documentation

- [Architecture Overview](docs/architecture/overview.md)
- [Database Schema](docs/architecture/database_schema.md)
- [API Reference](docs/api/rest.md)
- [Development Guide](docs/guides/development.md)

## Roadmap

### Phase 1: Foundation (Current)
- [x] Database schema (9 tables)
- [x] Alembic migrations setup
- [ ] All 9 SQLAlchemy models
- [ ] Repository layer
- [ ] LiteLLM client wrapper

### Phase 2: Core Agents
- [ ] Conductor Agent
- [ ] Meta Prompter Agent
- [ ] Worker Agent
- [ ] QA Agent
- [ ] Summarizer Agent

### Phase 3: LangGraph Workflow
- [ ] State definitions
- [ ] Node functions
- [ ] Workflow composition
- [ ] Conditional routing

### Phase 4: API & Memory
- [ ] FastAPI endpoints
- [ ] Memory system
- [ ] WebSocket streaming
- [ ] Session management

### Phase 5: Production
- [ ] Comprehensive tests
- [ ] Performance optimization
- [ ] Monitoring dashboard
- [ ] Production deployment guide

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](docs/guides/contributing.md) for details.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for your changes
4. Implement your changes
5. Run tests and type checks
6. Commit with conventional commits (`git commit -m "feat: add amazing feature"`)
7. Push to your fork
8. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [LangGraph](https://github.com/langchain-ai/langgraph)
- Powered by [LiteLLM](https://github.com/BerriAI/litellm)
- Inspired by production LLM orchestration systems

## Contact & Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/bsai/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/bsai/discussions)

---

**Built for production-grade AI agent orchestration**
