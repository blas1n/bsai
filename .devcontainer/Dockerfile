# ============================================
# DEVELOPMENT DOCKERFILE
# ============================================
# 용도: VS Code Dev Containers / GitHub Codespaces
# 사용: .devcontainer/devcontainer.json에서 자동 빌드
#
# 특징:
# - 모든 개발 도구 포함 (pytest, black, ruff, mypy, ipython 등)
# - PostgreSQL/Redis 클라이언트 도구
# - Claude Code 지원
# - Non-root user (vscode)
# - 소스 코드는 bind mount로 실시간 반영
# ============================================

ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim

USER root
WORKDIR /workspace
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build tools
    build-essential \
    gcc \
    g++ \
    make \
    # PostgreSQL client and dev libs
    libpq-dev \
    postgresql-client \
    # Redis client
    redis-tools \
    # Git
    git \
    # Networking tools
    curl \
    wget \
    netcat-openbsd \
    iputils-ping \
    dnsutils \
    # Firewall (for Claude Code)
    iptables \
    ipset \
    iproute2 \
    # Text editors
    vim \
    # Process management
    procps \
    sudo \
    zsh \
    # Node.js (for Claude Code)
    nodejs \
    npm \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID
ARG CLAUDE_CODE_VERSION=latest

RUN groupadd -g $USER_GID $USERNAME \
    && useradd -m -u $USER_UID -g $USER_GID -d /home/$USERNAME -s /bin/bash $USERNAME

# Set up npm global directory
RUN mkdir -p /usr/local/share/npm-global && \
    chown -R $USER_UID:$USER_GID /usr/local/share
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH=$PATH:/usr/local/share/npm-global/bin

# Persist bash history
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
    && mkdir /commandhistory \
    && touch /commandhistory/.bash_history \
    && chown -R $USER_UID:$USER_GID /commandhistory \
    && echo $SNIPPET >> /home/$USERNAME/.bashrc

# Create workspace and config directories
RUN mkdir -p /workspace /home/$USERNAME/.claude && \
    chown -R $USER_UID:$USER_GID /workspace /home/$USERNAME/.claude

# Set environment
ENV DEVCONTAINER=true \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/$USERNAME/.local/bin:$PATH"

# Switch to non-root user for package installation
USER $USERNAME

# Install Claude Code
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# Copy project files (only metadata for dependency installation)
COPY --chown=$USERNAME:$USERNAME pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    # Web framework
    fastapi>=0.109.0 \
    uvicorn[standard]>=0.27.0 \
    # Data validation
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0 \
    # Database
    sqlalchemy>=2.0.25 \
    alembic>=1.13.1 \
    asyncpg>=0.29.0 \
    databases>=0.8.0 \
    # Cache
    redis>=5.0.1 \
    # LLM SDKs
    openai>=1.10.0 \
    anthropic>=0.18.0 \
    google-generativeai>=0.3.2 \
    litellm>=1.27.0 \
    # Observability
    opentelemetry-api>=1.22.0 \
    opentelemetry-sdk>=1.22.0 \
    opentelemetry-instrumentation-fastapi>=0.43b0 \
    prometheus-client>=0.19.0 \
    structlog>=24.1.0 \
    # Security
    python-jose[cryptography]>=3.3.0 \
    passlib[bcrypt]>=1.7.4 \
    # Utilities
    python-multipart>=0.0.6 \
    websockets>=12.0 \
    tenacity>=8.2.3 \
    httpx>=0.26.0 \
    # Development tools
    pytest>=7.4.0 \
    pytest-asyncio>=0.23.0 \
    pytest-cov>=4.1.0 \
    pytest-mock>=3.12.0 \
    faker>=22.0.0 \
    black>=24.1.0 \
    ruff>=0.1.14 \
    mypy>=1.8.0 \
    # Interactive dev tools
    ipython \
    ipdb \
    rich \
    # Documentation
    mkdocs>=1.5.3 \
    mkdocs-material>=9.5.3 \
    mkdocstrings[python]>=0.24.0 \
    mkdocs-mermaid2-plugin>=1.1.1

#RUN /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
#ENV PATH="/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:${PATH}"

# Copy and set up firewall script (for Claude Code)
USER root
COPY ./.devcontainer/scripts/init-firewall.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/init-firewall.sh && \
    echo "$USERNAME ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh" > /etc/sudoers.d/firewall && \
    chmod 0440 /etc/sudoers.d/firewall

# Switch back to non-root user
USER $USERNAME

# Install homebrew (for dotfiles)
RUN mkdir -p $HOME/.linuxbrew \
    && git clone https://github.com/Homebrew/brew $HOME/.linuxbrew/Homebrew \
    && mkdir -p $HOME/.linuxbrew/bin \
    && ln -s $HOME/.linuxbrew/Homebrew/bin/brew $HOME/.linuxbrew/bin/brew \
    && eval "$($HOME/.linuxbrew/bin/brew shellenv)"
#    && echo 'eval "$($HOME/.linuxbrew/bin/brew shellenv)"' >> $HOME/.bashrc \
#    && brew update --force --quiet
ENV PATH=/home/$USERNAME/.linuxbrew/bin:/home/$USERNAME/.linuxbrew/sbin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

CMD ["zsh"]
