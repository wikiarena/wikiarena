from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
import logging

from backend.models.solver_models import SolverRequest, SolverResponse, SolverStatus
from backend.services.wiki_solver_service import wiki_solver
from backend.services.wiki_db_service import wiki_db

router = APIRouter(prefix="/api/solver", tags=["solver"])
logger = logging.getLogger(__name__)

@router.post("/path", response_model=SolverResponse)
async def find_shortest_path(request: SolverRequest) -> SolverResponse:
    """
    Find the shortest path between two Wikipedia pages.
    
    This endpoint performs bidirectional BFS to find the optimal path.
    """
    try:
        # Initialize solver if needed (simple hasattr check for one-time init)
        if not hasattr(wiki_solver, '_initialized') or not wiki_solver._initialized:
            await wiki_solver.initialize()
            wiki_solver._initialized = True
        
        response = await wiki_solver.find_shortest_path(
            request.start_page, 
            request.target_page
        )
        
        logger.info(
            f"Path found: {request.start_page} -> {request.target_page} "
            f"({response.path_length} steps, {response.computation_time_ms:.1f}ms, "
        )
        
        return response
        
    except ValueError as e:
        logger.warning(f"Path finding failed: {e}")
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error in path finding: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@router.get("/status", response_model=SolverStatus)
async def get_solver_status() -> SolverStatus:
    """
    Get the current status of the Wikipedia solver.
    
    Returns information about the database state.
    """
    try:
        # Get database statistics
        page_count: Optional[int] = None
        link_count: Optional[int] = None
        database_ready: bool = False
        try:
            page_count, link_count = await wiki_db.get_database_stats()
            database_ready = page_count > 0 and link_count > 0 # Or just page_count > 0
        except Exception as db_error:
            logger.warning(f"Could not get database stats: {db_error}")
            # page_count, link_count, database_ready remain as initialized above (None, None, False)
        
        # Cache statistics calls removed.
        
        return SolverStatus(
            database_ready=database_ready,
            total_pages=page_count,
            total_links=link_count,
            last_updated=None  # TODO: Add timestamp tracking to database
        )
        
    except Exception as e:
        logger.error(f"Failed to get solver status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get status: {str(e)}"
        )

# Removed /cache/stats endpoint
# Removed DELETE /cache endpoint

@router.get("/validate/{page_title}")
async def validate_page(page_title: str) -> Dict[str, Any]: # Kept Dict[str, Any] for now
    """
    Check if a Wikipedia page exists in the database.
    
    Useful for validating user input before attempting path finding.
    """
    try:
        exists = await wiki_db.page_exists(page_title)
        page_id = None
        if exists:
            # Optionally, also return the page ID if it exists
            page_id = await wiki_db.get_page_id(page_title)

        return {
            "page_title": page_title,
            "exists": exists,
            "page_id": page_id,
            "message": "Page found in database" if exists else "Page not found in database"
        }
        
    except Exception as e:
        logger.error(f"Failed to validate page: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to validate page: {str(e)}"
        ) 