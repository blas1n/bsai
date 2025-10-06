# Docker Usage Guide

The BSAI project has **2 separate Dockerfiles for different purposes**.

## 📁 Dockerfile Structure

```
bsai/
├── Dockerfile                      # Production (root)
└── .devcontainer/
    └── Dockerfile                  # Development (devcontainer)
```

---

## 🏭 `/Dockerfile` - Production

### Purpose
- Production deployment
- CI/CD pipelines
- Cloud Run, ECS, Kubernetes, etc.

### Features
✅ **Optimized**
- Multi-stage build for minimal image size
- Production dependencies only (dev tools excluded)
- Separate build and runtime layers

✅ **Secure**
- Non-root user execution
- Minimal packages installed
- Minimized vulnerabilities

✅ **Performance**
- Small image size (~200MB)
- Fast deployment
- Built-in health check

### Usage

#### 1. Build
```bash
docker build -t bsai:latest .
```

#### 2. Run
```bash
docker run -d \
  -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://... \
  -e REDIS_URL=redis://... \
  -e OPENAI_API_KEY=sk-... \
  --name bsai-app \
  bsai:latest
```

#### 3. Health Check
```bash
curl http://localhost:8000/api/health
```

#### 4. Docker Compose (Production)
```bash
docker compose up -d
```

### Image Structure
```
Stage 1 (Builder)
└─ build-essential, libpq-dev
   └─ pip install (dependencies)

Stage 2 (Runtime) ← Final image
└─ libpq5 (runtime only)
   └─ Copy from builder
      └─ App code
```

---

## 💻 `.devcontainer/Dockerfile` - Development

### Purpose
- VS Code Dev Containers
- GitHub Codespaces
- Local development environment

### Features
✅ **Complete Development Tools**
- pytest, black, ruff, mypy
- ipython, ipdb, rich
- mkdocs, mkdocs-material
- PostgreSQL/Redis CLI tools

✅ **Convenience**
- Git, GitHub CLI
- vim, nano editors
- Claude Code support
- Shell customization

✅ **Integrated Environment**
- PostgreSQL + Redis auto-connection
- Source code bind mount (live reload)
- VS Code extensions auto-installed

### Usage

#### 1. VS Code Dev Containers
```bash
# Auto-built
code .
# F1 → "Reopen in Container"
```

#### 2. GitHub Codespaces
```
Code → Codespaces → Create codespace
# Auto-built and launched
```

#### 3. Docker Compose (Development)
```bash
docker compose -f docker-compose.dev.yml up -d
docker compose exec app bash
```

### Image Structure
```
Single Stage (development environment)
└─ python:3.11-slim
   ├─ System tools (git, postgresql-client, redis-tools, vim, etc)
   ├─ Node.js + Claude Code
   ├─ Python dev dependencies (all)
   └─ Dev tools (pytest, black, ipython, mkdocs, etc)
```

---

## 🔄 Comparison Table

| Item | Production (`/Dockerfile`) | Development (`.devcontainer/Dockerfile`) |
|------|---------------------------|------------------------------------------|
| **Purpose** | Deployment, CI/CD | Local dev, Codespaces |
| **Image Size** | ~200MB | ~800MB |
| **Build Type** | Multi-stage | Single-stage |
| **Dev Tools** | ❌ None | ✅ Included |
| **DB Clients** | ❌ None | ✅ Included (psql, redis-cli) |
| **Git** | ❌ None | ✅ Included |
| **Editors** | ❌ None | ✅ Included (vim, nano) |
| **Claude Code** | ❌ None | ✅ Included |
| **Source Code** | COPY (static) | Bind mount (live) |
| **Dependencies** | Production only | All (dev, docs included) |
| **User** | appuser | vscode |
| **Health check** | ✅ Included | ✅ Included |

---

## 🎯 Usage Scenarios

### Scenario 1: Local Development
```bash
# Uses .devcontainer/Dockerfile
code .
# F1 → "Reopen in Container"
```
**Result**: Development environment with all tools

### Scenario 2: GitHub Codespaces
```
# .devcontainer/Dockerfile auto-used
Create codespace → auto-build → start developing
```
**Result**: Instant development in browser

### Scenario 3: CI/CD Testing
```yaml
# .github/workflows/test.yml
- uses: docker/build-push-action@v5
  with:
    file: Dockerfile  # Production Dockerfile
    push: false
```
**Result**: Testing in production-like environment

### Scenario 4: Production Deployment
```bash
# Uses /Dockerfile
docker build -t ghcr.io/myorg/bsai:v1.0.0 .
docker push ghcr.io/myorg/bsai:v1.0.0
```
**Result**: Optimized image deployment

### Scenario 5: Kubernetes Deployment
```yaml
# k8s/deployment.yaml
spec:
  containers:
  - name: bsai
    image: ghcr.io/myorg/bsai:v1.0.0  # Production image
```
**Result**: Fast scaling with lightweight image

---

## 🚀 Best Practices

### During Development
1. ✅ Use `.devcontainer/Dockerfile` (automatic)
2. ✅ Use `docker-compose.dev.yml`
3. ✅ Live reload with bind mount
4. ✅ Utilize dev tools (pytest, ipdb, etc)

### During Deployment
1. ✅ Use `/Dockerfile`
2. ✅ Use `docker compose` (production) or Kubernetes
3. ✅ Inject configuration via environment variables
4. ✅ Monitor health checks

### Common
1. ✅ Utilize `.dockerignore`
2. ✅ Maximize layer caching
3. ✅ Run as non-root user
4. ✅ Use environment variables or Vault for secrets

---

## 📝 FAQ

### Q: Why are there 2 Dockerfiles?
**A**: Because development and production have different requirements.
- **Development**: Need debugging tools, editors, clients
- **Production**: Need minimal size, security, performance optimization

### Q: Which Dockerfile should I modify?
**A**:
- Development environment changes → `.devcontainer/Dockerfile`
- Production dependency changes → Both
- Production optimization → `/Dockerfile`

### Q: Which Dockerfile does `docker build` use?
**A**: By default, the root `/Dockerfile` (production)
```bash
# Production
docker build -t bsai:latest .

# Development (explicit)
docker build -f .devcontainer/Dockerfile -t bsai:dev .
```

### Q: Which one for CI/CD?
**A**: Production Dockerfile (`/Dockerfile`)
```yaml
# GitHub Actions example
- name: Build image
  run: docker build -t bsai:${{ github.sha }} .
```

### Q: How to reduce image size?
**A**: Production Dockerfile is already optimized.
- Multi-stage build used ✅
- Using slim instead of alpine (compatibility) ✅
- Exclude unnecessary files (.dockerignore) ✅

---

## 🛠️ Debugging Tips

### Development Image Issues
```bash
# Check logs
docker compose -f docker-compose.dev.yml logs app

# Access container
docker compose exec app bash

# Rebuild
docker compose build --no-cache app
```

### Production Image Issues
```bash
# Test production image locally
docker build -t bsai:test .
docker run -it --rm bsai:test bash

# Check image layers
docker history bsai:test
```

---

## 📚 Related Documentation

- [GitHub Codespaces Guide](docs/deployment/codespaces.md)
- [Installation Guide](docs/guides/installation.md)
- [Containerization Strategy](CONTAINERIZATION.md)
- [Docker Compose Documentation](https://docs.docker.com/compose/)

---

**Summary**: Use `.devcontainer/` for development, root `Dockerfile` for deployment! 🎯
