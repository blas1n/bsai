# 100% Containerization Strategy

## Core Principles

BSAI ensures the following through **complete containerization**:

1. ✅ **Zero External Dependencies**: No need to install Python, PostgreSQL, Redis locally
2. ✅ **Instant Execution**: Start developing within 3-5 minutes on GitHub Codespaces
3. ✅ **Environment Consistency**: All developers work in identical environments
4. ✅ **Production Parity**: Development/staging/production environments completely identical

## Validation Criteria

**"Does it run well on GitHub Codespaces?"**

- [x] Full stack execution just by creating Codespace
- [x] Automatic dependency installation
- [x] Automatic database initialization
- [x] Automatic test execution
- [x] Automatic port forwarding

## Architecture

### Container Composition

```
┌─────────────────────────────────────────┐
│         Dev Container (app)              │
│  - Python 3.11                          │
│  - All dependencies                     │
│  - Source code (bind mount)             │
│  - Development tools                    │
└─────────────────────────────────────────┘
           ↓          ↓          ↓
┌──────────────┐ ┌──────────┐ ┌─────────┐
│  PostgreSQL  │ │  Redis   │ │ Optional│
│    (15)      │ │   (7)    │ │ Monitor │
└──────────────┘ └──────────┘ └─────────┘
```

### Development Environment Composition

#### 1. GitHub Codespaces
- `.devcontainer/devcontainer.json` - Dev container configuration
- `.devcontainer/Dockerfile` - Custom image
- `.devcontainer/scripts/` - Lifecycle scripts
- `docker-compose.dev.yml` - Full stack

#### 2. VS Code Dev Containers
- Uses same `.devcontainer/`
- Leverages local Docker Desktop
- Full IDE integration

#### 3. Docker Compose (Standalone)
- `docker-compose.dev.yml` - Development
- `docker-compose.yml` - Production

## Configuration File Structure

### `.devcontainer/devcontainer.json`
```json
{
  "name": "BSAI",
  "dockerComposeFile": "../docker-compose.dev.yml",
  "service": "app",
  "workspaceFolder": "/workspace",
  "onCreateCommand": "bash .devcontainer/scripts/on-create.sh",
  "postStartCommand": "bash .devcontainer/scripts/post-start.sh",
  "forwardPorts": [8000, 5432, 6379],
  ...
}
```

**Key Features**:
- Docker Compose integration
- Lifecycle hooks
- Automatic port forwarding
- VS Code extension auto-installation

### `docker-compose.dev.yml`
```yaml
services:
  app:
    build: .devcontainer/Dockerfile
    volumes:
      - .:/workspace:cached  # Live source code reflection
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }

  postgres:
    image: postgres:15-alpine
    healthcheck: ...

  redis:
    image: redis:7-alpine
    healthcheck: ...
```

**Key Features**:
- Health checks ensure service readiness
- Live development with volume mounts
- Environment variable injection

### `.devcontainer/Dockerfile`
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client redis-tools git curl ...

# Pre-install Python dependencies
COPY pyproject.toml ./
RUN pip install fastapi uvicorn sqlalchemy ...

# Development tools
RUN pip install ipython ipdb rich

# Non-root user
USER vscode
```

**Key Features**:
- All dependencies included in image
- Development tools pre-installed
- Non-root user for security

## Lifecycle Scripts

### `on-create.sh` (Runs once on container creation)
```bash
# Wait for PostgreSQL
until pg_isready -h postgres; do sleep 1; done

# Wait for Redis
until redis-cli -h redis ping; do sleep 1; done

# Install Python packages
pip install -e .

# Run database migrations
alembic upgrade head

# Run initial tests
pytest tests/unit/core/test_llm_base.py
```

### `post-start.sh` (Runs on every container start)
```bash
# Health checks
pg_isready -h postgres
redis-cli -h redis ping

# Firewall init (for Claude Code)
sudo /usr/local/bin/init-firewall.sh
```

## Port Forwarding

Automatically forwarded ports:

| Port | Service | Purpose |
|------|---------|---------|
| 8000 | FastAPI | API server |
| 5432 | PostgreSQL | Database |
| 6379 | Redis | Cache |
| 9090 | Prometheus | Metrics (optional) |
| 3001 | Grafana | Dashboard (optional) |

## Volume Strategy

### 1. Source Code
```yaml
volumes:
  - .:/workspace:cached
```
- Live reflection with bind mount
- Performance optimization with `cached` option

### 2. Database
```yaml
volumes:
  - postgres-data:/var/lib/postgresql/data
```
- Data persistence with named volume

### 3. Python Packages
```yaml
volumes:
  - venv:/workspace/.venv
```
- Preserve dependencies on rebuild

## Environment Variable Injection

### 1. GitHub Secrets (Codespaces)
```
Settings → Secrets → Codespaces → New secret
```

### 2. `.env` File (Local)
```bash
cp .env.example .env
# Enter API keys
```

### 3. Docker Compose
```yaml
environment:
  - DATABASE_URL=postgresql+asyncpg://postgres@postgres:5432/bsai
  - REDIS_URL=redis://redis:6379/0
```

## Performance Optimization

### 1. Image Layer Caching
```dockerfile
# Copy dependencies first (low change frequency)
COPY pyproject.toml ./
RUN pip install ...

# Copy source code later (high change frequency)
COPY src/ ./src/
```

### 2. Multi-stage Build (Production)
```dockerfile
# Builder stage
FROM python:3.11-slim as builder
RUN pip install ...

# Runtime stage
FROM python:3.11-slim
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
```

### 3. Codespaces Prebuild
```yaml
# .github/workflows/codespaces-prebuild.yml
on:
  push:
    branches: [main]

jobs:
  prebuild:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: github/codespaces-prebuild@v1
```

Initial build: ~5 minutes → With prebuild: ~30 seconds

## Monitoring and Debugging

### Container Logs
```bash
# All logs
docker compose logs -f

# Specific service
docker compose logs -f app
docker compose logs -f postgres
```

### Container Access
```bash
# App container
docker compose exec app bash

# PostgreSQL
docker compose exec postgres psql -U postgres -d bsai

# Redis
docker compose exec redis redis-cli
```

### Health Checks
```bash
# PostgreSQL
pg_isready -h postgres -U postgres -d bsai

# Redis
redis-cli -h redis ping

# FastAPI
curl http://localhost:8000/api/health/detailed
```

## Troubleshooting

### 1. Services Not Starting
```bash
# Full restart
docker compose down && docker compose up -d

# Check logs
docker compose logs postgres
```

### 2. Database Initialization
```bash
# Delete including volumes (data loss!)
docker compose down -v
docker compose up -d
```

### 3. Dependency Issues
```bash
# Rebuild image
docker compose build --no-cache app
docker compose up -d
```

### 4. Port Conflicts
```bash
# Use different port
docker compose -f docker-compose.dev.yml \
  run -p 8080:8000 app \
  uvicorn src.agent_platform.main:app --reload
```

## Security Considerations

### 1. Non-root User
```dockerfile
USER vscode
```

### 2. Secrets Management
- Use GitHub Secrets
- `.env` file included in `.gitignore`
- Use Vault/AWS Secrets Manager in production

### 3. Network Isolation
```yaml
networks:
  bsai-network:
    driver: bridge
```

### 4. Health Checks
```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready"]
  interval: 5s
  timeout: 5s
  retries: 5
```

## Production Deployment

### Kubernetes Conversion
```bash
# Convert Docker Compose → Kubernetes with Kompose
kompose convert -f docker-compose.yml
```

### Docker Swarm
```bash
docker stack deploy -c docker-compose.yml bsai
```

### Cloud Run / ECS
- Use `Dockerfile` as-is
- Inject environment variables
- Connect to managed PostgreSQL/Redis

## Conclusion

✅ **100% Containerization Complete**

- Instant execution on GitHub Codespaces
- Automatic dependency resolution
- Development/production environment match
- New developer onboarding time: **Under 5 minutes**

**Verification Complete**: "It runs well on GitHub Codespaces!" ✨
