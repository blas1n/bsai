# Installation Guide

BSAI is **100% containerized**, allowing you to start development immediately without complex local setup.

## 🎯 Recommended Method: GitHub Codespaces (Easiest!)

**Zero external dependencies!** Just a browser.

### Quick Start

1. GitHub repository → **Code** → **Codespaces** → **Create codespace**
2. Wait 3-5 minutes (automatic setup)
3. Start developing! 🎉

Details: [GitHub Codespaces Guide](../deployment/codespaces.md)

---

## 🐳 Local Development: Docker Compose (Recommended)

### Prerequisites

- Docker Desktop or Docker Engine + Docker Compose
- Git

**That's all!** No need to install Python, PostgreSQL, or Redis.

### Installation Steps

#### 1. Clone Repository

```bash
git clone https://github.com/yourusername/bsai.git
cd bsai
```

#### 2. Setup Environment Variables

```bash
cp .env.example .env
```

Open `.env` file and add your API keys:

```env
OPENAI_API_KEY=sk-your-openai-key-here
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here
GOOGLE_API_KEY=your-google-ai-key-here
SECRET_KEY=your-random-secret-key-here
```

#### 3. Start Services

```bash
# Start full development stack
docker compose -f docker-compose.dev.yml up -d

# Or for production
docker compose up -d
```

#### 4. Access Dev Container

```bash
# Enter dev container
docker compose exec app bash

# Or use VS Code Dev Containers
code .
# Click "Reopen in Container"
```

#### 5. Run Server

Inside the container:

```bash
uvicorn src.agent_platform.main:app --reload --host 0.0.0.0
```

#### 6. Verify

In browser:
- API Documentation: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)
- Health Check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

### Service Management

```bash
# Check logs
docker compose logs -f app
docker compose logs -f postgres
docker compose logs -f redis

# Stop services
docker compose down

# Complete removal including data
docker compose down -v

# Restart specific service
docker compose restart postgres
```

---

## 💻 VS Code Dev Containers (Recommended)

Provides the smoothest local development experience.

### Prerequisites

- VS Code
- Docker Desktop
- [Dev Containers Extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

### Installation Steps

#### 1. Open Repository

```bash
git clone https://github.com/yourusername/bsai.git
code bsai
```

#### 2. Reopen in Container

In VS Code:
1. `F1` or `Cmd/Ctrl + Shift + P`
2. Select **"Dev Containers: Reopen in Container"**
3. Automatic build and setup (5-10 minutes initially)

#### 3. Start Developing

Terminal automatically opens inside the container:

```bash
# Run server
uvicorn src.agent_platform.main:app --reload

# Run tests
pytest

# Serve documentation
mkdocs serve
```

All ports are automatically forwarded!

### Included Features

- ✅ Python development environment (Pylance, Black, Ruff, mypy)
- ✅ PostgreSQL + Redis auto-start
- ✅ Automatic database migrations
- ✅ Git, GitHub CLI
- ✅ Debugger configuration
- ✅ REST Client
- ✅ SQLTools (DB GUI)

---

## 🧪 Installation Verification

### 1. Service Health Check

```bash
curl http://localhost:8000/api/health/detailed
```

Response:
```json
{
  "status": "healthy",
  "components": {
    "database": "healthy",
    "redis": "healthy"
  }
}
```

### 2. Database Connection

```bash
# Using Docker
docker compose exec postgres psql -U postgres -d bsai -c "SELECT 1"
```

### 3. Redis Connection

```bash
# Using Docker
docker compose exec redis redis-cli ping
```

### 4. Run Tests

```bash
pytest tests/unit/core/test_llm_base.py -v
```

Installation successful when all tests pass!

---

## 🎓 Next Steps

After installation:

1. **Quick Start Guide**: [Quick Start](quickstart.md) (TODO)
2. **Understand Architecture**: [Architecture Overview](../architecture/overview.md)
3. **Explore API**: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)
4. **Codespaces Guide**: [GitHub Codespaces](../deployment/codespaces.md)

---

## 📚 Additional Resources

- [GitHub Codespaces Guide](../deployment/codespaces.md)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [VS Code Dev Containers](https://code.visualstudio.com/docs/devcontainers/containers)
- [Project README](../../README.md)

---

## 🤔 Which Method Should I Choose?

| Method | Difficulty | Setup Time | Recommended For |
|--------|-----------|------------|-----------------|
| **GitHub Codespaces** | ⭐️ | 3-5 min | Everyone (Easiest!) |
| **VS Code Dev Containers** | ⭐️⭐️ | 5-10 min | Local development preference |
| **Docker Compose** | ⭐️⭐️⭐️ | 10-15 min | CLI preference |

**Conclusion: Use GitHub Codespaces or VS Code Dev Containers!**

---

**Happy Coding!** 🚀
