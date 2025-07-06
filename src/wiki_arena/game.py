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
)
from wiki_arena.events import EventBus, GameEvent
from wiki_arena.wikipedia import LiveWikiService
from wiki_arena.language_models import LanguageModel, ToolCall


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
            error_message=None,
            current_page=start_page,
            steps=0,
        )

        logging.info(
            f"Game {self.id} initialized. Start: '{config.start_page_title}', Target: '{config.target_page_title}'"
        )
        logging.info(f"Player: {config.model.model_name} ({config.model.provider})")
        logging.info(f"Loaded {len(self.tools)} tools.")

        # The game is initialized but not yet started, so we set the status accordingly
        self.state.status = GameStatus.IN_PROGRESS  # TODO(hunter): this should update state to NOT_STARTED from INITIALIZING

    def _generate_game_id(self, model_config: ModelConfig) -> str:
        """Generate descriptive game ID with model info."""
        timestamp = datetime.now()
        date_str = timestamp.strftime("%Y%m%d_%H%M%S")
        uuid_short = str(uuid.uuid4())[:4]
        model_key = model_config.model_name

        return f"{model_key}_{date_str}_{uuid_short}"

    async def play_turn(self) -> bool:
        """Play a single turn of the game. Returns True if game is over, False otherwise."""
        if not self.state:
            logging.error("play_turn called but game state is None. Game cannot proceed.")
            return True

        if self.state.status != GameStatus.IN_PROGRESS:
            logging.warning(f"play_turn called but game status is {self.state.status.value}. Game is already considered over.")
            if not self.state.error_message and self.state.status not in [GameStatus.WON, GameStatus.NOT_STARTED]:
                 self.state.error_message = f"Game ended: play_turn called when status was {self.state.status.value}"
            return True

        current_step = self.state.steps + 1
        current_page_title = self.state.current_page.title

        # Early validation
        if not self.language_model:
            self.state.status = GameStatus.ERROR
            self.state.error_message = "Language model not initialized"
            logging.error(f"Game {self.id}: Critical error - Language model not initialized")
            return True

        try:
            # Get model response
            tool_call_request = await self._get_model_response()

            # Validate and process the model response
            validation_error = self._validate_model_response(tool_call_request)
            if validation_error:
                self._create_error_move(current_step, current_page_title, validation_error, tool_call_request)
                self.state.status = GameStatus.LOST_INVALID_MOVE
                await self._emit_game_ended_event()
                return True

            # Extract target page from tool call
            target_page, extraction_error = self._extract_target_page(tool_call_request)
            if extraction_error:
                self._create_error_move(current_step, current_page_title, extraction_error, tool_call_request)
                self.state.status = GameStatus.LOST_INVALID_MOVE
                await self._emit_game_ended_event()
                return True

            # Validate the link exists on current page
            link_error = self._validate_link(target_page, tool_call_request)
            if link_error:
                self._create_error_move(current_step, current_page_title, link_error, tool_call_request)
                self.state.status = GameStatus.LOST_INVALID_MOVE
                await self._emit_game_ended_event()
                return True

            # Attempt navigation
            try:
                next_page = await self.wiki_service.get_page(target_page, include_all_namespaces=False)
            except (ConnectionError, ValueError) as e:
                nav_error = GameError(
                    type=ErrorType.APP_NAVIGATION_ERROR,
                    message=f"Navigation failed: {e}",
                    metadata={"target_page": target_page, "nav_error": str(e)}
                )
                self._create_error_move(current_step, current_page_title, nav_error, tool_call_request)
                self.state.status = GameStatus.ERROR
                await self._emit_game_ended_event()
                return True

            # Success! Create successful move and update game state
            return await self._handle_successful_move(current_step, current_page_title, next_page, tool_call_request)

        except Exception as e:
            return self._handle_unexpected_exception(e, current_step, current_page_title, locals().get('tool_call_request'))

    async def _get_model_response(self):
        """Get response from language model with proper error handling."""
        try:
            return await self.language_model.generate_response(
                tools=self.tools,
                game_state=self.state
            )
        except Exception as e:
            # Re-raise with provider context for categorization
            if "rate limit" in str(e).lower() or "429" in str(e):
                raise Exception(f"PROVIDER_RATE_LIMIT: {e}")
            elif "timeout" in str(e).lower() or "504" in str(e) or "502" in str(e):
                raise Exception(f"PROVIDER_TIMEOUT: {e}")
            elif any(code in str(e) for code in ["500", "503", "502", "504"]):
                raise Exception(f"PROVIDER_API_ERROR: {e}")
            else:
                raise Exception(f"MODEL_GENERATION_ERROR: {e}")

    def _validate_model_response(self, tool_call_request) -> Optional[GameError]:
        """Validate that the model provided a valid tool call."""
        if not tool_call_request or not tool_call_request.tool_name:
            return GameError(
                type=ErrorType.MODEL_NO_TOOL_CALL,
                message="Language model did not select a valid action",
                metadata={
                    "model_response": tool_call_request.model_text_response if tool_call_request else None,
                    "has_tool_call": bool(tool_call_request and tool_call_request.tool_name)
                }
            )

        # Check if tool exists in available tools
        tool_definition = next((t for t in self.tools if t["name"] == tool_call_request.tool_name), None)
        if not tool_definition:
            return GameError(
                type=ErrorType.MODEL_INVALID_TOOL,
                message=f"Model requested unavailable tool: {tool_call_request.tool_name}",
                metadata={
                    "requested_tool": tool_call_request.tool_name,
                    "tools": [t["name"] for t in self.tools]
                }
            )

        return None


    # TODO(hunter): why are we allowing the model make an error here?
    def _extract_target_page(self, tool_call_request: ToolCall) -> tuple[Optional[str], Optional[GameError]]:
        """Extract target page title from tool call arguments."""
        chosen_tool_args = tool_call_request.tool_arguments or {}

        # Handle various navigation tool parameter formats
        target_page_title = None
        if "page_title" in chosen_tool_args:
            target_page_title = chosen_tool_args.get("page_title")
        elif "page" in chosen_tool_args:
            target_page_title = chosen_tool_args.get("page")
        elif "title" in chosen_tool_args:
            target_page_title = chosen_tool_args.get("title")
        else:
            # Find first string argument as fallback
            for arg_value in chosen_tool_args.values():
                if isinstance(arg_value, str):
                    target_page_title = arg_value
                    break

        if not target_page_title:
            error = GameError(
                type=ErrorType.MODEL_INVALID_TOOL,
                message=f"Tool '{tool_call_request.tool_name}' called without page title argument",
                metadata={
                    "tool_name": tool_call_request.tool_name,
                    "arguments": chosen_tool_args,
                    "expected_params": ["page_title", "page", "title"]
                }
            )
            return None, error

        return target_page_title, None

    def _validate_link(self, target_page: str, tool_call_request) -> Optional[GameError]:
        """Validate that the target page is available as a link on the current page."""
        if target_page not in self.state.current_page.links:
            is_target_page = target_page == self.state.config.target_page_title

            return GameError(
                type=ErrorType.MODEL_INVALID_LINK,
                message=f"Page '{target_page}' is not in available links of '{self.state.current_page.title}'",
                metadata={
                    "requested_page": target_page,
                    "current_page": self.state.current_page.title,
                    "is_target_page": is_target_page,
                    "available_links_count": len(self.state.current_page.links),
                    "tool_call": {
                        "name": tool_call_request.tool_name,
                        "arguments": tool_call_request.tool_arguments
                    }
                }
            )

        return None

    async def _handle_successful_move(self, step: int, from_page: str, new_page: Page, tool_call_request) -> bool:
        """Handle a successful move and update game state."""
        # Update current page
        self.state.current_page = new_page

        # Create successful move record
        move = Move(
            step=step,
            from_page_title=from_page,
            to_page_title=new_page.title,
            model_response=tool_call_request.model_text_response,
            tool_call_attempt={
                "tool_name": tool_call_request.tool_name,
                "arguments": tool_call_request.tool_arguments
            },
            error=None,
            metrics=tool_call_request.metrics
        )

        self.state.move_history.append(move)
        self.state.steps += 1

        logging.info(f"Game {self.id} Step {step}: '{from_page}' -> '{new_page.title}'")

        # Check win condition
        if new_page.title == self.state.config.target_page_title:
            self.state.status = GameStatus.WON
            self.state.error_message = "Target page reached!"
            logging.info(f"Game {self.id}: Won! Reached target '{new_page.title}' in {self.state.steps} steps.")
            game_over = True
        # Check max steps
        elif self.state.steps >= self.state.config.max_steps:
            self.state.status = GameStatus.LOST_MAX_STEPS
            self.state.error_message = "Maximum turns reached"
            logging.info(f"Game {self.id}: Lost - Max turns ({self.state.config.max_steps}) reached.")
            game_over = True
        else:
            game_over = False

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

        return game_over

    async def _emit_game_ended_event(self):
        """Helper method to emit game_ended event."""
        if self.event_bus:
            await self.event_bus.publish(GameEvent(
                type="game_ended",
                game_id=self.id,
                data={"game_state": self.state}
            ))

    def _create_error_move(self, step: int, from_page: str, error: GameError, tool_call_request):
        """Create a move record for an error case."""
        move = Move(
            step=step,
            from_page_title=from_page,
            to_page_title=None,  # No successful navigation
            model_response=tool_call_request.model_text_response if tool_call_request else None,
            tool_call_attempt={
                "tool_name": tool_call_request.tool_name,
                "arguments": tool_call_request.tool_arguments
            } if tool_call_request else None,
            error=error,
            metrics=tool_call_request.metrics if tool_call_request else None
        )

        self.state.move_history.append(move)
        self.state.error_message = error.message

        logging.warning(f"Game {self.id} Step {step}: Error - {error.message}")

    def _handle_unexpected_exception(self, exception: Exception, step: int, from_page: str, tool_call_request) -> bool:
        """Handle unexpected exceptions with proper categorization."""
        error = GameError(
            type=ErrorType.APP_UNKNOWN_ERROR,
            message=f"Unexpected error: {str(exception)}",
            metadata={
                "exception_type": type(exception).__name__,
                "step": step,
                "has_tool_call_request": bool(tool_call_request)
            }
        )

        if tool_call_request:
            self._create_error_move(step, from_page, error, tool_call_request)
        else:
            self.state.error_message = error.message

        self.state.status = GameStatus.ERROR
        logging.error(f"Game {self.id}: {error.message}", exc_info=True)

        # Emit game_ended event if event bus is available
        if self.event_bus:
            asyncio.create_task(self._emit_game_ended_event())

        return True
