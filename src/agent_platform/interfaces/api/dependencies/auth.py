"""
Authentication and authorization dependencies
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import structlog

logger = structlog.get_logger()

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Get current authenticated user

    For MVP, this is a placeholder that returns a mock user.
    In production, this should validate JWT tokens and return real user data.
    """
    # TODO: Implement real JWT validation
    # For now, allow unauthenticated access in development
    if credentials is None:
        logger.warning("unauthenticated_request_allowed")
        return {"user_id": "anonymous", "is_admin": True}

    # Placeholder JWT validation
    return {"user_id": "user_123", "is_admin": False}


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Require admin privileges"""
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
