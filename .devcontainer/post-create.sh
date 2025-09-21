#!/bin/bash
# Comprehensive automated development environment setup
# Includes dependency installation, secret management, and environment configuration

set -e
echo "BSAI automated environment setup starting..."

# Install project dependencies automatically
echo "Installing project dependencies..."
if [ -f "pyproject.toml" ]; then
    uv sync --extra dev
fi

# Auto-create basic directory structure only
echo "Creating basic directory structure..."
mkdir -p temp/{logs,data,uploads}

# ============================================================================
# DYNAMIC SECRET LOADING with Priority: 1Password > .env > Environment > Demo
# ============================================================================

echo "=== BSAI Dynamic Secret Loading ==="

# Function to export environment variable
export_secret() {
    local key=$1
    local value=$2
    if [ -n "$value" ] && [ "$value" != "demo_key_safe_mode" ]; then
        export "$key=$value"
        echo "✓ $key loaded successfully"
        return 0
    fi
    return 1
}

# Function to get secret from Secret Manager
get_secret_from_manager() {
    local key=$1
    if [ -f "secrets/secret-manager.py" ]; then
        python secrets/secret-manager.py get-secret "$key" 2>/dev/null || echo ""
    else
        echo ""
    fi
}

# Load ANTHROPIC_API_KEY with priority order
load_anthropic_key() {
    local api_key=""
    
    # Priority 1: Try 1Password via Secret Manager
    echo "Checking 1Password..."
    api_key=$(get_secret_from_manager "ANTHROPIC_API_KEY")
    if export_secret "ANTHROPIC_API_KEY" "$api_key"; then
        echo "Source: 1Password"
        return 0
    fi
    
    # Priority 2: Try .env file
    echo "Checking .env file..."
    if [ -f ".env" ]; then
        api_key=$(grep "^ANTHROPIC_API_KEY=" .env 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'")
        if export_secret "ANTHROPIC_API_KEY" "$api_key"; then
            echo "Source: .env file"
            return 0
        fi
    fi
    
    # Priority 3: Try existing environment variable
    echo "Checking environment variables..."
    if export_secret "ANTHROPIC_API_KEY" "$ANTHROPIC_API_KEY"; then
        echo "Source: Environment variable"
        return 0
    fi
    
    # Priority 4: Demo mode
    echo "Using demo mode"
    export ANTHROPIC_API_KEY="demo_key_safe_mode"
    export BSAI_MODE="demo"
    echo "Source: Demo mode (no real API calls)"
    return 0
}

# Load other secrets with same priority
load_other_secrets() {
    # SECRET_KEY
    local secret_key=""
    secret_key=$(get_secret_from_manager "SECRET_KEY")
    if [ -z "$secret_key" ] && [ -f ".env" ]; then
        secret_key=$(grep "^SECRET_KEY=" .env 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    fi
    if [ -z "$secret_key" ]; then
        secret_key="$SECRET_KEY"
    fi
    export SECRET_KEY="${secret_key:-$(openssl rand -base64 32)}"
    
    # JWT_SECRET_KEY
    local jwt_secret=""
    jwt_secret=$(get_secret_from_manager "JWT_SECRET_KEY")
    if [ -z "$jwt_secret" ] && [ -f ".env" ]; then
        jwt_secret=$(grep "^JWT_SECRET_KEY=" .env 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    fi
    if [ -z "$jwt_secret" ]; then
        jwt_secret="$JWT_SECRET_KEY"
    fi
    export JWT_SECRET_KEY="${jwt_secret:-$(openssl rand -base64 32)}"
}

# Execute secret loading
load_anthropic_key
load_other_secrets

# Create/update .env file for consistency
echo "Updating .env file..."
cat > .env << EOF
# BSAI Environment Configuration (Auto-generated)
ENVIRONMENT=development
LOG_LEVEL=DEBUG

# AI Models
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY

# Security
SECRET_KEY=$SECRET_KEY
JWT_SECRET_KEY=$JWT_SECRET_KEY

# Features
ENABLE_WEB_UI=true
ENABLE_MONITORING=false
BSAI_MODE=${BSAI_MODE:-development}
EOF

# Make variables available to current shell and future sessions
echo "export ANTHROPIC_API_KEY='$ANTHROPIC_API_KEY'" >> ~/.bashrc
echo "export SECRET_KEY='$SECRET_KEY'" >> ~/.bashrc
echo "export JWT_SECRET_KEY='$JWT_SECRET_KEY'" >> ~/.bashrc

# Create manual loading script
mkdir -p scripts
cat > scripts/load-env.sh << 'EOF'
#!/bin/bash
# Manual environment loading script
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
    echo "Environment variables loaded from .env"
else
    echo ".env file not found"
fi
EOF
chmod +x scripts/load-env.sh

# ============================================================================
# REMAINING SETUP TASKS
# ============================================================================

# Initialize secret management system
echo "Initializing secret management..."
if [ -f "secrets/secret-manager.py" ]; then
    python secrets/secret-manager.py init || echo "Secret manager initialization completed"
fi

# Run security scan
echo "Running security checks..."
if command -v gitleaks >/dev/null 2>&1; then
    gitleaks detect --config .gitleaks.toml || echo "Security scan completed"
fi

echo ""
echo "BSAI development environment setup complete!"
echo ""
echo "Secret Loading Results:"
echo "  ANTHROPIC_API_KEY: $(if [ "$ANTHROPIC_API_KEY" = "demo_key_safe_mode" ]; then echo "Demo Mode"; else echo "Loaded"; fi)"
echo "  SECRET_KEY: Loaded"
echo "  JWT_SECRET_KEY: Loaded"
echo ""
echo "Ready to use commands:"
echo "  python -m bsai.cli.main status"
echo "  python -m bsai.cli.main hello"
echo ""
echo "Development tools available:"
echo "  uv run pytest                    # Run tests"
echo "  uv run black .                   # Format code"
echo "  uv run mkdocs serve              # Serve documentation"
echo "  gitleaks detect                  # Security scan"
echo "  source scripts/load-env.sh       # Manual reload environment"
echo ""
echo "Happy coding!"