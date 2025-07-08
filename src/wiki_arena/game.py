import random
import logging
from datetime import datetime
from typing import Optional, List, Tuple
import uuid
import asyncio
import json

from wiki_arena.models import (
    GameConfig,
    GameState,
    GameStatus,
    Page,
    Move,
    GameError,
    ErrorType,
    ModelConfig,
    SystemMessage,
    UserMessage,
    ToolResultMessage,
    AssistantToolCall,
)
from wiki_arena.events import EventBus, GameEvent
from wiki_arena.wikipedia import LiveWikiService
from wiki_arena.language_models import LanguageModel, LLMProviderError
from wiki_arena.tools import get_tool_by_name


logger = logging.getLogger(__name__)


class Game:
    def __init__(
        self,
        config: GameConfig,
        wiki_service: LiveWikiService,
        language_model: LanguageModel,
        start_page: Page,
        tools: List[dict],
        event_bus: Optional[EventBus] = None,
    ):
        """Initialize the game with all dependencies and a starting page."""
        self.config = config
        self.wiki_service = wiki_service
        self.language_model = language_model
        self.tools = tools
        self.event_bus = event_bus

        self.id = self._generate_game_id(config.model)

        self.state = GameState(
            game_id=self.id,
            config=config,
            status=GameStatus.NOT_STARTED,
            current_page=start_page,
            steps=0,
        )

        self._initialize_context()

        logger.info(
            f"Game {self.id} initialized. Start: '{config.start_page_title}', Target: '{config.target_page_title}'"
        )
        logger.info(f"Player: {config.model.model_name} ({config.model.provider})")
        logger.info(f"Loaded {len(self.tools)} tools.")

    def _generate_game_id(self, model_config: ModelConfig) -> str:
        """Generate descriptive game ID with model info."""
        timestamp = datetime.now()
        date_str = timestamp.strftime("%Y%m%d_%H%M%S")
        uuid_short = uuid.uuid4().hex[:4]
        model_key = model_config.model_name

        return f"{model_key}_{date_str}_{uuid_short}"

    def _initialize_context(self):
        """Sets up the initial system and user messages in the context."""
        # System Prompt
        system_prompt = self.state.config.system_prompt_template.format(
            start_page_title=self.state.config.start_page_title,
            target_page_title=self.state.config.target_page_title,
        )
        self.state.context.append(SystemMessage(content=system_prompt))

        # Initial User Message (contains the first page's content)
        initial_user_message = (
            f"You are currently on the page '{self.state.current_page.title}'.\n"
            f"Here are the available links:\n{self.state.current_page.links}"
        )
        self.state.context.append(UserMessage(content=initial_user_message))

    async def run(self):
        """Run the game until completion."""

        if self.state.status == GameStatus.NOT_STARTED:
            self.state.status = GameStatus.IN_PROGRESS
            logger.info(f"Game {self.id} started.")

        while self.state.status == GameStatus.IN_PROGRESS:
            # Small delay between moves to avoid overwhelming services and to allow for observation.
            # await asyncio.sleep(1.0)
            await self._play_turn()

        logger.info(f"Game {self.id} completed with status: {self.state.status.value}")

    async def _play_turn(self) -> None:
        """Play a single turn of the game following a retry loop for recoverable errors."""
        if not self.state:
            logger.error("_play_turn called but game state is None. Game cannot proceed.")
            return
        
        if self.state.status != GameStatus.IN_PROGRESS:
            logger.warning(f"_play_turn called but game status is {self.state.status.value}. Game is already considered over.")
            return

        current_step = self.state.steps + 1
        current_page_title = self.state.current_page.title
        
        MAX_ATTEMPTS = 3 # I am realizing that these cost money
        last_error = None

        # TODO(hunter): this whole thing probably needs to be in a try catch block as to not kill the app
        for attempt in range(MAX_ATTEMPTS):
            # 1. Get model response
            try:
                assistant_message = await self.language_model.generate_response(
                    tools=self.tools,
                        context=self.state.context,
                        game_state=self.state,
                    )
                self.state.context.append(assistant_message)
            except LLMProviderError as e:
                logger.error(f"Attempt {attempt + 1}: Model provider error: {e}", exc_info=True)
                last_error = GameError(type=ErrorType.PROVIDER_API_ERROR, message=str(e))
                break # end game on api errors

            # 2. Check for tool calls
            if not assistant_message.tool_calls:
                logger.warning(f"Attempt {attempt + 1}: Model did not call a tool.")
                self.state.context.append(
                    UserMessage(content="You must use a tool to navigate. Please choose one of the available tools.")
                )
                last_error = GameError(type=ErrorType.MODEL_NO_TOOL_CALL, message="Model did not call a tool.")
                continue

            # For this game, we only handle the first tool call
            tool_call = assistant_message.tool_calls[0]

            # 3. Validate tool name
            try:
                tool_info = get_tool_by_name(tool_call.name)
                tool_implementation = tool_info["implementation"]
            except ValueError as e:
                logger.warning(f"Attempt {attempt + 1}: Model called an invalid tool '{tool_call.name}'.")
                error_message = f"Error: {str(e)}. You must use one of the available tools."
                self.state.context.append(
                    ToolResultMessage(
                        tool_call_id=tool_call.id,
                        content=error_message,
                        is_error=True
                    )
                )
                last_error = GameError(type=ErrorType.MODEL_INVALID_TOOL, message=str(e))
                continue

            # 4. Validate tool call argument schema
            tool_schema = tool_info.get("schema", {})
            input_schema = tool_schema.get("inputSchema", {})
            required_params = input_schema.get("required", [])
            provided_args = tool_call.arguments or {}

            missing_params = [p for p in required_params if p not in provided_args]
            if missing_params:
                error_message = f"Error: Missing required arguments for tool '{tool_call.name}'. Missing: {', '.join(missing_params)}"
                logger.warning(f"Attempt {attempt + 1}: {error_message}")
                self.state.context.append(
                    ToolResultMessage(
                        tool_call_id=tool_call.id,
                        content=error_message,
                        is_error=True
                    )
                )
                last_error = GameError(
                    type=ErrorType.MODEL_INVALID_TOOL,
                    message="Missing required arguments for tool call.",
                    metadata={"missing_params": missing_params}
                )
                continue

            to_page_title = tool_call.arguments["to_page_title"]
            # 5. Validate link is on the current page
            if to_page_title not in self.state.current_page.links:
                is_target_page = to_page_title == self.state.config.target_page_title
                logger.warning(f"Attempt {attempt + 1}: Model chose a link '{to_page_title}' that is not on the current page.")
                error_message = f"Error: Page '{to_page_title}' is not in available links of '{self.state.current_page.title}'"
                self.state.context.append(
                    ToolResultMessage(
                        tool_call_id=tool_call.id,
                        content=error_message,
                        is_error=True
                    )
                )
                last_error = GameError(
                    type=ErrorType.MODEL_INVALID_LINK,
                    message=error_message,
                    metadata={
                        "current_page": self.state.current_page.title,
                        "requested_page": to_page_title,
                        "is_target_page": is_target_page,
                        "available_links_count": len(self.state.current_page.links),
                    }
                )
                continue

            # 6. Execute tool and handle results
            try:
                # TODO(hunter): passing the wiki_service feels wrong here. guess we go back to mcp client
                next_page = await tool_implementation(wiki_service=self.wiki_service, **tool_call.arguments)
                # TODO(hunter): model needs to know if the link redirected so they don't get confused
                tool_result_message = (
                    f"Successfully navigated to '{next_page.title}'. "
                    f"It has {len(next_page.links)} links."
                )
                self.state.context.append(
                    ToolResultMessage(tool_call_id=tool_call.id, content=tool_result_message, is_error=False)
                )
                
                await self._handle_successful_move(current_step, current_page_title, next_page)
                return  # Success, exit the turn

            except (ConnectionError, ValueError) as e:
                # Handle tool execution errors (e.g., page not found)
                logger.warning(f"Attempt {attempt + 1}: Tool '{tool_call.name}' failed. Error: {e}")
                self.state.context.append(
                    ToolResultMessage(
                        tool_call_id=tool_call.id,
                        content=f"Error executing tool: {e}",
                        is_error=True
                    )
                )
                last_error = GameError(type=ErrorType.APP_NAVIGATION_ERROR, message=f"Navigation failed: {e}")
                continue
            except Exception as e:
                # Handle unexpected errors by ending the game
                await self._handle_unexpected_exception(e, current_step, current_page_title, tool_call)
                return

        # If the loop finishes, all attempts have failed.
        logger.error(f"Game lost after {MAX_ATTEMPTS} failed attempts to make a move.")
        self._create_error_move(current_step, current_page_title, last_error)
        self.state.status = GameStatus.LOST_INVALID_MOVE
        await self._emit_game_ended_event()
    
    async def _handle_successful_move(self, step: int, from_page: str, new_page: Page) -> None:
        """Handle a successful move and update game state."""
        # Update current page
        self.state.current_page = new_page

        # Create successful move record
        move = Move(
            step=step,
            from_page_title=from_page,
            to_page_title=new_page.title,
            error=None
        )

        self.state.move_history.append(move)
        self.state.steps += 1

        logger.info(f"Game {self.id} Step {step}: '{from_page}' -> '{new_page.title}'")

        # Check win condition
        game_over = False
        if new_page.title == self.state.config.target_page_title:
            self.state.status = GameStatus.WON
            logger.info(f"Game {self.id}: Won! Reached target '{new_page.title}' in {self.state.steps} steps.")
            game_over = True
        # Check max steps
        elif self.state.steps >= self.state.config.max_steps:
            self.state.status = GameStatus.LOST_MAX_STEPS
            self.state.error_message = "Maximum turns reached"
            logger.info(f"Game {self.id}: Lost - Max turns ({self.state.config.max_steps}) reached.")
            game_over = True

        # Provide the context for the next turn if the game is still in progress
        # TODO(hunter): I am pretty sure this is redundant with tool call result. we need one or the other
        if not game_over:
            new_user_message = (
                f"You are now on the page '{self.state.current_page.title}'.\n"
                f"Here are the available links:\n{self.state.current_page.links}"
            )
            self.state.context.append(UserMessage(content=new_user_message))

        # Emit event if event bus is available
        if self.event_bus:
            await self.event_bus.publish(GameEvent(
                type="move_completed",
                game_id=self.id,
                data={
                    "move": move,
                    "game_state": self.state,
                    "from_page": from_page,
                    "to_page": new_page.title
                }
            ))

            if game_over:
                await self._emit_game_ended_event()

    async def _emit_game_ended_event(self):
        """Helper method to emit game_ended event."""
        if self.event_bus:
            await self.event_bus.publish(GameEvent(
                type="game_ended",
                game_id=self.id,
                data={"game_state": self.state}
            ))

    def _create_error_move(self, step: int, from_page: str, error: GameError):
        """Create a move record for an error case."""
        move = Move(
            step=step,
            from_page_title=from_page,
            to_page_title=None,  # No successful navigation
            error=error
        )

        self.state.move_history.append(move)
        self.state.error_message = error.message

        logger.warning(f"Game {self.id} Step {step}: Error - {error.message}")

    async def _handle_unexpected_exception(self, exception: Exception, step: int, from_page: str, tool_call: Optional[AssistantToolCall]) -> None:
        """Handle unexpected exceptions with proper categorization."""
        error = GameError(
            type=ErrorType.APP_UNKNOWN_ERROR,
            message=f"Unexpected error: {str(exception)}",
            metadata={
                "exception_type": type(exception).__name__,
                "step": step,
                "has_tool_call_request": bool(tool_call)
            }
        )

        if tool_call:
            self._create_error_move(step, from_page, error)
        else:
            self.state.error_message = error.message
            # If there's no tool call, we might still have metrics from the failed model response
            # So we create a move to record the error and the API call cost
            move = Move(
                step=step,
                from_page_title=from_page,
                to_page_title=None,
                error=error
            )
            self.state.move_history.append(move)


        self.state.status = GameStatus.ERROR
        logger.error(f"Game {self.id}: {error.message}", exc_info=True)
        await self._emit_game_ended_event() 