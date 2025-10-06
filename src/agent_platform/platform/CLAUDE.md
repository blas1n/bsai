# Platform Layer - Claude Guide

## 역할

LLMOps 및 플랫폼 운영에 필요한 기능을 제공합니다.

## 하위 모듈

### prompt_store/ - 프롬프트 중앙 관리
**목적**: 프롬프트를 코드가 아닌 관리 가능한 리소스로 취급

**핵심 기능**:
- Git 방식 버전 관리
- 변경 이력 추적
- 롤백 지원
- 템플릿 렌더링

**구현 파일**:
- `store.py` - CRUD 및 버전 관리 ✅ (스텁)
- `versioning.py` - 버전 비교, diff
- `template.py` - Jinja2 템플릿 렌더링

**데이터베이스 테이블**:
```sql
prompts               -- 프롬프트 메타데이터
prompt_versions       -- 버전 이력
prompt_deployments    -- 환경별 배포 상태
```

**사용 예시**:
```python
# 프롬프트 생성
prompt = await prompt_store.create_prompt(
    name="customer_greeting",
    content="Hello {{customer_name}}, how can I help?",
    template_variables={"customer_name": "string"}
)

# 버전 업데이트
await prompt_store.update_prompt(
    name="customer_greeting",
    content="Hi {{customer_name}}, what can I do for you today?",
    commit_message="Make greeting more casual"
)

# 롤백
await prompt_store.rollback(name="customer_greeting", version=1)
```

### trace/ - 분산 추적
**목적**: 모든 요청의 전체 생명주기 추적

**핵심 기능**:
- OpenTelemetry 기반 tracing
- Span 생성 및 전파
- Trace 데이터 저장

**구현 파일**:
- `tracer.py` - Trace 관리
- `logger.py` - 구조화 로깅

**Span 구조**:
```
agent.execute (root span)
  ├─ planner.plan
  │   └─ llm.chat_completion
  ├─ executor.execute
  │   ├─ tool.web_search
  │   └─ llm.chat_completion
  └─ memory.store
```

### cost/ - 비용 추적
**목적**: LLM 사용 비용 실시간 추적 및 예산 관리

**핵심 기능**:
- 토큰 단위 비용 계산
- 실시간 집계
- 예산 알림
- 비용 리포트

**구현 파일**:
- `tracker.py` - 사용량 기록
- `pricing.py` - 모델별 가격 정보
- `aggregator.py` - 비용 집계

**가격 테이블**:
```python
PRICING = {
    "openai": {
        "gpt-4": {"input": 0.03/1000, "output": 0.06/1000}
    },
    "anthropic": {
        "claude-3-opus": {"input": 0.015/1000, "output": 0.075/1000}
    }
}
```

### experiments/ - 실험 플랫폼
**목적**: 프롬프트 A/B 테스트 및 품질 평가

**핵심 기능**:
- 실험 설정 및 실행
- 변형(variant) 비교
- 자동 평가
- 결과 분석

**구현 파일**:
- `runner.py` - 실험 실행
- `evaluator.py` - 품질 평가

**실험 흐름**:
```
1. Experiment 생성 (control vs variant)
2. Traffic 분배 (50/50)
3. 각 variant로 실행
4. 평가 메트릭 수집
5. 통계적 유의성 분석
6. Winner 선정
```

### security/ - 보안
**목적**: PII 보호, 접근 제어, 감사

**핵심 기능**:
- PII 탐지 및 마스킹
- JWT 인증
- RBAC 권한 관리
- 감사 로그

**구현 파일**:
- `auth.py` - 인증/인가
- `pii_filter.py` - 민감정보 필터링
- `credentials.py` - API 키 관리

**PII 필터링 예시**:
```python
text = "My email is john@example.com and SSN is 123-45-6789"
filtered = pii_filter.mask_pii(text)
# "My email is ***@*** and SSN is ***-**-****"
```

## 개발 우선순위

### Phase 1 (MVP)
1. ✅ Prompt Store 스텁
2. Cost Tracker 구현
3. 기본 Trace 로깅
4. PII 필터링

### Phase 2
1. Prompt Store DB 연동
2. OpenTelemetry 통합
3. Experiment Framework
4. 고급 보안 기능

## 테스트 전략

각 모듈은 독립적으로 테스트 가능해야 합니다:

```python
# tests/unit/platform/test_prompt_store.py
@pytest.mark.asyncio
async def test_prompt_versioning():
    store = PromptStore()
    v1 = await store.create_prompt(name="test", content="v1")
    v2 = await store.update_prompt(name="test", content="v2")
    assert v2.version == 2
```

## 의존성

- **Database**: PostgreSQL (모든 모듈)
- **Cache**: Redis (일부 모듈)
- **Metrics**: Prometheus (Cost, Trace)
- **OpenTelemetry**: Trace 모듈

## 다음 단계

1. Cost Tracker 완전 구현
2. Prompt Store DB 연동
3. Experiment Runner 프로토타입
4. PII Filter 정규식 기반 구현
