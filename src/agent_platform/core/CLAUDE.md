# Core Layer - Claude Guide

## 역할

Agent의 핵심 비즈니스 로직을 담당합니다.

## 하위 모듈

### llm/ - LLM 추상화 계층
**목적**: 여러 LLM 벤더를 단일 인터페이스로 통합

**구현 우선순위**:
1. `base.py` - LLMProvider 인터페이스 정의 ✅
2. `providers/openai_provider.py` - OpenAI 구현
3. `providers/anthropic_provider.py` - Anthropic 구현
4. `providers/google_provider.py` - Google AI 구현
5. `registry.py` - Provider 등록 및 관리 ✅ (스텁)
6. `middleware.py` - Cost tracking, PII filtering 등

**테스트**:
- `tests/unit/core/test_llm_base.py` ✅
- `tests/unit/core/llm/test_openai_provider.py`
- `tests/unit/core/llm/test_registry.py`

### orchestrator/ - Agent 오케스트레이터
**목적**: Task planning, execution, memory 조정

**구현 파일**:
- `planner.py` - 복잡한 요청을 서브태스크로 분해
- `executor.py` - 계획된 태스크 실행
- `orchestrator.py` - 전체 조정 ✅ (스텁)

**데이터 흐름**:
```
User Request → Orchestrator
    ↓
Planner (LLM) → Execution Plan
    ↓
Executor → LLM calls + Tool calls
    ↓
Memory → Store context
    ↓
Response
```

### memory/ - 메모리 관리
**목적**: 대화 컨텍스트 및 지식 저장/검색

**구현 파일**:
- `short_term.py` - Redis 기반 세션 메모리 ✅ (스텁)
- `long_term.py` - 벡터 DB 기반 장기 메모리 (향후)

**Redis 키 구조**:
```
session:{session_id}:messages → List of messages
session:{session_id}:metadata → Session metadata
```

### tools/ - 도구 레지스트리
**목적**: Agent가 사용할 수 있는 도구 등록 및 관리

**구현 파일**:
- `base.py` - Tool 인터페이스
- `registry.py` - Tool 등록 및 검색
- `builtin/` - 기본 제공 도구 (계산기, 웹 검색 등)

**도구 예시**:
```python
class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web for information"

    async def execute(self, query: str) -> str:
        # 구현
        pass
```

## 개발 시 주의사항

### 1. 모든 I/O는 Async
```python
# ✅
async def get_completion(request):
    response = await provider.chat_completion(request)
    return response

# ❌
def get_completion(request):
    response = provider.chat_completion(request)  # Blocking!
    return response
```

### 2. 타입 힌트 필수
```python
from typing import Optional, List
from agent_platform.core.llm.base import ChatRequest, ChatResponse

async def process(request: ChatRequest) -> ChatResponse:
    pass
```

### 3. 에러 처리
```python
try:
    response = await llm.chat_completion(request)
except LLMProviderError as e:
    logger.error("llm_call_failed", error=str(e), provider=provider_name)
    raise
```

### 4. Tracing
```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("llm_call") as span:
    span.set_attribute("provider", provider_name)
    span.set_attribute("model", model_name)
    response = await provider.chat_completion(request)
```

## 다음 단계

1. **OpenAI Provider 구현**
   - API 호출
   - 토큰 카운팅
   - 스트리밍 지원

2. **Orchestrator 완성**
   - Planner 로직
   - Executor 로직
   - Memory 통합

3. **Tool Registry 구현**
   - 기본 도구 추가
   - 동적 등록 지원
