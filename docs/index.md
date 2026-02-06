# BSAI - Multi-Agent LLM Orchestration System

Welcome to the BSAI documentation.

## Overview

BSAI is a production-ready multi-agent LLM orchestration system built with LangGraph. It provides:

- **Token Cost Optimization**: Automatic LLM selection based on task complexity
- **Quality Assurance**: Independent QA Agent validates all outputs
- **Context Preservation**: Memory system maintains progress across sessions

## Quick Links

- [README](../README.md) - Project overview and quick start
- [GitHub Repository](https://github.com/blas1n/bsai)

## Getting Started

For installation and setup instructions, please refer to the [README](../README.md).

## Architecture

The system consists of 7 specialized agents:

1. **Conductor Agent** - Task analysis and LLM selection
2. **Meta Prompter Agent** - Prompt optimization
3. **Worker Agent** - Task execution
4. **QA Agent** - Output validation
5. **Artifact Extractor Agent** - Code block and artifact extraction
6. **Responder Agent** - Localized response generation (75+ languages)
7. **Summarizer Agent** - Context compression

## Technology Stack

- **LangGraph** - Workflow orchestration
- **LiteLLM** - Multi-provider LLM client
- **FastAPI** - Web framework
- **PostgreSQL** - Database
- **SQLAlchemy 2.0** - Async ORM
- **Alembic** - Database migrations
- **lingua-py** - Language detection (75+ languages)

## Documentation

For the most up-to-date information, please refer to:
- [Project README](../README.md)
- [Development Guide](../src/bsai/CLAUDE.md)
