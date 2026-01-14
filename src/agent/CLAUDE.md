# Agent Module - Development Guide

This guide contains detailed coding conventions and implementation patterns for the agent module.

## Core Principles

### 1. Type Safety
**All code must have complete type hints.**

```python
# Good
async def get_prompt(name: str, version: int | None = None) -> Prompt | None:
    pass

# Bad
async def get_prompt(name, version=None):
    pass
```

### 2. Async/Await First
**All I/O operations must be async.**

```python
# Good - async I/O
async def fetch_data() -> dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        response = await session.get(url)
        return await response.json()

# Bad - synchronous I/O
def fetch_data() -> dict[str, Any]:
    response = requests.get(url)
    return response.json()
```

### 3. Structured Logging
```python
import structlog
logger = structlog.get_logger()

# Good - structured logging
logger.info("prompt_created", prompt_id=str(prompt.id), version=1, author=user_id)

# Bad - string formatting
logger.info(f"Prompt {prompt.id} created with version 1 by {user_id}")
```

## Coding Conventions

### Import Ordering
```python
# 1. Standard library
import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

# 2. Third-party
from sqlalchemy import VARCHAR, func
from sqlalchemy.orm import Mapped, mapped_column

# 3. Local
from .base import Base

# 4. TYPE_CHECKING (for type hints only)
if TYPE_CHECKING:
    from .other_model import OtherModel
```

### SQLAlchemy 2.0 Patterns
```python
# Use Mapped types for full type safety
class MyModel(Base):
    __tablename__ = "my_table"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(VARCHAR(255))
    optional_field: Mapped[str | None] = mapped_column(TEXT)
    json_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Relationships with TYPE_CHECKING
    related: Mapped["RelatedModel"] = relationship(back_populates="my_model")
```

### Pydantic Models
```python
from pydantic import BaseModel, Field

class PromptCreate(BaseModel):
    name: str = Field(..., description="Unique prompt name")
    content: str = Field(..., min_length=1)
    category: str | None = None
```

### Repository Pattern
```python
class MyRepository(BaseRepository[MyModel]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(MyModel, session)

    async def get_by_name(self, name: str) -> MyModel | None:
        """Get record by name.

        Args:
            name: Record name

        Returns:
            Model instance or None if not found
        """
        stmt = select(MyModel).where(MyModel.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
```

## Performance Best Practices

### 1. Database Query Optimization
```python
# Good - single query with eager loading
stmt = select(Task).where(Task.id == task_id).options(selectinload(Task.milestones))
task = (await session.execute(stmt)).scalar_one_or_none()

# Bad - N+1 queries
task = (await session.execute(select(Task).where(Task.id == task_id))).scalar_one()
for milestone_id in task.milestone_ids:
    milestone = await session.get(Milestone, milestone_id)
```

### 2. Parallel Processing
```python
# Good - parallel LLM calls
results = await asyncio.gather(
    llm1.chat_completion(request1),
    llm2.chat_completion(request2),
)

# Bad - sequential processing
result1 = await llm1.chat_completion(request1)
result2 = await llm2.chat_completion(request2)
```

### 3. Caching
```python
# Cache frequently accessed data in Redis
cache_key = f"prompt:{name}:v{version}"
cached = await redis_client.get(cache_key)
if cached:
    return json.loads(cached)

# Compute and cache
result = await expensive_operation()
await redis_client.setex(cache_key, 3600, json.dumps(result))
return result
```

## Error Handling

### 1. Repository Methods
```python
async def get_or_raise(self, id: UUID) -> MyModel:
    """Get record by ID or raise error.

    Args:
        id: Record UUID

    Returns:
        Model instance

    Raises:
        ValueError: If record not found
    """
    instance = await self.get_by_id(id)
    if instance is None:
        raise ValueError(f"Record with id {id} not found")
    return instance
```

### 2. LLM Calls
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def call_llm(self, request: Request) -> Response:
    """Call LLM with automatic retry.

    Args:
        request: LLM request

    Returns:
        LLM response
    """
    return await self.client.complete(request)
```

## Testing Patterns

### 1. Repository Tests
```python
@pytest.mark.asyncio
async def test_repository_get_by_id(session: AsyncSession) -> None:
    # Arrange
    repo = MyRepository(session)
    created = await repo.create(name="test")

    # Act
    retrieved = await repo.get_by_id(created.id)

    # Assert
    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.name == "test"
```

### 2. Mock LLM Responses
```python
@pytest.fixture
def mock_llm_client(mocker: MockerFixture) -> Mock:
    mock = mocker.AsyncMock()
    mock.complete.return_value = {
        "content": "test response",
        "usage": {"input_tokens": 10, "output_tokens": 20},
        "cost": 0.001,
    }
    return mock
```

## Documentation

### 1. Docstrings
```python
def complex_function(param: str, option: int | None = None) -> Result:
    """Brief description of what this function does.

    Detailed explanation if needed. Can span multiple lines
    and include important information about behavior.

    Args:
        param: Description of parameter
        option: Optional parameter description

    Returns:
        Description of return value

    Raises:
        ValueError: When param is invalid
        RuntimeError: When operation fails

    Example:
        >>> result = complex_function("test")
        >>> print(result.value)
        "processed_test"
    """
    pass
```

### 2. Type Hints
```python
# Always use type hints for function signatures
async def process(
    data: list[dict[str, Any]],
    callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> tuple[int, list[str]]:
    """Process data with optional callback."""
    pass
```

## Event-Driven Architecture

### EventBus Pattern
The agent module uses an event-driven architecture to decouple business logic from notification/persistence concerns.

```python
from agent.events.bus import get_event_bus
from agent.events.types import (
    AgentActivityEvent,
    AgentStatus,
    EventType,
)

# In workflow nodes - emit events instead of direct WebSocket calls
async def execute_worker_node(state, config, session):
    event_bus = get_event_bus_from_config(config)

    # Emit event when work starts
    await event_bus.emit(
        AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=milestone_id,
            sequence_number=1,
            agent="worker",
            status=AgentStatus.STARTED,  # Explicit status
            message="Starting execution",
        )
    )

    # ... do work ...

    # Emit event when work completes
    await event_bus.emit(
        AgentActivityEvent(
            type=EventType.AGENT_COMPLETED,
            status=AgentStatus.COMPLETED,  # Explicit status
            details={"output": result, "tokens_used": 100},
            # ... other fields
        )
    )
```

### Event Types
All events inherit from `Event` base class with explicit status fields:

- **Task Events**: `TASK_STARTED`, `TASK_PROGRESS`, `TASK_COMPLETED`, `TASK_FAILED`
- **Milestone Events**: `MILESTONE_STATUS_CHANGED`, `MILESTONE_COMPLETED`, `MILESTONE_FAILED`, `MILESTONE_RETRY`
- **Agent Events**: `AGENT_STARTED`, `AGENT_COMPLETED`, `AGENT_FAILED`
- **LLM Events**: `LLM_CHUNK`, `LLM_COMPLETE`
- **Context Events**: `CONTEXT_COMPRESSED`
- **Breakpoint Events**: `BREAKPOINT_HIT`, `BREAKPOINT_RESUMED`

### Explicit Status (No Heuristics)
The frontend receives explicit status from backend - no keyword-based detection:

```python
# Backend sends explicit status
class AgentStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"

class MilestoneStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"  # Not "completed" - matches backend exactly
    FAILED = "failed"
```

### Event Handlers
Handlers are registered globally in `main.py`:

```python
from agent.events.bus import get_event_bus
from agent.events.handlers.websocket_handler import WebSocketEventHandler
from agent.events.handlers.logging_handler import LoggingEventHandler

# Initialize and register handlers
event_bus = get_event_bus()
ws_handler = WebSocketEventHandler(app.state.ws_manager)
logging_handler = LoggingEventHandler()

event_bus.subscribe_all(ws_handler.handle)
event_bus.subscribe_all(logging_handler.handle)
```

## Common Patterns

### 1. Dependency Injection
```python
# FastAPI dependencies (see api/dependencies.py)
from agent.api.dependencies import DBSession, CurrentUserId

@router.post("/")
async def create_task(
    data: TaskCreate,
    db: DBSession,  # Type alias for Annotated[AsyncSession, Depends(get_db)]
    user_id: CurrentUserId,  # Type alias for current user
) -> TaskResponse:
    """Create new task."""
    repo = TaskRepository(db)
    task = await repo.create(user_id=user_id, **data.model_dump())
    return TaskResponse.model_validate(task)
```

### 2. Context Managers
```python
# Use context managers for resource management
async with DatabaseSessionManager(db_url) as manager:
    async for session in manager.get_session():
        # Use session
        pass
```

### 3. Enum for Constants
```python
from enum import Enum

class TaskComplexity(str, Enum):
    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    CONTEXT_HEAVY = "context_heavy"

# Usage
complexity = TaskComplexity.MODERATE
```

## Security

### 1. Input Validation
```python
# Always validate user input with Pydantic
class UserInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9_-]+$")
    email: str = Field(..., pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
```

### 2. SQL Injection Prevention
```python
# Good - parameterized queries
stmt = select(User).where(User.name == name)

# Bad - string concatenation
stmt = f"SELECT * FROM users WHERE name = '{name}'"  # NEVER DO THIS
```

### 3. Secrets Management
```python
# Good - environment variables
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str
    database_url: str

    class Config:
        env_file = ".env"

# Bad - hardcoded secrets
api_key = "sk-xxx"  # NEVER DO THIS
```
