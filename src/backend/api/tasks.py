from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, Annotated
import logging

from backend.models.api_models import (
    CreateTaskRequest,
    CreateTaskResponse, 
    ErrorResponse
)
from backend.coordinators.task_coordinator import TaskCoordinator
from backend.dependencies import get_task_coordinator

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)

TaskCoordinatorDep = Annotated[TaskCoordinator, Depends(get_task_coordinator)]

@router.post("", response_model=CreateTaskResponse)
async def create_task(request: CreateTaskRequest, coordinator: TaskCoordinatorDep) -> CreateTaskResponse:
    """Create a new task with multiple competing games."""
    try:
        logger.info(f"Creating task with {len(request.model_names)} games")
        return await coordinator.create_task(request)
    except Exception as e:
        logger.error(f"Failed to create task: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create task: {str(e)}"
        )

@router.get("/{task_id}")
async def get_task_info(task_id: str, coordinator: TaskCoordinatorDep) -> Dict[str, Any]:
    """Get basic information about a task."""
    task_info = await coordinator.get_task_info(task_id)
    if not task_info:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found"
        )
    return task_info

@router.get("")
async def list_active_tasks(coordinator: TaskCoordinatorDep) -> Dict[str, Any]:
    """List all active tasks."""
    try:
        active_tasks = coordinator.get_active_tasks()
        return {
            "active_tasks": active_tasks,
            "total_tasks": len(active_tasks)
        }
    except Exception as e:
        logger.error(f"Failed to list active tasks: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list active tasks: {str(e)}"
        ) 