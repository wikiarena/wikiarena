import logging
from typing import Dict, List, Optional
from datetime import datetime

from wiki_arena import EventBus, GameEvent
from wiki_arena.models import Task

from backend.models.api_models import CreateTaskRequest, CreateTaskResponse
from backend.coordinators.game_coordinator import GameCoordinator
from backend.services.task_selector_service import task_selector_service

logger = logging.getLogger(__name__)

class TaskData:
    """Internal representation of a task with its associated games."""
    def __init__(self, task_id: str, task: Task, game_ids: List[str]):
        self.task_id = task_id
        self.task = task
        self.game_ids = game_ids
        self.created_at = datetime.now()

class TaskCoordinator:
    """
    Orchestrates task-level operations and coordinates multiple games per task.
    
    Responsibilities:
    - Task lifecycle management (create, monitor)
    - Game orchestration via GameCoordinator
    - Task-game mapping and relationships
    - Task-level event handling
    """
    
    def __init__(self, event_bus: EventBus, game_coordinator: GameCoordinator):
        self.event_bus = event_bus
        self.game_coordinator = game_coordinator
        self.active_tasks: Dict[str, TaskData] = {}  # task_id -> TaskData
        self.game_to_task: Dict[str, str] = {}  # game_id -> task_id
        
    # NOTE: tasks already have an id but it doesn't have timestamp info
    def _generate_task_id(self, start_page: str, target_page: str) -> str:
        """Generate a descriptive task ID with titles and datetime."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Clean page titles for use in ID and URL (replace spaces and special chars)
        clean_start = start_page.replace(" ", "_").replace("/", "_")
        clean_target = target_page.replace(" ", "_").replace("/", "_")
        return f"{clean_start}__to__{clean_target}__{timestamp}"
    
    async def create_task(self, request: CreateTaskRequest) -> CreateTaskResponse:
        """Create a new task with multiple competing games."""
        logger.info(f"Creating task with strategy: {request.task_strategy.type}, {len(request.model_selections)} games")
        
        # Select task using the specified strategy
        task = await task_selector_service.select_task(request.task_strategy)
        if not task:
            raise ValueError("Failed to select a valid task")
        
        logger.info(f"Selected task: {task.start_page_title} -> {task.target_page_title}")
        
        # Generate task ID
        task_id = self._generate_task_id(task.start_page_title, task.target_page_title)
        
        # setup games for this task (execution won't start until task_solved event)
        game_ids = []
        for i, model_selection in enumerate(request.model_selections, start=1):
            try:
                game_id = await self.game_coordinator.setup_game(
                    task=task,
                    model_selection=model_selection,
                    max_steps=request.max_steps
                )
                game_ids.append(game_id)
                
                # Track game-to-task mapping
                self.game_to_task[game_id] = task_id
                
                logger.info(f"Setup game {i}/{len(request.model_selections)}: {game_id}")
                
            except Exception as e:
                logger.error(f"Failed to setup game {i}: {e}")
                # Clean up any games that were successfully created
                for cleanup_game_id in game_ids:
                    try:
                        await self.game_coordinator.terminate_game(cleanup_game_id)
                        self.game_to_task.pop(cleanup_game_id, None)
                    except Exception as cleanup_error:
                        logger.error(f"Failed to cleanup game {cleanup_game_id}: {cleanup_error}")
                raise ValueError(f"Failed to setup game {i}: {str(e)}")
        
        # Store task data
        task_data = TaskData(task_id, task, game_ids)
        self.active_tasks[task_id] = task_data
        
        # Emit task_selected event
        await self.event_bus.publish(GameEvent(
            type="task_selected",
            game_id=task_id,  # Use task_id as game_id for task-level events TODO(hunter): this feels wrong
            data={
                "task_id": task_id,
                "task": task,
                "game_ids": game_ids
            }
        ))
        
        logger.info(f"Task {task_id} created successfully with {len(game_ids)} games")
        
        return CreateTaskResponse(
            task_id=task_id,
            start_page=task.start_page_title,
            target_page=task.target_page_title,
            game_ids=game_ids
        )
    
    async def get_task_info(self, task_id: str) -> Optional[Dict]:
        """Get basic task information."""
        task_data = self.active_tasks.get(task_id)
        if not task_data:
            return None
        
        return {
            "task_id": task_id,
            "start_page": task_data.task.start_page_title,
            "target_page": task_data.task.target_page_title,
            "game_ids": task_data.game_ids,
            "created_at": task_data.created_at.isoformat()
        }
    
    def get_task_id_for_game(self, game_id: str) -> Optional[str]:
        """Get the task ID that contains a specific game."""
        return self.game_to_task.get(game_id)
    
    def get_active_tasks(self) -> Dict[str, Dict]:
        """Get information about all active tasks."""
        return {
            task_id: {
                "start_page": task_data.task.start_page_title,
                "target_page": task_data.task.target_page_title,
                "game_count": len(task_data.game_ids),
                "created_at": task_data.created_at.isoformat()
            }
            for task_id, task_data in self.active_tasks.items()
        }
    
    async def handle_task_solved(self, event: GameEvent):
        """Handle task_solved events to start execution of all games in the task."""
        task_id = event.data.get("task_id")
        game_ids = event.data.get("game_ids", [])
        
        if not task_id:
            logger.warning("Received task_solved event without task_id")
            return
        
        logger.info(f"Task {task_id} solved, starting execution for {len(game_ids)} games")
        
        # Start execution for all games in this task
        started_count = await self.game_coordinator.start_games(game_ids, background=True)
        
        if started_count == len(game_ids):
            logger.info(f"Successfully started all {started_count} games for task {task_id}")
        else:
            logger.warning(f"Only started {started_count}/{len(game_ids)} games for task {task_id}")
    
    async def cleanup_completed_games(self):
        """Clean up references to completed games and empty tasks."""
        completed_tasks = []
        
        for task_id, task_data in self.active_tasks.items():
            # Check if all games in this task are completed
            remaining_games = []
            for game_id in task_data.game_ids:
                if game_id in self.game_coordinator.active_games:
                    remaining_games.append(game_id)
                else:
                    # Game completed, remove from mapping
                    self.game_to_task.pop(game_id, None)
            
            if not remaining_games:
                # All games completed, mark task for removal
                completed_tasks.append(task_id)
                logger.info(f"Task {task_id} completed - all games finished")
            else:
                # Update game list
                task_data.game_ids = remaining_games
        
        # Remove completed tasks
        for task_id in completed_tasks:
            del self.active_tasks[task_id]
    
    async def shutdown(self):
        """Gracefully shutdown TaskCoordinator."""
        logger.info("Shutting down TaskCoordinator...")
        
        # Clear all mappings
        self.active_tasks.clear()
        self.game_to_task.clear()
        
        logger.info("TaskCoordinator shutdown complete") 