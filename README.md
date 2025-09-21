# BSAI - BS AI Agent

> **Perfect Containerization** meets **Enterprise Security** for AI-powered development

[![CI](https://github.com/blas1n/bsai/workflows/CI/badge.svg)](https://github.com/blas1n/bsai/actions)
[![Security Scan](https://github.com/blas1n/bsai/workflows/Security%20Scan/badge.svg)](https://github.com/blas1n/bsai/actions)
[![codecov](https://codecov.io/gh/blas1n/bsai/branch/main/graph/badge.svg)](https://codecov.io/gh/blas1n/bsai)

BSAI is an advanced AI agent system designed for developers who demand both cutting-edge AI capabilities and uncompromising security. Built with perfect containerization principles, it delivers a zero-setup development experience while maintaining enterprise-grade security standards.

## ✨ Key Features

### 🚀 Perfect Containerization
- **Zero Manual Setup**: Clone → Open → Container → Ready
- **No Scripts Required**: No Makefile, setup.sh, or manual commands
- **Universal Compatibility**: Works identically everywhere
- **Instant Productivity**: Start coding immediately

### 🔐 Enterprise Security
- **Zero Secret Exposure**: Never commits secrets to repository
- **Multi-Layer Protection**: GitLeaks, Bandit, Safety scanning
- **Smart Secret Management**: Auto-detects environment and configures appropriately
- **Continuous Monitoring**: Real-time security scanning in CI/CD

### 🤖 AI-Powered Development
- **Claude Integration**: Advanced AI assistance powered by Anthropic Claude
- **LangChain Framework**: Sophisticated AI agent orchestration
- **Multiple Agent Types**: Chat, Code Generation, Data Analysis, Documentation
- **Extensible Architecture**: Easy to add new AI capabilities

### 🛠 Modern Development Stack
- **Python 3.11+**: Latest Python features and performance
- **FastAPI**: High-performance async web framework
- **Typer**: Beautiful CLI interfaces
- **Rich**: Stunning terminal output
- **uv**: Lightning-fast package management

## 🚀 Quick Start

### Prerequisites
- [VS Code](https://code.visualstudio.com/) with [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)

### Get Started (3 Steps)

```bash
# 1. Clone the repository
git clone https://github.com/blas1n/bsai.git
cd bsai

# 2. Open in VS Code
code .

# 3. Reopen in Container (VS Code will prompt)
# Click "Reopen in Container" when prompted
```

**That's it!** Everything else happens automatically:
- Dependencies install automatically
- Development tools configure automatically  
- Security scanning runs automatically
- Environment detects and configures secrets automatically

### Verify Installation

```bash
# Check system status
python -m bsai.cli.main status

# Say hello
python -m bsai.cli.main hello "Your Name"

# Run tests
uv run pytest

# View documentation
uv run mkdocs serve
```

## 🏗 Architecture

### Project Structure
```
bsai/
├── 🤖 bsai/                    # Core AI agent system
│   ├── cli/                    # Command-line interface
│   ├── core/                   # Business logic
│   │   ├── agents/             # AI agent implementations
│   │   ├── config/             # Configuration management
│   │   └── security/           # Security utilities
│   └── utils/                  # Shared utilities
├── 🔐 secrets/                 # Secret management system
├── 🧪 tests/                   # Comprehensive test suite
├── 📚 docs/                    # Documentation
├── 🐳 .devcontainer/          # Perfect containerization
└── 🌐 .github/                # CI/CD and automation
```

### Technology Stack

#### Core Technologies
- **[Python 3.11+](https://python.org)**: Modern Python with latest features
- **[uv](https://github.com/astral-sh/uv)**: Ultra-fast Python package manager
- **[FastAPI](https://fastapi.tiangolo.com/)**: High-performance web framework
- **[Typer](https://typer.tiangolo.com/)**: Modern CLI framework

#### AI & ML Stack
- **[Anthropic Claude](https://www.anthropic.com/)**: Advanced language model
- **[LangChain](https://langchain.com/)**: AI application framework
- **[Pydantic](https://pydantic.dev/)**: Data validation and settings

#### Development Tools
- **[pytest](https://pytest.org/)**: Advanced testing framework
- **[Black](https://black.readthedocs.io/)**: Code formatting
- **[Ruff](https://ruff.rs/)**: Fast Python linter
- **[MyPy](https://mypy.readthedocs.io/)**: Static type checking

#### Security Tools
- **[GitLeaks](https://gitleaks.io/)**: Secret detection and prevention
- **[Bandit](https://bandit.readthedocs.io/)**: Python security linting
- **[Safety](https://pyup.io/safety/)**: Dependency vulnerability scanning
- **[1Password SDK](https://developer.1password.com/docs/sdks/python/)**: Enterprise secret management

#### Documentation
- **[MkDocs](https://mkdocs.org/)**: Static site generator
- **[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)**: Beautiful documentation theme
- **[mkdocstrings](https://mkdocstrings.github.io/)**: Automatic API documentation

## 🔐 Security Architecture

### Multi-Layer Security Model

#### 1. Secret Management
```
Environment Detection → Secret Provider → Secure Storage
     ↓                       ↓               ↓
Demo/Local/Codespaces → 1Password/Env → Never in Repo
```

#### 2. Continuous Security Scanning
- **Pre-commit**: GitLeaks scan before every commit
- **CI/CD**: Comprehensive security audit on every push
- **Dependency Monitoring**: Automated vulnerability detection
- **Code Analysis**: Static security analysis with Bandit

#### 3. Environment Isolation
- **Demo Mode**: Safe defaults for learning and development
- **Local Development**: 1Password CLI or manual configuration
- **GitHub Codespaces**: Secure cloud-based development
- **Production**: Kubernetes secrets and enterprise tools

### Security Features

✅ **Zero Secret Exposure**: No secrets ever committed to repository  
✅ **Automatic Detection**: Real-time secret scanning and prevention  
✅ **Smart Configuration**: Environment-aware secret management  
✅ **Audit Trail**: Comprehensive security event logging  
✅ **Compliance Ready**: Meets enterprise security standards  

## 🌟 Perfect Containerization

### Design Principles

1. **Zero Manual Steps**: Everything works after container start
2. **No Build Scripts**: No Makefile, setup.sh, or manual commands
3. **Universal Experience**: Identical behavior across all environments
4. **Immediate Productivity**: Start coding without configuration

### Container Features

- **Pre-installed Tools**: All development tools ready to use
- **Automatic Dependencies**: Project dependencies install automatically
- **Smart Defaults**: Safe configuration for immediate functionality
- **Port Management**: Automatic port forwarding and service discovery

### Supported Environments

| Environment | Status | Secret Management | Notes |
|------------|--------|------------------|-------|
| **Local Dev** | ✅ | 1Password CLI / Manual | Full development experience |
| **GitHub Codespaces** | ✅ | Codespaces Secrets | Cloud development ready |
| **VS Code Dev Containers** | ✅ | Auto-detection | Primary development method |
| **CI/CD** | ✅ | GitHub Secrets | Automated testing and deployment |

## 🤖 AI Agent Capabilities

### Current Features

#### 1. Basic Agent Framework
- **CLI Interface**: Command-line interaction with AI agents
- **Status Monitoring**: System health and readiness checks
- **Extensible Design**: Easy to add new agent types

#### 2. Configuration Management
- **Smart Settings**: Pydantic-based configuration with validation
- **Environment Awareness**: Automatic adaptation to runtime environment
- **Secret Integration**: Secure API key and credential management

### Planned Features (Roadmap)

#### 🎯 Phase 1: Core Agents
- **Chat Agent**: Natural language conversation and assistance
- **Code Agent**: Code generation, review, and optimization
- **Data Agent**: Data analysis and visualization
- **Documentation Agent**: Automatic documentation generation

#### 🎯 Phase 2: Advanced Features
- **Web Search Integration**: Real-time information retrieval
- **File Processing**: Document analysis and manipulation
- **Workflow Automation**: Complex multi-step task execution
- **Memory Management**: Conversation history and context retention

#### 🎯 Phase 3: Enterprise Features
- **Multi-Agent Orchestration**: Coordinated agent workflows
- **Custom Agent Creation**: User-defined agent capabilities
- **API Integrations**: External service connectivity
- **Performance Optimization**: Scalability and efficiency improvements

## 🚀 Usage Examples

### Basic CLI Usage

```bash
# Check system status
python -m bsai.cli.main status

# Interactive hello command
python -m bsai.cli.main hello "Developer"

# Get help
python -m bsai.cli.main --help
```

### Development Workflow

```bash
# Run tests
uv run pytest

# Format code
uv run black .
uv run isort .

# Lint code
uv run ruff check .
uv run mypy bsai/

# Security scan
gitleaks detect

# Serve documentation
uv run mkdocs serve
```

### Secret Management

```bash
# Initialize secret system (automatic)
python secrets/secret-manager.py init

# Manual setup (if needed)
python secrets/secret-manager.py setup

# 1Password sync (if available)
python secrets/secret-manager.py sync
```

## 🧪 Testing

### Test Categories

- **Unit Tests**: Individual component testing
- **Integration Tests**: System interaction testing
- **Security Tests**: Secret management and vulnerability testing
- **Performance Tests**: Load and stress testing (planned)

### Running Tests

```bash
# All tests
uv run pytest

# Unit tests only
uv run pytest tests/unit/

# Integration tests
uv run pytest tests/integration/

# Security tests
uv run pytest tests/security/

# With coverage
uv run pytest --cov=bsai --cov-report=html
```

### Test Configuration

Tests are configured with:
- **Automatic discovery**: pytest finds tests automatically
- **Fixtures**: Reusable test components in `conftest.py`
- **Markers**: Categorized test execution (`@pytest.mark.unit`)
- **Coverage**: Minimum 80% coverage requirement

## 📖 Documentation

### Available Documentation

- **[User Guide](docs/index.md)**: Getting started and basic usage
- **[Security Guide](docs/security/secret-management.md)**: Secret management and security practices
- **[API Reference](http://localhost:8001)**: Automatic API documentation (when serving)

### Building Documentation

```bash
# Build static documentation
uv run mkdocs build

# Serve documentation locally
uv run mkdocs serve

# Documentation will be available at http://localhost:8001
```

## 🤝 Contributing

### Development Setup

The project uses perfect containerization, so setup is automatic:

1. Fork and clone the repository
2. Open in VS Code
3. Click "Reopen in Container" when prompted
4. Start developing immediately

### Code Standards

- **Code Style**: Black formatting, isort imports
- **Type Hints**: Full type annotation required
- **Documentation**: Google-style docstrings
- **Testing**: Minimum 80% test coverage
- **Security**: All commits scanned for secrets

### Pull Request Process

1. **Create Feature Branch**: `git checkout -b feature/your-feature`
2. **Develop & Test**: Use the containerized environment
3. **Security Scan**: `gitleaks detect` before committing
4. **Submit PR**: Include tests and documentation updates

### Code Quality Gates

All PRs must pass:
- ✅ Security scanning (GitLeaks, Bandit, Safety)
- ✅ Code formatting (Black, isort)
- ✅ Linting (Ruff, MyPy)
- ✅ Test coverage (minimum 80%)
- ✅ Documentation updates

## 📊 Project Status

### Current Status: **Alpha Development**

- ✅ **Perfect Containerization**: Complete
- ✅ **Security Framework**: Complete
- ✅ **Basic CLI**: Complete
- ✅ **Test Framework**: Complete
- ✅ **Documentation System**: Complete
- 🔄 **AI Agent Implementation**: In Progress
- 📋 **Advanced Features**: Planned

### Version History

- **v0.1.0**: Initial release with containerization and security framework

### Metrics

- **Security Score**: A+ (GitLeaks, Bandit, Safety)
- **Code Coverage**: 80%+ target
- **Documentation**: Auto-generated and maintained
- **Container Size**: Optimized for development speed

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

### Getting Help

- **Documentation**: [Project Documentation](http://localhost:8001)
- **Issues**: [GitHub Issues](https://github.com/blas1n/bsai/issues)
- **Discussions**: [GitHub Discussions](https://github.com/blas1n/bsai/discussions)

### Common Issues

#### Container Issues
```bash
# Rebuild container
Ctrl+Shift+P → "Dev Containers: Rebuild Container"
```

#### Secret Management Issues
```bash
# Reinitialize secrets
python secrets/secret-manager.py init
```

#### Dependency Issues
```bash
# Reinstall dependencies
uv sync --extra dev
```

## 🎯 Goals and Vision

### Project Goals

1. **Perfect Development Experience**: Zero-friction development environment
2. **Enterprise Security**: Bank-grade security without compromising usability
3. **AI-First Architecture**: Built from the ground up for AI integration
4. **Production Ready**: Scalable from development to enterprise deployment

### Target Use Cases

- **Individual Developers**: Personal AI assistant for coding and productivity
- **Development Teams**: Shared AI-powered development workflows
- **Enterprise**: Secure, compliant AI integration for business applications
- **Education**: Safe environment for learning AI development

### Future Vision

BSAI aims to become the premier platform for secure AI agent development, combining:
- **Cutting-edge AI capabilities** with **enterprise security**
- **Developer productivity** with **operational excellence**
- **Innovation speed** with **production reliability**

---

**Ready to build the future of AI-powered development?** 🚀

[Get Started](#-quick-start) | [View Documentation](docs/) | [Join Community](https://github.com/blas1n/bsai/discussions)