import random
import logging
from datetime import datetime
from typing import Optional, List, Tuple
import uuid
import asyncio

from wiki_arena.data_models.game_models import (
    GameConfig,
    GameState,
    GameStatus,
    Page,
    Move,
    GameError,
    ErrorType
)
from wiki_arena.mcp_client.client import MCPClient
from mcp.types import Tool, CallToolResult, TextContent

from wiki_arena.language_models import PROVIDERS
from wiki_arena.language_models.language_model import LanguageModel, ToolCall

# Capability-based architecture
from wiki_arena.services.capability_registry import CapabilityRegistry
from wiki_arena.capabilities.navigation import INavigationCapability, NavigationResult

class GameManager:
    def __init__(self, mcp_client: MCPClient):
        """Initialize the game manager with an MCP client."""
        self.mcp_client = mcp_client
        self.capability_registry = CapabilityRegistry(mcp_client)
        self.state: Optional[GameState] = None
        self.language_model: Optional[LanguageModel] = None
        self.available_tools: List[Tool] = []
        # TODO(hunter): I know start game logic shouldn't be in init but I want to know why

    def _generate_game_id(self, model_config) -> str:
        """Generate descriptive game ID with model info."""
        timestamp = datetime.now()
        date_str = timestamp.strftime("%Y%m%d_%H%M%S")
        uuid_short = str(uuid.uuid4())[:8]
        model_key = model_config.get_storage_key()
        
        return f"{model_key}_{date_str}_{uuid_short}"

    async def start_game(self, config: GameConfig) -> GameState:
        """Start a new game with the given configuration."""
        self.state = GameState(
            game_id=self._generate_game_id(config.model),
            config=config,
            status=GameStatus.NOT_STARTED,
            error_message=None # Initialize error_message
        )

        # Initialize Language Model using simplified system
        try:
            provider = config.model.provider
            if provider not in PROVIDERS:
                available_providers = list(PROVIDERS.keys())
                raise ValueError(f"Unknown provider '{provider}'. Available: {available_providers}")
            
            provider_class = PROVIDERS[provider]
            self.language_model = provider_class(config.model)
            logging.info(f"Using {config.model.provider} ({config.model.model_name}) for link selection.")
        except ValueError as e:
            logging.error(f"Failed to create language model: {e}")
            self.state.status = GameStatus.ERROR
            self.state.error_message = f"Language model initialization failed: {e}"
            return self.state
        except Exception as e:
            logging.error(f"Unexpected error creating language model: {e}")
            self.state.status = GameStatus.ERROR
            self.state.error_message = f"Language model initialization failed: {e}"
            return self.state

        try:
            # Initialize capability registry
            if not await self.capability_registry.initialize():
                self.state.status = GameStatus.ERROR
                self.state.error_message = "Failed to initialize capabilities"
                logging.error(self.state.error_message)
                return self.state
            
            # Get navigation capability
            nav_capability = self.capability_registry.get_navigation_capability()
            if not nav_capability:
                self.state.status = GameStatus.ERROR
                self.state.error_message = "Navigation capability not available"
                logging.error(self.state.error_message)
                return self.state

            # Still need tools for language model interface
            list_tools_result = await self.mcp_client.list_tools()
            self.available_tools = list_tools_result.tools
            if not self.available_tools:
                logging.warning("No tools discovered from MCP server. The game might not function correctly if tools are expected.")
            else:
                logging.info(f"Discovered {len(self.available_tools)} tools from MCP server.")

            # Use navigation capability to get initial page
            nav_result = await nav_capability.navigate_to_page(config.start_page_title)
            if not nav_result.is_success:
                self.state.status = GameStatus.ERROR
                self.state.error_message = nav_result.error_message
                logging.error(f"Failed to initialize start page '{config.start_page_title}': {nav_result.error_message}")
                return self.state

            self.state.current_page = nav_result.page
            self.state.status = GameStatus.IN_PROGRESS
            self.state.steps = 0 # Start at 0 steps, first move will increment it to 1
            
            logging.info(f"Game started. ID: {self.state.game_id}. Start: '{config.start_page_title}', Target: '{config.target_page_title}'")
            return self.state
            
        except Exception as e:
            logging.error(f"Unhandled exception during game start: {e}", exc_info=True)
            self.state.status = GameStatus.ERROR
            self.state.error_message = f"Unhandled exception during game start: {e}"
            return self.state

    async def play_turn(self) -> bool: # True if game over, False otherwise
        """Play a single turn of the game. Returns True if game is over, False otherwise."""
        if not self.state:
            logging.error("play_turn called but game state is None. Game cannot proceed.")
            return True # Game is over (critically)

        if self.state.status != GameStatus.IN_PROGRESS:
            logging.warning(f"play_turn called but game status is {self.state.status.value}. Game is already considered over.")
            if not self.state.error_message and self.state.status not in [GameStatus.WON, GameStatus.NOT_STARTED]:
                 self.state.error_message = f"Game ended: play_turn called when status was {self.state.status.value}"
            return True # Game is over

        current_step = self.state.steps + 1
        current_page_title = self.state.current_page.title

        # Early validation - these are critical errors that prevent any move attempt
        critical_error = self._check_critical_errors()
        if critical_error:
            self.state.status = GameStatus.ERROR
            self.state.error_message = critical_error
            logging.error(f"Game {self.state.game_id}: Critical error - {critical_error}")
            return True

        try:
            # Attempt to get model response
            tool_call_request = await self._get_model_response()
            
            # Validate and process the model response
            validation_error = self._validate_model_response(tool_call_request)
            if validation_error:
                self._create_error_move(current_step, current_page_title, validation_error, tool_call_request)
                self.state.status = GameStatus.LOST_INVALID_MOVE
                return True
            
            # Extract target page from tool call
            target_page, extraction_error = self._extract_target_page(tool_call_request)
            if extraction_error:
                self._create_error_move(current_step, current_page_title, extraction_error, tool_call_request)
                self.state.status = GameStatus.LOST_INVALID_MOVE
                return True
            
            # Validate the link exists on current page
            link_error = self._validate_link(target_page, tool_call_request)
            if link_error:
                self._create_error_move(current_step, current_page_title, link_error, tool_call_request)
                self.state.status = GameStatus.LOST_INVALID_MOVE
                return True
            
            # Attempt navigation
            nav_result = await self._attempt_navigation(target_page)
            if not nav_result.is_success:
                nav_error = GameError(
                    type=ErrorType.APP_NAVIGATION_ERROR,
                    message=f"Navigation failed: {nav_result.error_message}",
                    metadata={"target_page": target_page, "nav_error": nav_result.error_message}
                )
                self._create_error_move(current_step, current_page_title, nav_error, tool_call_request)
                self.state.status = GameStatus.ERROR  # Navigation failures are system errors
                return True
            
            # Success! Create successful move and update game state
            return self._handle_successful_move(current_step, current_page_title, nav_result, tool_call_request)
            
        except Exception as e:
            return self._handle_unexpected_exception(e, current_step, current_page_title, locals().get('tool_call_request'))

    def _check_critical_errors(self) -> Optional[str]:
        """Check for critical errors that prevent any move attempt."""
        if not self.language_model:
            return "Language model not initialized"
        
        nav_capability = self.capability_registry.get_navigation_capability()
        if not nav_capability:
            return "Navigation capability not available"
        
        return None

    async def _get_model_response(self):
        """Get response from language model with proper error handling."""
        try:
            return await self.language_model.generate_response(
                tools=self.available_tools,
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
        
        # Check if tool exists
        tool_definition = next((t for t in self.available_tools if t.name == tool_call_request.tool_name), None)
        if not tool_definition:
            return GameError(
                type=ErrorType.MODEL_INVALID_TOOL,
                message=f"Model requested unavailable tool: {tool_call_request.tool_name}",
                metadata={
                    "requested_tool": tool_call_request.tool_name,
                    "available_tools": [t.name for t in self.available_tools]
                }
            )
        
        return None

    def _extract_target_page(self, tool_call_request) -> tuple[Optional[str], Optional[GameError]]:
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
            # Special case: check if model is trying to go to target page directly
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

    async def _attempt_navigation(self, target_page: str):
        """Attempt navigation using the navigation capability."""
        nav_capability = self.capability_registry.get_navigation_capability()
        return await nav_capability.navigate_to_page(target_page)

    def _handle_successful_move(self, step: int, from_page: str, nav_result, tool_call_request) -> bool:
        """Handle a successful move and update game state."""
        # Update current page
        self.state.current_page = nav_result.page
        
        # Create successful move record
        move = Move(
            step=step,
            from_page_title=from_page,
            to_page_title=nav_result.page.title,
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
        
        logging.info(f"Game {self.state.game_id} Step {step}: '{from_page}' -> '{nav_result.page.title}'")
        
        # Check win condition
        if nav_result.page.title == self.state.config.target_page_title:
            self.state.status = GameStatus.WON
            self.state.error_message = "Target page reached!"
            logging.info(f"Game {self.state.game_id}: Won! Reached target '{nav_result.page.title}' in {self.state.steps} steps.")
            return True
        
        # Check max steps
        if self.state.steps >= self.state.config.max_steps:
            self.state.status = GameStatus.LOST_MAX_STEPS
            self.state.error_message = "Maximum turns reached"
            logging.info(f"Game {self.state.game_id}: Lost - Max turns ({self.state.config.max_steps}) reached.")
            return True
        
        return False  # Game continues

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
        
        logging.warning(f"Game {self.state.game_id} Step {step}: Error - {error.message}")

    def _handle_unexpected_exception(self, exception: Exception, step: int, from_page: str, tool_call_request) -> bool:
        """Handle unexpected exceptions with proper categorization."""
        exception_str = str(exception)
        
        # Categorize based on exception content
        if exception_str.startswith("PROVIDER_RATE_LIMIT:"):
            error_type = ErrorType.PROVIDER_RATE_LIMIT
            actual_error = exception_str.replace("PROVIDER_RATE_LIMIT: ", "")
        elif exception_str.startswith("PROVIDER_TIMEOUT:"):
            error_type = ErrorType.PROVIDER_TIMEOUT
            actual_error = exception_str.replace("PROVIDER_TIMEOUT: ", "")
        elif exception_str.startswith("PROVIDER_API_ERROR:"):
            error_type = ErrorType.PROVIDER_API_ERROR
            actual_error = exception_str.replace("PROVIDER_API_ERROR: ", "")
        elif exception_str.startswith("MODEL_GENERATION_ERROR:"):
            error_type = ErrorType.MODEL_GENERATION_ERROR
            actual_error = exception_str.replace("MODEL_GENERATION_ERROR: ", "")
        else:
            error_type = ErrorType.APP_UNKNOWN_ERROR
            actual_error = exception_str
        
        error = GameError(
            type=error_type,
            message=f"Unexpected error: {actual_error}",
            metadata={
                "exception_type": type(exception).__name__,
                "step": step,
                "has_tool_call_request": bool(tool_call_request)
            }
        )
        
        if tool_call_request:
            # We had a model response, so create a Move
            self._create_error_move(step, from_page, error, tool_call_request)
        else:
            # No model response, just update game state
            self.state.error_message = error.message
        
        self.state.status = GameStatus.ERROR
        logging.error(f"Game {self.state.game_id}: {error.message}", exc_info=True)
        return True
