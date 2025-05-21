import random
import logging
from datetime import datetime
from typing import Optional, List

from wiki_arena.data_models.game_models import (
    GameConfig,
    GameState,
    GameStatus,
    Page,
    Move
)
from wiki_arena.mcp_client.client import MCPClient
from mcp.types import Tool, CallToolResult, TextContent

from wiki_arena.language_models.language_model import LanguageModel, ToolCall
from wiki_arena.language_models.random_model import RandomModel
from wiki_arena.language_models.anthropic_model import AnthropicModel
from wiki_arena.language_models.openai_model import OpenAIModel

class GameManager:
    def __init__(self, mcp_client: MCPClient):
        """Initialize the game manager with an MCP client."""
        self.mcp_client = mcp_client
        self.state: Optional[GameState] = None
        self.language_model: Optional[LanguageModel] = None
        self.available_tools: List[Tool] = []
        # TODO(hunter): I know start game logic shouldn't be in init but I want to know why

    # TODO(hunter): maybe we make a dict func that maps tool names to result processing logic
    async def _process_tool_call_result(self, tool_result: CallToolResult, called_tool_name: str, called_tool_args: dict) -> Optional[Page]:
        """Processes the result of a tool call, creating a Page object or handling errors."""
        
        # Determine the page title from the arguments of the tool that was called.
        # This part needs to be adaptable if we support multiple page-fetching tools with different arg names.
        # For now, we hardcode the knowledge for "navigate_to_page".
        page_title_for_page_object: Optional[str] = None
        if called_tool_name == "navigate_to_page":
            page_title_for_page_object = called_tool_args.get("page_title")
        # TODO(hunter): Add logic here for other tools if they are introduced and create Pages
        # For example:
        # elif called_tool_name == "get_another_page_tool":
        #     page_title_for_page_object = called_tool_args.get("document_id")

        if not page_title_for_page_object:
            logging.error(f"Could not determine page identifier from tool '{called_tool_name}' with args {called_tool_args} for creating a Page object.")
            return None

        if tool_result.isError:
            error_message = f"Tool call for '{called_tool_name}' with args {called_tool_args} (targeting '{page_title_for_page_object}') resulted in an error."
            if tool_result.content and isinstance(tool_result.content[0], TextContent):
                error_message += f" Server message: {tool_result.content[0].text}"
            else:
                error_message += f" Raw error content: {tool_result.content}"
            logging.error(error_message)
            return None

        if not tool_result.content or not isinstance(tool_result.content[0], TextContent):
            logging.error(f"Tool call for '{called_tool_name}' (targeting '{page_title_for_page_object}') returned no content or unexpected content format.")
            return None
        
        links_text = tool_result.content[0].text
        page_links = links_text.split("\\n") if links_text else [] # TODO(hunter): make this configurable for the tool, or part of the tool definition
        
        return Page(
            title=page_title_for_page_object, # Use the extracted title
            url=f"https://en.wikipedia.org/wiki/{page_title_for_page_object.replace(' ', '_')}",
            text=links_text,
            links=page_links
        )

    async def start_game(self, config: GameConfig) -> GameState:
        """Start a new game with the given configuration."""
        self.state = GameState(
            game_id=f"game_{int(datetime.now().timestamp())}_{config.model_provider}", # TODO(hunter): make this more robust, e.g. lookup
            config=config,
            status=GameStatus.NOT_STARTED,
            error_message=None # Initialize error_message
        )

        MODEL_PROVIDER_MAP = {
            "random": RandomModel,
            "anthropic": AnthropicModel,
            "openai": OpenAIModel,
        }

        # Initialize Language Model based on config
        model_provider_name = config.model_provider.lower() # Normalize to lowercase
        if model_provider_name in MODEL_PROVIDER_MAP:
            model_class = MODEL_PROVIDER_MAP[model_provider_name]
            self.language_model = model_class(config.model_settings)
            logging.info(f"Using {model_class.__name__} for link selection.")
        else:
            logging.error(f"Unsupported model provider: {config.model_provider}")
            raise ValueError(f"Unsupported model provider: {config.model_provider}")
        
        if not self.language_model: # Should be caught by else above, but as a safeguard
            logging.error(f"Language model could not be initialized for {config.model_provider}.")
            self.state.status = GameStatus.ERROR
            self.state.error_message = "Language model initialization failed."
            return self.state

        try:
            # Discover available tools from MCP server
            # TODO(hunter): we should probably cache these tools at the application level
            # rather than per game, or at least offer that option.
            # For now, fetching them at the start of each game.
            list_tools_result = await self.mcp_client.list_tools()
            self.available_tools = list_tools_result.tools
            if not self.available_tools:
                logging.warning("No tools discovered from MCP server. The game might not function correctly if tools are expected.")
            else:
                logging.info(f"Discovered {len(self.available_tools)} tools from MCP server.")

            tool_result = await self.mcp_client.call_tool(
                "navigate_to_page",
                {"page_title": config.start_page_title}
            )
            
            initial_page = await self._process_tool_call_result(tool_result, "navigate_to_page", {"page_title": config.start_page_title})
            if not initial_page:
                self.state.status = GameStatus.ERROR
                self.state.error_message = f"Failed to initialize start page '{config.start_page_title}'."
                logging.error(self.state.error_message)
                return self.state

            self.state.current_page = initial_page
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

        current_page_title = self.state.current_page.title
        current_step_for_move = self.state.steps + 1

        if not self.language_model:
            msg = "Language model not initialized"
            logging.error(f"Game {self.state.game_id}: Critical error - {msg} for turn {current_step_for_move}.")
            self.state.status = GameStatus.ERROR
            self.state.error_message = msg
            # No move object here as it's a fundamental setup issue for the turn.
            return True # Game over

        tool_call_request: Optional[ToolCall] = None
        try:
            tool_call_request = await self.language_model.generate_response(
                tools=self.available_tools,
                game_state=self.state
            )
        except Exception as e:
            msg = f"Language model error: {e}"
            logging.error(f"Game {self.state.game_id}: {msg}", exc_info=True)
            self.state.status = GameStatus.ERROR
            self.state.error_message = msg
            move = Move(
                step=current_step_for_move, from_page_title=current_page_title, to_page_title=None, # Error, no page reached
                timestamp=datetime.now(), model_response=None, tool_call_attempt=None, tool_call_result=None, error=msg
            )
            self.state.move_history.append(move)
            return True # Game over

        model_text_resp = tool_call_request.model_text_response if tool_call_request else None

        if not tool_call_request or not tool_call_request.tool_name:
            msg = f"Language model did not select a valid action. Response: {model_text_resp or 'N/A'}"
            logging.warning(f"Game {self.state.game_id}: {msg}")
            self.state.status = GameStatus.LOST_INVALID_MOVE
            self.state.error_message = msg
            move = Move(
                step=current_step_for_move, from_page_title=current_page_title, to_page_title=None, # Error, no page reached
                timestamp=datetime.now(), model_response=model_text_resp,
                tool_call_attempt=None, tool_call_result=None, error=msg
            )
            self.state.move_history.append(move)
            return True # Game over

        chosen_tool_name = tool_call_request.tool_name
        chosen_tool_args = tool_call_request.tool_arguments or {}
        
        tool_definition = next((t for t in self.available_tools if t.name == chosen_tool_name), None)
        if not tool_definition:
            msg = f"Model requested an unavailable tool: {chosen_tool_name}"
            logging.error(f"Game {self.state.game_id}: {msg}")
            self.state.status = GameStatus.ERROR
            self.state.error_message = msg
            move = Move(
                step=current_step_for_move, from_page_title=current_page_title, to_page_title=None, # Error, no page reached
                timestamp=datetime.now(), model_response=model_text_resp,
                tool_call_attempt={"tool_name": chosen_tool_name, "arguments": chosen_tool_args},
                tool_call_result=None, error=msg
            )
            self.state.move_history.append(move)
            return True # Game over
        
        if chosen_tool_name == "navigate_to_page":
            target_page_title_from_lm = chosen_tool_args.get("page_title")
            if not target_page_title_from_lm:
                msg = f"Tool '{chosen_tool_name}' called without 'page_title' argument. Args: {chosen_tool_args}"
                logging.warning(f"Game {self.state.game_id}: {msg}")
                self.state.status = GameStatus.LOST_INVALID_MOVE
                self.state.error_message = msg
                move = Move(
                    step=current_step_for_move, from_page_title=current_page_title, to_page_title=None, # Error, no page reached
                    timestamp=datetime.now(), model_response=model_text_resp,
                    tool_call_attempt={"tool_name": chosen_tool_name, "arguments": chosen_tool_args},
                    tool_call_result=None, error=msg
                )
                self.state.move_history.append(move)
                return True # Game over

            if target_page_title_from_lm not in self.state.current_page.links:
                msg = f"Invalid navigation: Page '{target_page_title_from_lm}' is not in the available links of '{current_page_title}'."
                logging.warning(f"Game {self.state.game_id} Turn {current_step_for_move}: {msg} Available links: {self.state.current_page.links}")
                self.state.status = GameStatus.LOST_INVALID_MOVE
                self.state.error_message = msg
                move = Move(
                    step=current_step_for_move, from_page_title=current_page_title, to_page_title=None, # Error, invalid link, no page reached
                    timestamp=datetime.now(), model_response=model_text_resp,
                    tool_call_attempt={"tool_name": chosen_tool_name, "arguments": chosen_tool_args},
                    tool_call_result=None, error=msg
                )
                self.state.move_history.append(move)
                return True # Game over

        logging.info(f"Game {self.state.game_id} Turn {current_step_for_move}: From '{current_page_title}', model chose tool '{chosen_tool_name}' with args {chosen_tool_args}. Model text: {model_text_resp}")
        
        try:
            tool_result: CallToolResult = await self.mcp_client.call_tool(
                tool_name=chosen_tool_name,
                arguments=chosen_tool_args
            )

            next_page_object = await self._process_tool_call_result(
                tool_result,
                called_tool_name=chosen_tool_name, 
                called_tool_args=chosen_tool_args
            )
            
            move_timestamp = datetime.now() # Timestamp after processing attempt

            if not next_page_object:
                error_detail = "Unknown error during tool call processing."
                if tool_result.isError and tool_result.content and isinstance(tool_result.content[0], TextContent):
                    error_detail = tool_result.content[0].text
                elif tool_result.isError:
                    error_detail = f"Tool returned an error. Raw content: {tool_result.content}"
                
                msg = f"Failed to process tool call result for '{chosen_tool_name}' with args {chosen_tool_args}. Server message: {error_detail}"
                
                move = Move(
                    step=current_step_for_move,
                    from_page_title=current_page_title,
                    to_page_title=None, # Error in processing, no page reached
                    timestamp=move_timestamp,
                    model_response=model_text_resp,
                    tool_call_attempt={"tool_name": chosen_tool_name, "arguments": chosen_tool_args},
                    tool_call_result=tool_result, # Include the raw tool result
                    error=msg
                )
                self.state.move_history.append(move)
                self.state.status = GameStatus.LOST_INVALID_MOVE
                self.state.error_message = msg
                logging.warning(f"Game {self.state.game_id}: {msg}")
                return True # Game over
            
            # Success: page processed successfully
            self.state.current_page = next_page_object
            
            move = Move(
                step=current_step_for_move,
                from_page_title=current_page_title,
                to_page_title=next_page_object.title, # Actual title from processed page
                timestamp=move_timestamp,
                model_response=model_text_resp,
                tool_call_attempt={"tool_name": chosen_tool_name, "arguments": chosen_tool_args},
                tool_call_result=tool_result,
                error=None
            )
            self.state.move_history.append(move)
            self.state.steps += 1 # Increment steps only on successful move processing and page update
            
            if next_page_object.title == self.state.config.target_page_title:
                self.state.status = GameStatus.WON
                self.state.error_message = "Target page reached!" # Success message
                logging.info(f"Game {self.state.game_id}: Won! Reached target '{next_page_object.title}' in {self.state.steps} steps.")
                return True # Game over
                
            if self.state.steps >= self.state.config.max_steps: 
                self.state.status = GameStatus.LOST_MAX_STEPS
                self.state.error_message = "Maximum turns reached"
                logging.info(f"Game {self.state.game_id}: Lost - Max turns ({self.state.config.max_steps}) reached.")
                return True # Game over
                
            return False # Game continues
            
        except Exception as e:
            msg = f"Unhandled exception during turn processing (tool call or result handling): {e}"
            logging.error(f"Game {self.state.game_id}: {msg}", exc_info=True)
            self.state.status = GameStatus.ERROR
            self.state.error_message = msg
            
            # Create a Move object for this exception. 
            # tool_result might not be defined if exception was in call_tool itself.
            # We pass None for tool_call_result in this generic exception case for safety.
            move_for_exception = Move(
                step=current_step_for_move, 
                from_page_title=current_page_title, 
                to_page_title=None, # Error, no page reached
                timestamp=datetime.now(), # Timestamp of the exception handling
                model_response=model_text_resp,
                tool_call_attempt={"tool_name": chosen_tool_name, "arguments": chosen_tool_args},
                tool_call_result=None, # tool_result might not be available here
                error=msg
            )
            self.state.move_history.append(move_for_exception)
            return True # Game over
