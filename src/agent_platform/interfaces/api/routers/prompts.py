"""
Prompt management endpoints
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
import structlog

from agent_platform.interfaces.api.dependencies.auth import get_current_user

logger = structlog.get_logger()

router = APIRouter()


class PromptCreate(BaseModel):
    """Create prompt request"""

    name: str = Field(..., description="Unique prompt identifier")
    content: str = Field(..., description="Prompt content/template")
    description: Optional[str] = Field(None, description="Prompt description")
    category: Optional[str] = Field(None, description="Prompt category")
    tags: Optional[dict] = Field(None, description="Searchable tags")
    template_variables: Optional[dict] = Field(None, description="Required variables")


class PromptUpdate(BaseModel):
    """Update prompt request"""

    content: str = Field(..., description="New prompt content")
    commit_message: str = Field(..., description="Reason for change")


class PromptResponse(BaseModel):
    """Prompt response"""

    id: UUID
    name: str
    content: str
    description: Optional[str]
    category: Optional[str]
    version: int
    is_active: bool
    created_at: str
    updated_at: str


class PromptVersionResponse(BaseModel):
    """Prompt version response"""

    id: UUID
    prompt_id: UUID
    version_number: int
    content: str
    commit_message: Optional[str]
    author: str
    created_at: str


@router.post("/", response_model=PromptResponse, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    prompt_data: PromptCreate,
    current_user: dict = Depends(get_current_user),
) -> PromptResponse:
    """Create a new prompt"""
    from agent_platform.platform.prompt_store.store import prompt_store

    logger.info(
        "creating_prompt", name=prompt_data.name, user_id=current_user["user_id"]
    )

    try:
        prompt = await prompt_store.create_prompt(
            name=prompt_data.name,
            content=prompt_data.content,
            description=prompt_data.description,
            category=prompt_data.category,
            tags=prompt_data.tags,
            template_variables=prompt_data.template_variables,
            author=current_user["user_id"],
        )

        logger.info("prompt_created", prompt_id=str(prompt.id), name=prompt_data.name)
        return prompt

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("prompt_creation_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create prompt: {str(e)}",
        )


@router.get("/", response_model=List[PromptResponse], status_code=status.HTTP_200_OK)
async def list_prompts(
    category: Optional[str] = Query(None, description="Filter by category"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of items to return"),
    current_user: dict = Depends(get_current_user),
) -> List[PromptResponse]:
    """List all prompts"""
    from agent_platform.platform.prompt_store.store import prompt_store

    try:
        prompts = await prompt_store.list_prompts(
            category=category, skip=skip, limit=limit
        )
        return prompts

    except Exception as e:
        logger.error("prompt_list_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list prompts: {str(e)}",
        )


@router.get(
    "/{name}", response_model=PromptResponse, status_code=status.HTTP_200_OK
)
async def get_prompt(
    name: str,
    version: Optional[int] = Query(None, description="Specific version number"),
    current_user: dict = Depends(get_current_user),
) -> PromptResponse:
    """Get prompt by name (optionally specific version)"""
    from agent_platform.platform.prompt_store.store import prompt_store

    try:
        prompt = await prompt_store.get_prompt(name=name, version=version)

        if not prompt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Prompt '{name}' not found",
            )

        return prompt

    except HTTPException:
        raise
    except Exception as e:
        logger.error("prompt_fetch_failed", name=name, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch prompt: {str(e)}",
        )


@router.put(
    "/{name}", response_model=PromptResponse, status_code=status.HTTP_200_OK
)
async def update_prompt(
    name: str,
    update_data: PromptUpdate,
    current_user: dict = Depends(get_current_user),
) -> PromptResponse:
    """Update prompt (creates new version)"""
    from agent_platform.platform.prompt_store.store import prompt_store

    logger.info("updating_prompt", name=name, user_id=current_user["user_id"])

    try:
        prompt = await prompt_store.update_prompt(
            name=name,
            content=update_data.content,
            commit_message=update_data.commit_message,
            author=current_user["user_id"],
        )

        logger.info("prompt_updated", prompt_id=str(prompt.id), name=name)
        return prompt

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("prompt_update_failed", name=name, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update prompt: {str(e)}",
        )


@router.get(
    "/{name}/versions",
    response_model=List[PromptVersionResponse],
    status_code=status.HTTP_200_OK,
)
async def list_prompt_versions(
    name: str,
    current_user: dict = Depends(get_current_user),
) -> List[PromptVersionResponse]:
    """List all versions of a prompt"""
    from agent_platform.platform.prompt_store.store import prompt_store

    try:
        versions = await prompt_store.list_versions(name=name)
        return versions

    except Exception as e:
        logger.error("prompt_versions_fetch_failed", name=name, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch prompt versions: {str(e)}",
        )


@router.post(
    "/{name}/rollback/{version}",
    response_model=PromptResponse,
    status_code=status.HTTP_200_OK,
)
async def rollback_prompt(
    name: str,
    version: int,
    current_user: dict = Depends(get_current_user),
) -> PromptResponse:
    """Rollback prompt to specific version"""
    from agent_platform.platform.prompt_store.store import prompt_store

    logger.info(
        "rolling_back_prompt",
        name=name,
        target_version=version,
        user_id=current_user["user_id"],
    )

    try:
        prompt = await prompt_store.rollback(
            name=name, version=version, author=current_user["user_id"]
        )

        logger.info("prompt_rolled_back", name=name, version=version)
        return prompt

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("prompt_rollback_failed", name=name, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rollback prompt: {str(e)}",
        )
