# Developing with GitHub Codespaces

## Overview

BSAI is **100% containerized**, allowing you to start developing immediately in GitHub Codespaces **without any local installation**.

## 🚀 Quick Start

### 1. Starting Codespaces

From the GitHub repository:

1. Click the **Code** button
2. Select the **Codespaces** tab
3. Click **Create codespace on main**

Or access directly via URL:
```
https://github.com/yourusername/bsai/codespaces
```

### 2. Automatic Initialization

When Codespace starts, it automatically:

1. ✅ Builds dev container
2. ✅ Starts and initializes PostgreSQL
3. ✅ Starts Redis
4. ✅ Installs Python dependencies
5. ✅ Runs database migrations
6. ✅ Runs initial tests

**Duration**: About 3-5 minutes (first build)

### 3. Start Developing

In the terminal:

```bash
# Start server
uvicorn src.agent_platform.main:app --reload --host 0.0.0.0 --port 8000

# Or use npm script (to be added)
# npm run dev
```

Access API documentation via port 8000 (automatically opened in browser):
- Swagger UI: `https://<your-codespace-url>-8000.githubpreview.dev/api/docs`

## 📦 Included Services

### Automatically Running Services

| Service | Port | Purpose |
|---------|------|---------|
| **FastAPI** | 8000 | Application server |
| **PostgreSQL** | 5432 | Main database |
| **Redis** | 6379 | Cache and sessions |

### Optional Services (Profile)

To start monitoring stack additionally:

```bash
docker compose --profile monitoring up -d
```

| Service | Port | Purpose |
|---------|------|---------|
| **Prometheus** | 9090 | Metrics collection |
| **Grafana** | 3001 | Visualization dashboard |

## 🛠️ Development Workflow

### Running Server

```bash
# Development mode (auto-reload)
uvicorn src.agent_platform.main:app --reload --host 0.0.0.0

# Or run as Python module
python -m src.agent_platform.main
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Specific test
pytest tests/unit/core/test_llm_base.py -v
```

### Database Operations

```bash
# Connect to PostgreSQL
psql -h postgres -U postgres -d bsai

# Create migration
alembic revision --autogenerate -m "Add new table"

# Apply migration
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

### Redis Operations

```bash
# Connect to Redis CLI
redis-cli -h redis

# Check keys
KEYS *

# Check session data
GET session:uuid-here
```

### Documentation Work

```bash
# Start local docs server
mkdocs serve --dev-addr 0.0.0.0:8001

# Build docs
mkdocs build
```

## 🔍 Health Checks

### Checking Service Status

```bash
# PostgreSQL
pg_isready -h postgres -U postgres -d bsai

# Redis
redis-cli -h redis ping

# FastAPI (when server is running)
curl http://localhost:8000/api/health
```

### Detailed Health Check

```bash
curl http://localhost:8000/api/health/detailed | jq
```

Example response:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "development",
  "components": {
    "database": "healthy",
    "redis": "healthy"
  }
}
```

## 🐛 Debugging

### Using Python Debugger

Add breakpoint in code:

```python
def my_function():
    breakpoint()  # Stops here
    return result
```

Run:
```bash
python -m pytest tests/unit/core/test_llm_base.py
```

### Checking Logs

```bash
# Application logs
tail -f /workspace/logs/app.log

# Docker logs
docker compose logs -f app
docker compose logs -f postgres
docker compose logs -f redis
```

### Accessing Containers

```bash
# PostgreSQL container
docker compose exec postgres bash

# Redis container
docker compose exec redis sh
```

## 🔒 Environment Variables

Managing sensitive information securely in Codespaces:

### Using GitHub Secrets

1. GitHub repository → **Settings** → **Secrets and variables** → **Codespaces**
2. Add these secrets:
   - `OPENAI_API_KEY`
   - `ANTHROPIC_API_KEY`
   - `GOOGLE_API_KEY`
   - `SECRET_KEY`

3. Automatically injected on Codespace restart

### Local .env File

Can use `.env` file for development:

```bash
# .env file is included in .gitignore
cp .env.example .env
# Enter API keys
```

## 📊 Performance Optimization

### Using Prebuild

**Reduce build time** with `.github/workflows/codespaces-prebuild.yml` configuration:

- Initial start: ~3-5 minutes
- With prebuild: ~30 seconds-1 minute

### Choosing Resource Type

When creating Codespace:
- **2-core** (default): General development
- **4-core**: Heavy build/testing
- **8-core**: Large-scale dev/performance testing

## 🎯 Common Tasks

### Testing API Endpoints

Using VS Code REST Client extension:

```http
### Health Check
GET http://localhost:8000/api/health

### Agent Execute
POST http://localhost:8000/api/v1/agents/execute
Content-Type: application/json

{
  "message": "What is 2+2?",
  "temperature": 0.7
}
```

### Database Queries

Using SQLTools extension:

1. Click **Database** icon in sidebar
2. Connect to **PostgreSQL** (auto-configured)
3. Execute queries

Or in terminal:
```bash
psql -h postgres -U postgres -d bsai -c "SELECT COUNT(*) FROM prompts;"
```

## 🚨 Troubleshooting

### Services Not Starting

```bash
# Restart all services
docker compose down
docker compose up -d

# Restart specific service
docker compose restart postgres
docker compose restart redis
```

### Database Initialization

```bash
# Reset database
docker compose down -v  # Delete volumes
docker compose up -d
```

### Dependency Issues

```bash
# Reinstall Python packages
pip install --force-reinstall -e ".[dev,docs]"

# Purge cache and reinstall
pip cache purge
pip install -e ".[dev,docs]"
```

### Port Conflicts

```bash
# Check ports in use
lsof -i :8000
lsof -i :5432
lsof -i :6379

# Kill process
kill -9 <PID>
```

## 💡 Tips & Tricks

### 1. Command Aliases

Aliases already configured in `.bashrc`:

```bash
ll          # ls -la
pytest      # python -m pytest
```

Add custom aliases:
```bash
echo 'alias serve="uvicorn src.agent_platform.main:app --reload"' >> ~/.bashrc
source ~/.bashrc
```

### 2. Quick Restart

Code changes reflected without server restart (with uvicorn --reload):
- Just save Python files for auto-reload

### 3. Multi-Terminal

Use multiple terminals simultaneously in VS Code:
1. Server execution
2. Test execution
3. Database operations

### 4. Recommended Extensions

Auto-installed extensions:
- Python
- Pylance
- Black Formatter
- Ruff
- SQLTools
- Docker
- REST Client
- GitLens

## 📚 Additional Resources

- [Dev Containers Documentation](https://code.visualstudio.com/docs/devcontainers/containers)
- [GitHub Codespaces Documentation](https://docs.github.com/en/codespaces)
- [BSAI Architecture Documentation](../architecture/overview.md)
- [BSAI Installation Guide](../guides/installation.md)

## 🤝 Contributing

Creating PR after development in Codespaces:

```bash
# Create branch
git checkout -b feature/my-feature

# Work and commit
git add .
git commit -m "feat: add my feature"

# Push
git push origin feature/my-feature
```

Then create Pull Request on GitHub!

---

**Happy developing in Codespaces!** 🎉
