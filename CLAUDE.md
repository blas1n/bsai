# BSAI - Claude Development Guide

## Project Overview
BSAI is a **LangGraph-based Multi-Agent LLM Orchestration System** with the following core features:

1. **Token Cost Optimization**: Automatic LLM selection based on task complexity
2. **Quality Assurance**: Independent QA Agent validates all outputs (max 3 retries)
3. **Context Preservation**: Memory system maintains context across session interruptions

## Architecture

- **LiteLLM**: Direct usage for unified multi-provider LLM access
- **LangGraph StateGraph**: Orchestrates 7 specialized agents
- **FastAPI**: REST API with async/await throughout

## Development Guidelines

- **Backend**: [src/agent/CLAUDE.md](src/agent/CLAUDE.md)
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
