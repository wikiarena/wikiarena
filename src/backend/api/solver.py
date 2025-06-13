from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, Any, Optional
import logging

from wiki_arena.solver import SolverRequest, SolverResponse, WikiTaskSolver
from wiki_arena.solver.static_db import static_solver_db
from backend.dependencies import get_solver

router = APIRouter(prefix="/api/solver", tags=["solver"])
logger = logging.getLogger(__name__)

@router.post("/path", response_model=SolverResponse)
async def find_shortest_path(
    request: SolverRequest, 
    solver: WikiTaskSolver = Depends(get_solver)
) -> SolverResponse:
    """
    Find the shortest path between two Wikipedia pages.
    
    This endpoint performs bidirectional BFS to find the optimal path.
    """
    try:
        response = await solver.find_shortest_path(
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

@router.get("/validate/{page_title}")
async def validate_page(page_title: str) -> Dict[str, Any]:
    """
    Check if a Wikipedia page exists in the database.
    
    Useful for validating user input before attempting path finding.
    """
    try:
        exists = await static_solver_db.page_exists(page_title)
        page_id = None
        if exists:
            # Optionally, also return the page ID if it exists
            page_id = await static_solver_db.get_page_id(page_title)

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