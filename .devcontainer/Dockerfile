FROM mcr.microsoft.com/devcontainers/python:3.11-bookworm

USER vscode
WORKDIR /workspace

# Install system tools and CLI utilities
USER root
RUN apt-get update && apt-get install -y \
    curl wget git vim tree jq \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Kind (Kubernetes in Docker)
RUN curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64 \
    && chmod +x ./kind \
    && mv ./kind /usr/local/bin/kind

# Install 1Password Connect SDK dependencies
RUN pip install onepassword-sdk

# Install GitLeaks
RUN curl -sSfL https://github.com/gitleaks/gitleaks/releases/download/v8.18.0/gitleaks_8.18.0_linux_x64.tar.gz | tar -xz \
    && mv gitleaks /usr/local/bin/ \
    && chmod +x /usr/local/bin/gitleaks

USER vscode

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/vscode/.cargo/bin:$PATH"

# Pre-install common Python development tools
RUN pip install --upgrade pip \
    && pip install \
    black isort ruff mypy \
    pytest pytest-asyncio pytest-cov \
    anthropic langchain langchain-anthropic \
    fastapi uvicorn typer rich \
    pydantic pydantic-settings \
    python-dotenv httpx aiofiles \
    mkdocs mkdocs-material mkdocstrings \
    bandit safety pre-commit

# Setup development environment
RUN git config --global init.defaultBranch main \
    && echo 'export PS1="bsai-dev:\w\$ "' >> ~/.bashrc \
    && echo 'alias ll="ls -alF"' >> ~/.bashrc \
    && echo 'alias bsai="python -m bsai.cli.main"' >> ~/.bashrc

# Create necessary directories with proper permissions
USER root
RUN mkdir -p /workspace/temp/{logs,data,uploads} \
    && chown -R vscode:vscode /workspace

# Install Node.js & npm (needed for Claude CLI)
USER root
RUN apt-get update && apt-get install -y nodejs npm \
    && npm install -g @anthropic-ai/claude-code

USER vscode
WORKDIR /home/vscode

RUN /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
ENV PATH="/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:${PATH}"
CMD ["zsh"]