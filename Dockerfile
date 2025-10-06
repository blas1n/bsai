# ============================================
# PRODUCTION DOCKERFILE
# ============================================
# 용도: 프로덕션 배포용 최적화된 이미지
# 사용: docker build -t bsai:latest .
#      docker run -p 8000:8000 bsai:latest
#
# 특징:
# - Multi-stage build로 이미지 크기 최소화
# - 개발 도구 제외 (최소한의 의존성만)
# - Non-root user 실행
# - Health check 포함
# ============================================

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./

# Install production dependencies only
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini ./

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

# Run application
CMD ["uvicorn", "src.agent_platform.main:app", "--host", "0.0.0.0", "--port", "8000"]
