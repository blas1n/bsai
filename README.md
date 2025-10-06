# BSAI - Platform-oriented AI Agent Orchestrator

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**BSAI** is an enterprise-grade AI Agent orchestrator platform. It's not just a simple agent, but a **platform with built-in LLMOps capabilities**.

## 🎯 Key Features

### 🤖 Multi-Interface Support
- **REST API**: RESTful interface for web frontends
- **WebSocket**: Real-time streaming responses
- **MCP (Model Context Protocol)**: Direct access for LLMs like Claude

### 🔄 Multi-Vendor LLM Integration
Use multiple LLM vendors through a unified interface:
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude 3)
- Google (Gemini)
- Extensible for additional vendors

### 📊 LLMOps Platform Features
- **Centralized Prompt Store**: Git-style version control, rollback, change history
- **Cost Tracking**: Real-time token-level cost monitoring
- **Distributed Tracing**: Complete request tracing with OpenTelemetry
- **Experimentation Platform**: A/B testing and prompt quality evaluation
- **Security**: Automatic PII filtering, RBAC, audit logs

### 🏗️ Production-Ready Architecture
- **100% Containerized**: Zero external dependencies, instant GitHub Codespaces execution
- High-performance async/await
- PostgreSQL + Redis
- Prometheus metrics
- Structured logging
- TDD/DDD-based development

## 🚀 Quick Start

### 🎯 Easiest Way: GitHub Codespaces (Recommended!)

**No installation required!**

1. [Create Codespace from this repository](https://github.com/yourusername/bsai/codespaces)
2. Wait 3-5 minutes (automatic setup)
3. In terminal: `uvicorn src.agent_platform.main:app --reload`
4. Access automatically forwarded port 8000 in browser!

Details: [GitHub Codespaces Guide](docs/deployment/codespaces.md)

### 💻 Local Development: Docker Compose

**Prerequisites**: Docker Desktop only

```bash
# 1. Clone & setup
git clone https://github.com/yourusername/bsai.git
cd bsai
cp .env.example .env
# Add your API keys to .env

# 2. Start full stack (PostgreSQL + Redis + Dev environment)
docker compose -f docker-compose.dev.yml up -d

# 3. Access dev container
docker compose exec app bash

# 4. Run server
uvicorn src.agent_platform.main:app --reload --host 0.0.0.0
```

### 💎 VS Code Dev Containers (Recommended!)

**Prerequisites**: VS Code + Docker Desktop + Dev Containers extension

```bash
# 1. Clone & open
git clone https://github.com/yourusername/bsai.git
code bsai

# 2. In VS Code: F1 → "Dev Containers: Reopen in Container"
# 3. Automatic build and all services start
# 4. Start developing immediately!
```

All setup is done automatically! 🎉

API Documentation: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)

## 📖 Documentation

### Core Documentation
- [Installation Guide](docs/guides/installation.md) - Container-based installation
- [GitHub Codespaces Guide](docs/deployment/codespaces.md) - How to use Codespaces
- [Docker Guide](DOCKER_GUIDE.md) - **Two Dockerfiles explained**
- [Containerization Strategy](CONTAINERIZATION.md) - 100% containerization details
- [Architecture Overview](docs/architecture/overview.md) - System architecture

### Full Documentation
Full documentation: [https://bsai.readthedocs.io](https://bsai.readthedocs.io)

Build docs locally:
```bash
pip install -e ".[docs]"
mkdocs serve
```

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Interfaces Layer                       │
│   REST API │ WebSocket │ MCP Server                     │
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

### Directory Structure

```
bsai/
├── src/agent_platform/          # Main source code
│   ├── core/                    # Agent core logic
│   │   ├── llm/                # LLM abstraction layer
│   │   ├── orchestrator/       # Task planning & execution
│   │   ├── memory/             # Context management
│   │   └── tools/              # Tool registry
│   ├── platform/               # Platform features
│   │   ├── prompt_store/       # Prompt versioning
│   │   ├── trace/              # Distributed tracing
│   │   ├── cost/               # Cost tracking
│   │   ├── experiments/        # A/B testing
│   │   └── security/           # Security & PII filtering
│   ├── interfaces/             # External interfaces
│   │   ├── api/               # FastAPI routers
│   │   └── mcp/               # MCP server
│   ├── infrastructure/         # Infrastructure layer
│   │   ├── database/          # PostgreSQL
│   │   ├── cache/             # Redis
│   │   └── messaging/         # Event bus (future)
│   └── domain/                # Domain models
├── tests/                     # Tests
│   ├── unit/                 # Unit tests
│   ├── integration/          # Integration tests
│   └── e2e/                  # E2E tests
├── docs/                     # MkDocs documentation
└── migrations/               # Alembic migrations
```

## 💡 Use Cases

### 1. Customer Support Agent
```python
response = await agent.execute(
    message="Customer is asking about refund policy",
    tools=["knowledge_base", "ticket_system", "escalation"]
)
```

### 2. Code Review Assistant
```python
response = await agent.execute(
    message="Review this pull request",
    context={"repo": "myorg/myrepo", "pr": 123},
    tools=["git", "linter", "security_scanner"]
)
```

### 3. Research Agent
```python
response = await agent.execute(
    message="Research latest trends in quantum computing",
    tools=["web_search", "paper_search", "summarization"]
)
```

## 🔧 Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Framework** | FastAPI | Async web framework |
| **Database** | PostgreSQL | Primary datastore |
| **Cache** | Redis | Session & caching |
| **LLM SDK** | LiteLLM | Multi-provider abstraction |
| **Tracing** | OpenTelemetry | Distributed tracing |
| **Metrics** | Prometheus | Monitoring |
| **Logging** | Structlog | Structured JSON logs |
| **Testing** | pytest | Test framework |
| **Docs** | MkDocs Material | Documentation |
| **Package Manager** | UV | Fast dependency management |

## 🛠️ Development

### Setup Development Environment

```bash
# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Lint
ruff check src/
black src/

# Type check
mypy src/
```

### Development Philosophy

#### 1️⃣ TDD (Test-Driven Development)
Write tests first for all features.

```python
# 1. Write test
def test_prompt_versioning():
    prompt = create_prompt(name="test", content="v1")
    assert prompt.version == 1

# 2. Implement
def create_prompt(name, content):
    return Prompt(name=name, content=content, version=1)

# 3. Refactor
```

#### 2️⃣ DDD (Documentation-Driven Development)
Write design documents first, then implement.

- Architecture: `docs/architecture/`
- API Specs: `docs/api/`
- Guides: `docs/guides/`

#### 3️⃣ Clean Architecture
- Dependency inversion
- Separation of concerns
- Testable components

### Project Structure Principles

```
interfaces → core → platform → infrastructure
     ↓        ↓        ↓
  domain ← domain ← domain
```

## 📊 Observability

### Metrics (Prometheus)

```bash
# Metrics endpoint
curl http://localhost:8000/metrics
```

Key metrics:
- `llm_calls_total` - Total LLM API calls
- `llm_latency_seconds` - LLM call latency
- `llm_tokens_used` - Token consumption
- `llm_cost_total` - Total cost in USD

### Tracing (OpenTelemetry)

All requests are automatically traced:

```
agent.execute (123ms)
  ├─ planner.plan (45ms)
  │   └─ llm.chat_completion (40ms)
  ├─ executor.execute (65ms)
  │   ├─ tool.web_search (30ms)
  │   └─ llm.chat_completion (30ms)
  └─ memory.store (3ms)
```

### Logging (Structlog)

Structured JSON logs:

```json
{
  "event": "llm_call_completed",
  "timestamp": "2025-10-05T12:34:56.789Z",
  "trace_id": "a1b2c3d4...",
  "provider": "openai",
  "model": "gpt-4",
  "tokens": 1234,
  "cost": 0.0246,
  "latency_ms": 850
}
```

## 🔐 Security

### Authentication
- JWT-based authentication
- API key support
- OAuth2 integration (planned)

### PII Protection
Automatic detection and masking:

```python
input: "My email is john@example.com"
output: "My email is ***@***"
```

### Access Control
- Role-based access control (RBAC)
- Resource-level permissions
- Audit logging

## 🧪 Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/core/test_llm_base.py

# Run with coverage
pytest --cov=src --cov-report=html

# Run only fast tests
pytest -m "not slow"
```

Test structure:
- **Unit tests**: Test individual components
- **Integration tests**: Test component interactions
- **E2E tests**: Test full workflows

## 📈 Roadmap

### Phase 1: MVP (Current)
- [x] Project structure
- [x] Core architecture design
- [x] Database schema design
- [x] FastAPI skeleton
- [x] Basic LLM abstraction
- [ ] OpenAI provider implementation
- [ ] Basic orchestrator
- [ ] Cost tracker

### Phase 2: Platform Features
- [ ] Full prompt versioning
- [ ] Experiment framework
- [ ] Advanced tracing
- [ ] MCP server
- [ ] PII filtering

### Phase 3: Production Ready
- [ ] Performance optimization
- [ ] Monitoring dashboard
- [ ] Auto-scaling support
- [ ] Load testing
- [ ] Production deployment

### Phase 4: Enterprise
- [ ] Multi-tenancy
- [ ] SSO integration
- [ ] Advanced RBAC
- [ ] Compliance features
- [ ] SLA monitoring

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](docs/guides/contributing.md) for details.

### Getting Started

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for your changes
4. Implement your changes
5. Run tests (`pytest`)
6. Commit with conventional commits (`git commit -m "feat: add amazing feature"`)
7. Push to your fork (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Inspired by [Woowa Brothers' LLM Platform Architecture](https://techblog.woowahan.com/)
- Built with [FastAPI](https://fastapi.tiangolo.com)
- Powered by [OpenTelemetry](https://opentelemetry.io)

## 📞 Contact & Support

- **Documentation**: [https://bsai.readthedocs.io](https://bsai.readthedocs.io)
- **Issues**: [GitHub Issues](https://github.com/yourusername/bsai/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/bsai/discussions)

---

**Built with ❤️ for the future of AI Agent platforms**
