from fastapi import APIRouter, HTTPException
from typing import List
import logging

from backend.models.api_models import ModelInfoResponse
from backend.services.model_service import model_service

router = APIRouter(prefix="/api/models", tags=["models"])
logger = logging.getLogger(__name__)


@router.get("", response_model=List[ModelInfoResponse])
async def get_models() -> List[ModelInfoResponse]:
    """
    Get a list of all available and supported models for the frontend.
    
    This endpoint is the single source of truth for the frontend to know
    which models can be used in a game. It enriches the model data with
    frontend-specific information like icon URLs.
    """
    try:
        return model_service.get_models()
    except Exception as e:
        logger.error(f"Failed to get models list: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve model list: {str(e)}"
        ) 