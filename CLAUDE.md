# BSAI - Claude Development Guide

## Project Overview
BSAI is a **LangGraph-based Multi-Agent LLM Orchestration System** with the following core features:

1. **Token Cost Optimization**: Automatic LLM selection based on task complexity
2. **Quality Assurance**: Independent QA Agent validates all outputs (max 3 retries)
3. **Context Preservation**: Memory system maintains context across session interruptions
4. **Dynamic Plan Modification (ReAct Pattern)**: Runtime plan adjustment based on execution observations

## Architecture

- **LiteLLM**: Direct usage for unified multi-provider LLM access
- **LangGraph StateGraph**: Orchestrates 8 specialized agents
- **FastAPI**: REST API with async/await throughout

### Workflow Flow
```
analyze_task → select_llm → [generate_prompt?] → execute_worker
    → verify_qa → [replan?] → check_context → [summarize?]
    → advance → [next_milestone | task_summary]
    → task_summary → generate_response → END
```

**ReAct Replanning Flow**: When QA detects plan viability issues (NEEDS_REVISION or BLOCKED), the workflow routes to the `replan` node which uses the Conductor to modify the execution plan dynamically.

### Key Agents
1. **Conductor**: Break request into milestones, select LLM, replan during execution
2. **Meta Prompter**: Generate optimized prompts (for MODERATE+ tasks)
3. **Worker**: Execute actual task with MCP tools, extract observations
4. **QA Agent**: Validate outputs with structured feedback, assess plan viability
5. **Summarizer**: Compress context when memory pressure
6. **Artifact Extractor**: Extract code blocks and files
7. **Task Summary**: Summarize all milestones for Responder
8. **Responder**: Generate user-friendly response

## Development Guidelines

- **Backend**: [src/bsai/CLAUDE.md](src/bsai/CLAUDE.md)
- **Frontend**: [web/CLAUDE.md](web/CLAUDE.md)

## Quick Reference

### Code Quality
```bash
# Linting
ruff check .

# Type checking
mypy src/

# Auto-fix
ruff check --fix .
```

### Testing
```bash
pytest                           # Run all tests
pytest --cov=src                 # With coverage
pytest -x                        # Fast fail
```

### Database Migrations
```bash
# Create migration
python3 -m alembic revision --autogenerate -m "Description"

# Apply migrations
python3 -m alembic upgrade head

# Rollback
python3 -m alembic downgrade -1
```

## References

### Backend
- FastAPI: https://fastapi.tiangolo.com
- Pydantic: https://docs.pydantic.dev
- SQLAlchemy: https://docs.sqlalchemy.org/en/20/
- LangGraph: https://langchain-ai.github.io/langgraph/
- LiteLLM: https://docs.litellm.ai/

### Frontend
- Next.js: https://nextjs.org/docs
- React: https://react.dev
- Tailwind CSS: https://tailwindcss.com/docs
- Radix UI: https://www.radix-ui.com/docs
- Zustand: https://zustand-demo.pmnd.rs/
