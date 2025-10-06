# BSAI - Claude Development Guide

이 문서는 Claude AI가 BSAI 프로젝트를 개발할 때 참고해야 하는 핵심 가이드입니다.

## 프로젝트 개요

BSAI는 **플랫폼 지향 AI Agent 오케스트레이터**로, 다음 세 가지 인터페이스를 지원합니다:

1. **REST/WebSocket API**: 웹 프론트엔드용
2. **MCP (Model Context Protocol)**: Claude 등 LLM이 직접 접근
3. **Multi-vendor LLM**: 내부적으로 여러 LLM (GPT, Claude, Gemini) 추상화

## 핵심 개발 원칙

### 1. TDD (Test-Driven Development)
**모든 기능은 테스트 코드부터 작성합니다.**

```python
# 1. 테스트 작성 (tests/unit/...)
def test_prompt_creation():
    prompt = PromptStore().create_prompt(name="test", content="...")
    assert prompt.version == 1

# 2. 최소 구현
class PromptStore:
    def create_prompt(self, name, content):
        return Prompt(version=1)

# 3. 리팩토링
```

### 2. DDD (Documentation-Driven Development)
**기능 구현 전에 설계 문서를 먼저 작성합니다.**

- Architecture 설계: `docs/architecture/`
- API 스펙: `docs/api/`
- 가이드: `docs/guides/`

### 3. 의존성 관리
**모든 의존성은 `pyproject.toml`에서 관리됩니다.**

```bash
# ❌ 직접 pip install 금지
pip install some-package

# ✅ uv를 통한 의존성 추가 (향후)
# 현재는 pyproject.toml을 직접 수정
```

## 디렉터리 구조

```
bsai/
├── src/agent_platform/          # 메인 소스 코드
│   ├── core/                    # 핵심 Agent 로직
│   │   ├── llm/                # LLM 추상화 계층
│   │   ├── orchestrator/       # 오케스트레이터
│   │   ├── memory/             # 메모리 관리
│   │   └── tools/              # 도구 레지스트리
│   ├── platform/               # 플랫폼 기능
│   │   ├── prompt_store/       # 프롬프트 버전 관리
│   │   ├── trace/              # 분산 추적
│   │   ├── cost/               # 비용 추적
│   │   ├── experiments/        # 실험 관리
│   │   └── security/           # 보안 (PII 필터링 등)
│   ├── interfaces/             # 외부 인터페이스
│   │   ├── api/               # FastAPI 라우터
│   │   └── mcp/               # MCP 서버
│   ├── infrastructure/         # 인프라 계층
│   │   ├── database/          # PostgreSQL
│   │   ├── cache/             # Redis
│   │   └── messaging/         # 이벤트 버스 (향후)
│   └── domain/                # 도메인 모델
│       ├── models/            # Pydantic/SQLAlchemy 모델
│       ├── repositories/      # 데이터 접근 계층
│       └── services/          # 비즈니스 로직
├── tests/                     # 테스트
│   ├── unit/                 # 단위 테스트
│   ├── integration/          # 통합 테스트
│   └── e2e/                  # E2E 테스트
├── docs/                     # MkDocs 문서
│   ├── architecture/        # 아키텍처 문서
│   ├── api/                # API 문서
│   └── guides/             # 사용 가이드
└── migrations/             # Alembic 마이그레이션
```

## 코딩 컨벤션

### Type Hints 필수
```python
# ✅ Good
async def get_prompt(name: str, version: Optional[int] = None) -> Optional[Prompt]:
    pass

# ❌ Bad
async def get_prompt(name, version=None):
    pass
```

### Async/Await 우선
```python
# ✅ Good - 모든 I/O는 async
async def fetch_data():
    async with aiohttp.ClientSession() as session:
        response = await session.get(url)
        return await response.json()

# ❌ Bad - 동기 I/O
def fetch_data():
    response = requests.get(url)
    return response.json()
```

### Structured Logging
```python
import structlog
logger = structlog.get_logger()

# ✅ Good - 구조화된 로깅
logger.info("prompt_created", prompt_id=str(prompt.id), version=1, author=user_id)

# ❌ Bad - 문자열 포맷팅
logger.info(f"Prompt {prompt.id} created with version 1 by {user_id}")
```

### Pydantic Models
```python
from pydantic import BaseModel, Field

class PromptCreate(BaseModel):
    name: str = Field(..., description="Unique prompt name")
    content: str = Field(..., min_length=1)
    category: Optional[str] = None
```

## 주요 모듈 개발 가이드

### LLM Provider 추가하기

1. **인터페이스 구현**
```python
# src/agent_platform/core/llm/providers/new_provider.py
from agent_platform.core.llm.base import LLMProvider, ChatRequest, ChatResponse

class NewLLMProvider(LLMProvider):
    async def chat_completion(self, request: ChatRequest) -> ChatResponse:
        # 구현
        pass
```

2. **레지스트리에 등록**
```python
# src/agent_platform/core/llm/registry.py
from .providers.new_provider import NewLLMProvider

await llm_registry.register("new_provider", NewLLMProvider())
```

3. **테스트 작성**
```python
# tests/unit/core/llm/test_new_provider.py
@pytest.mark.asyncio
async def test_new_provider_chat_completion():
    provider = NewLLMProvider()
    response = await provider.chat_completion(request)
    assert response.content is not None
```

### API 엔드포인트 추가하기

1. **라우터 생성**
```python
# src/agent_platform/interfaces/api/routers/new_feature.py
from fastapi import APIRouter, Depends
router = APIRouter()

@router.post("/", response_model=ResponseModel)
async def create_resource(
    data: RequestModel,
    current_user: dict = Depends(get_current_user)
):
    # 구현
    pass
```

2. **메인 앱에 등록**
```python
# src/agent_platform/main.py
from .interfaces.api.routers import new_feature

app.include_router(new_feature.router, prefix="/api/v1/new-feature", tags=["NewFeature"])
```

3. **통합 테스트**
```python
# tests/integration/api/test_new_feature.py
async def test_create_resource(client):
    response = await client.post("/api/v1/new-feature/", json={...})
    assert response.status_code == 201
```

## 데이터베이스 마이그레이션

```bash
# 1. 모델 변경 후 마이그레이션 생성
alembic revision --autogenerate -m "Add new table for experiments"

# 2. 마이그레이션 파일 검토
# migrations/versions/xxx_add_new_table_for_experiments.py

# 3. 적용
alembic upgrade head

# 4. 롤백 (필요시)
alembic downgrade -1
```

## 테스트 실행

```bash
# 전체 테스트
pytest

# 특정 테스트 파일
pytest tests/unit/core/test_llm_base.py

# 커버리지 포함
pytest --cov=src --cov-report=html

# 빠른 실패 (첫 실패 시 중단)
pytest -x

# 특정 마커만 실행
pytest -m "not slow"
```

## 문서 작성 가이드

### 코드 문서화
```python
def complex_function(param: str) -> Result:
    """
    Brief description of what this function does.

    Args:
        param: Description of parameter

    Returns:
        Description of return value

    Raises:
        ValueError: When param is invalid

    Example:
        >>> result = complex_function("test")
        >>> print(result.value)
        "processed_test"
    """
    pass
```

### MkDocs 문서
- 모든 주요 기능은 `docs/` 에 문서화
- API 변경 시 `docs/api/` 업데이트
- 아키텍처 변경 시 `docs/architecture/` 업데이트

## 성능 고려사항

### 1. Database Query 최적화
```python
# ✅ Good - 한 번의 쿼리로 조회
prompts = await db.fetch_all(
    "SELECT * FROM prompts WHERE category = $1 LIMIT $2",
    category, limit
)

# ❌ Bad - N+1 쿼리
for prompt_id in prompt_ids:
    prompt = await db.fetch_one("SELECT * FROM prompts WHERE id = $1", prompt_id)
```

### 2. 캐싱 활용
```python
# 자주 조회되는 프롬프트는 Redis 캐시
cache_key = f"prompt:{name}:v{version}"
cached = await redis_client.get(cache_key)
if cached:
    return json.loads(cached)
```

### 3. 병렬 처리
```python
# ✅ Good - 병렬 LLM 호출
results = await asyncio.gather(
    llm1.chat_completion(request1),
    llm2.chat_completion(request2),
)

# ❌ Bad - 순차 처리
result1 = await llm1.chat_completion(request1)
result2 = await llm2.chat_completion(request2)
```

## Observability

### Tracing
모든 주요 작업은 자동으로 trace됩니다:
```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("operation_name") as span:
    span.set_attribute("user.id", user_id)
    # 작업 수행
```

### Metrics
Prometheus 메트릭 노출:
```python
from prometheus_client import Counter, Histogram

llm_calls = Counter('llm_calls_total', 'Total LLM calls', ['provider', 'model'])
llm_calls.labels(provider='openai', model='gpt-4').inc()
```

### Logging
구조화된 로그 사용:
```python
logger.info("operation_completed", duration_ms=123, user_id=user_id)
```

## 보안 체크리스트

- [ ] API 키는 환경변수로 관리
- [ ] 사용자 입력 검증 (Pydantic)
- [ ] SQL Injection 방지 (파라미터 바인딩)
- [ ] PII 필터링 적용
- [ ] 권한 검증 (Depends)
- [ ] Rate limiting (향후)

## Git Workflow

```bash
# 1. Feature 브랜치 생성
git checkout -b feature/prompt-versioning

# 2. 작업 및 커밋
git add .
git commit -m "feat: Add prompt version rollback functionality"

# 3. 테스트 통과 확인
pytest

# 4. PR 생성
git push origin feature/prompt-versioning
```

## 다음 단계

작업 우선순위:

1. **Phase 1 - MVP**
   - [ ] LLM Provider 구현 (OpenAI, Anthropic)
   - [ ] 기본 Orchestrator 완성
   - [ ] Prompt Store 구현
   - [ ] Cost Tracker 구현

2. **Phase 2 - Platform**
   - [ ] Experiment Framework
   - [ ] Advanced Tracing
   - [ ] PII Filtering
   - [ ] MCP Server 구현

3. **Phase 3 - Production**
   - [ ] Performance 최적화
   - [ ] 모니터링 대시보드
   - [ ] 배포 자동화
   - [ ] 부하 테스트

## 참고 자료

- FastAPI Docs: https://fastapi.tiangolo.com
- Pydantic: https://docs.pydantic.dev
- OpenTelemetry: https://opentelemetry.io/docs/languages/python/
- MkDocs: https://www.mkdocs.org
- pytest: https://docs.pytest.org

## 질문/이슈

프로젝트 관련 질문이나 이슈는 GitHub Issues를 활용하세요.
