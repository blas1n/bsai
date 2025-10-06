#!/bin/bash
# on-create.sh - Runs once when container is created

set -e

echo "🚀 BSAI Dev Container - onCreate"
echo "=================================="

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL..."
until pg_isready -h postgres -U postgres -d bsai > /dev/null 2>&1; do
  sleep 1
done
echo "✅ PostgreSQL is ready"

# Wait for Redis to be ready
echo "⏳ Waiting for Redis..."
until redis-cli -h redis ping > /dev/null 2>&1; do
  sleep 1
done
echo "✅ Redis is ready"

# Install project in editable mode using uv
echo "📦 Installing project in editable mode with uv..."
cd /workspace

# Create virtual environment in user home if doesn't exist
if [ ! -d "$HOME/.venv" ]; then
  echo "🔧 Creating virtual environment..."
  ~/.local/bin/uv venv ~/.venv
fi

# Activate virtual environment
source ~/.venv/bin/activate

# Install project with all extras
echo "📥 Installing dependencies..."
~/.local/bin/uv pip install -e ".[dev,docs]" || true

# Run database migrations (if they exist)
if [ -d "/workspace/migrations" ]; then
  echo "🗄️  Running database migrations..."
  alembic upgrade head || echo "⚠️  No migrations to run or alembic not configured yet"
else
  echo "ℹ️  No migrations directory found, skipping"
fi

# Create .env file if it doesn't exist
if [ ! -f "/workspace/.env" ]; then
  echo "📝 Creating .env file from template..."
  cp /workspace/.env.example /workspace/.env || echo "⚠️  .env.example not found"
fi

# Run initial tests to verify setup
echo "🧪 Running initial tests..."
pytest tests/unit/core/test_llm_base.py -v || echo "⚠️  Tests not ready yet"

echo ""
echo "✨ Dev container is ready!"
echo "=================================="
echo "Quick start commands:"
echo "  • Start server:  uvicorn src.agent_platform.main:app --reload"
echo "  • Run tests:     pytest"
echo "  • View docs:     mkdocs serve"
echo "  • DB shell:      psql -h postgres -U postgres -d bsai"
echo "  • Redis CLI:     redis-cli -h redis"
echo "=================================="
