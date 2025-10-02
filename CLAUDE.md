# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Essential Commands

### Package Management
```bash
# Install dependencies in dev container
uv sync --extra dev

# Load environment variables manually if needed
source scripts/load-env.sh
```

### Testing
```bash
# Run all tests with coverage
uv run pytest

# Run specific test categories
uv run pytest tests/unit/          # Unit tests
uv run pytest tests/integration/   # Integration tests
uv run pytest tests/security/      # Security tests

# Run single test file
uv run pytest tests/unit/test_specific.py

# Coverage report
uv run pytest --cov=bsai --cov-report=html
```

### Code Quality
```bash
# Format and lint (run before commits)
uv run black .
uv run isort .
uv run ruff check .
uv run mypy bsai/

# Security scanning
gitleaks detect --config .gitleaks.toml
```

### Application
```bash
# CLI commands
python -m bsai.cli.main status
python -m bsai.cli.main hello "Name"

# Documentation server
uv run mkdocs serve  # http://localhost:8001
```

## Architecture

### Core Components
- **bsai/cli/**: Typer-based CLI with Rich output formatting
- **bsai/core/config/**: Pydantic settings with multi-provider secret management
- **bsai/core/security/**: Security utilities and secret abstraction layer
- **bsai/core/agents/**: AI agent framework (planned expansion)
- **secrets/**: Standalone secret management with 1Password SDK integration

### Secret Management Architecture
The project uses a sophisticated multi-tier secret management system:

1. **SecretProvider abstraction** (`bsai/core/config/secrets.py`):
   - `EnvironmentSecretProvider`: Environment variables
   - `OnePasswordSecretProvider`: 1Password SDK integration
   - Fallback chain: 1Password ’ Environment ’ Demo mode

2. **Standalone secret manager** (`secrets/secret-manager.py`):
   - Environment detection (Codespaces/Local/CI/Demo)
   - Automatic initialization in dev container post-create
   - 1Password vault mapping: "BSAI Secrets" vault with predefined items

3. **Priority loading sequence**:
   - 1Password SDK (production/local with CLI signed in)
   - .env file (manual configuration)
   - Environment variables (CI/CD)
   - Demo mode (safe defaults for development)

### Development Environment
- **Perfect containerization**: Zero-setup VS Code dev containers
- **Auto-initialization**: Dependencies and secrets configured automatically
- **Environment detection**: Codespaces/Local/CI environments handled differently
- **Port forwarding**: 8000 (API), 8001 (docs)

## Key Patterns

### Testing Framework
- **pytest** with 80% coverage requirement
- Test markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.security`
- Fixtures in `test/conftest.py` for reusable components
- Security tests verify secret management and vulnerability scanning

### Secret Configuration
Never hardcode secrets. Use the SecretManager pattern:
```python
from bsai.core.config.secrets import secret_manager
api_key = secret_manager.get_secret("ANTHROPIC_API_KEY", "demo_fallback")
```

### Code Standards
- **Type annotations required**: Full MyPy compliance
- **Black formatting**: 88 character line length
- **Import organization**: isort with black profile
- **Docstrings**: Google style for public APIs

## Environment Behavior

### Demo Mode
When no real API keys are available, the system automatically enters demo mode:
- `ANTHROPIC_API_KEY=demo_key_safe_mode`
- `BSAI_MODE=demo`
- Safe for development without real API calls

### 1Password Integration
For production use with real API keys:
- Requires "BSAI Secrets" vault in 1Password
- Maps to specific items: "Claude API Key", "Application Secret", "JWT Secret"
- Auto-detects availability and falls back gracefully

### Container Workflow
The dev container handles setup automatically via `.devcontainer/post-create.sh`:
1. Installs dependencies with `uv sync --extra dev`
2. Runs secret detection and loading
3. Creates `.env` file with appropriate values
4. Exports variables to shell environment

## AI Integration Notes
- Current CLI is basic (hello/status commands)
- Architecture designed for LangChain-based agent expansion
- Anthropic Claude integration via official SDK
- Extensible agent framework in `bsai/core/agents/`