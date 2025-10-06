# Agent Platform Core - Claude Guide

## 이 디렉터리의 역할

`src/agent_platform/`는 BSAI 플랫폼의 핵심 소스 코드입니다.

## 디렉터리 구조

```
agent_platform/
├── core/              # 핵심 Agent 로직
├── platform/          # 플랫폼 기능 (Prompts, Tracing, Cost, Experiments)
├── interfaces/        # 외부 인터페이스 (API, MCP)
├── infrastructure/    # 인프라 계층 (DB, Cache)
└── domain/           # 도메인 모델 및 비즈니스 로직
```

## 개발 가이드

### 새로운 모듈 추가 시

1. **하위 디렉터리 생성**
   ```bash
   mkdir -p src/agent_platform/new_module
   touch src/agent_platform/new_module/__init__.py
   ```

2. **테스트 디렉터리 생성**
   ```bash
   mkdir -p tests/unit/new_module
   touch tests/unit/new_module/__init__.py
   ```

3. **테스트 먼저 작성**
   ```python
   # tests/unit/new_module/test_feature.py
   def test_new_feature():
       assert new_function() == expected_result
   ```

4. **구현**
   ```python
   # src/agent_platform/new_module/feature.py
   def new_function():
       return expected_result
   ```

### Import 규칙

```python
# ✅ Absolute imports 사용
from agent_platform.core.llm.base import LLMProvider
from agent_platform.platform.prompt_store.store import PromptStore

# ❌ Relative imports 지양
from ..core.llm.base import LLMProvider
```

### 의존성 방향

```
interfaces → core → platform → infrastructure
     ↓        ↓        ↓
  domain ← domain ← domain
```

- 상위 레이어는 하위 레이어에 의존 가능
- 하위 레이어는 상위 레이어에 의존 금지
- 모든 레이어는 domain에 의존 가능

## 주요 모듈 설명

### core/
Agent의 핵심 로직:
- `llm/`: 멀티 벤더 LLM 추상화
- `orchestrator/`: Task planning & execution
- `memory/`: Context management
- `tools/`: Tool registry

### platform/
플랫폼 운영 기능:
- `prompt_store/`: 프롬프트 버전 관리
- `trace/`: OpenTelemetry 기반 분산 추적
- `cost/`: LLM 비용 추적
- `experiments/`: A/B 테스트 프레임워크
- `security/`: PII 필터링, 권한 관리

### interfaces/
외부 인터페이스:
- `api/`: FastAPI REST/WebSocket
- `mcp/`: Model Context Protocol 서버

### infrastructure/
인프라 계층:
- `database/`: PostgreSQL 연결
- `cache/`: Redis 연결
- `messaging/`: 이벤트 버스 (향후)

### domain/
도메인 모델:
- `models/`: Pydantic/SQLAlchemy 모델
- `repositories/`: Data access layer
- `services/`: Business logic

## 설정 관리

모든 설정은 `core/config.py`의 `Settings` 클래스에서 관리:

```python
from agent_platform.core.config import settings

# 환경변수에서 자동 로드
database_url = settings.DATABASE_URL
openai_key = settings.OPENAI_API_KEY
```

## 로깅

구조화된 로깅 사용:

```python
import structlog
logger = structlog.get_logger()

logger.info("operation_completed", user_id=user_id, duration_ms=123)
```

## 에러 처리

```python
from fastapi import HTTPException, status

# HTTP 에러
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Resource not found"
)

# 비즈니스 로직 에러
class PromptNotFoundError(ValueError):
    pass
```

## 다음 구현 우선순위

1. LLM Provider 구현 (OpenAI, Anthropic)
2. Orchestrator 완성
3. Prompt Store 데이터베이스 연동
4. Cost Tracker 구현
