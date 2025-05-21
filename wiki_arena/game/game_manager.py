import random
import logging
from datetime import datetime
from typing import Optional, List

from wiki_arena.data_models.game_models import (
    GameConfig,
    GameState,
    GameStatus,
    Page,
    Move,
    GameResult
)
from wiki_arena.mcp_client.client import MCPClient
from mcp.types import Tool, CallToolResult, TextContent

from wiki_arena.language_models.language_model import LanguageModel, ToolCall
from wiki_arena.language_models.random_model import RandomModel
from wiki_arena.language_models.anthropic_model import AnthropicModel
# TODO(hunter): Add other model imports here as they are created

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
        # For now, we hardcode the knowledge for "get_wikipedia_page_links_titles".
        page_title_for_page_object: Optional[str] = None
        if called_tool_name == "get_wikipedia_page_links_titles":
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
            status=GameStatus.NOT_STARTED
        )

        # Initialize Language Model based on config
        if config.model_provider == "random":
            self.language_model = RandomModel(config.model_settings)
            logging.info("Using RandomModel for link selection.")
        elif config.model_provider == "anthropic": # TODO(hunter): make this more robust, e.g. lookup
            self.language_model = AnthropicModel(config.model_settings)
            logging.info("Using AnthropicModel for link selection.")
        # Add other models here
        # elif config.model_provider == "another_model":
        #     self.language_model = AnotherModel(config.model_settings)
        else:
            logging.error(f"Unknown model_provider '{config.model_provider}' in game configuration.")
            self.state.status = GameStatus.ERROR
            self.state.error_message = f"Unknown model_provider '{config.model_provider}'"
            return self.state
        
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
                "get_wikipedia_page_links_titles",
                {"page_title": config.start_page_title}
            )
            
            initial_page = await self._process_tool_call_result(tool_result, "get_wikipedia_page_links_titles", {"page_title": config.start_page_title})
            if not initial_page:
                self.state.status = GameStatus.ERROR
                # Optionally, populate self.state.error_message or a similar field if added to GameState
                logging.error(f"Failed to initialize start page '{config.start_page_title}'.")
                return self.state

            self.state.current_page = initial_page
            self.state.status = GameStatus.IN_PROGRESS
            self.state.steps = 0 # Start at 0 steps, first move will increment it to 1
            
            logging.info(f"Game started. ID: {self.state.game_id}. Start: '{config.start_page_title}', Target: '{config.target_page_title}'")
            return self.state
            
        except Exception as e:
            logging.error(f"Unhandled exception during game start: {e}", exc_info=True)
            self.state.status = GameStatus.ERROR
            return self.state

    async def play_turn(self) -> Optional[GameResult]:
        """Play a single turn of the game using the configured language model."""
        if not self.state or self.state.status != GameStatus.IN_PROGRESS:
            logging.warning("play_turn called with no active game or game not in progress.")
            if self.state:
                return self._create_game_result(f"Game error: play_turn called when status was {self.state.status.value}")
            return GameResult(
                game_id="unknown", config=None, status=GameStatus.ERROR, 
                steps=0, path_taken=[], duration=0, end_timestamp=datetime.now(),
                error_message="play_turn called with no state"
            )

        current_page_title = self.state.current_page.title
        
        if not self.language_model:
            logging.error(f"Game {self.state.game_id}: Critical error - Language model not initialized for turn {self.state.steps + 1}.")
            self.state.status = GameStatus.ERROR
            return self._create_game_result("Language model not initialized")

        # Let the Language Model decide the next action
        try:
            # TODO(hunter): it might be better to pass the specific tool definition the LM should use
            # (e.g. "get_wikipedia_page_links_titles") rather than all available tools,
            # or let the LM decide if it wants to use a tool at all.
            # For now, we assume the LM wants to call 'get_wikipedia_page_links_titles'.
            tool_call_request: ToolCall = await self.language_model.generate_response(
                tools=self.available_tools, # Pass all discovered tools
                game_state=self.state
            )
        except Exception as e:
            logging.error(f"Game {self.state.game_id}: Error during language model response generation: {e}", exc_info=True)
            self.state.status = GameStatus.ERROR
            return self._create_game_result(f"Language model error: {e}")

        if not tool_call_request or not tool_call_request.tool_name:
            # This could happen if the LM decides not to call a tool, or an error occurs.
            # For WikiArena, we expect a tool call to select the next page.
            logging.warning(f"Game {self.state.game_id}: Language model did not request a tool call or returned an invalid request. Model response: {tool_call_request.model_text_response if tool_call_request else 'None'}")
            # TODO(hunter): what is the correct game status here? Lost? Error?
            # For now, let's assume it's an invalid move if no tool is chosen.
            self.state.status = GameStatus.LOST_INVALID_MOVE 
            return self._create_game_result(f"Language model did not select a valid action. Response: {tool_call_request.model_text_response if tool_call_request else 'N/A'}")

        # Validate the requested tool
        chosen_tool_name = tool_call_request.tool_name
        chosen_tool_args = tool_call_request.tool_arguments or {}

        # Check if the chosen tool is one of the available tools
        tool_definition: Optional[Tool] = next((t for t in self.available_tools if t.name == chosen_tool_name), None)

        if not tool_definition:
            logging.error(f"Game {self.state.game_id}: Language model requested to use tool '{chosen_tool_name}' which is not available or not discovered.")
            self.state.status = GameStatus.ERROR # Or LOST_INVALID_MOVE, depending on strictness
            return self._create_game_result(f"Model requested an unavailable tool: {chosen_tool_name}")
        
        # TODO(hunter): Add validation of arguments against tool_definition.input_schema if available and strictness is desired.
        # For now, we proceed if the tool exists.

        # For this game, we primarily expect tools that fetch new pages, like 'get_wikipedia_page_links_titles'.
        # If other tools are called, the game logic might need to handle them differently.
        # The `_process_tool_call_result` function will now rely on `chosen_tool_name` and `chosen_tool_args` to extract page title.
        # We no longer need to extract `next_page_title` here explicitly for all cases.

        logging.info(f"Game {self.state.game_id} Turn {self.state.steps + 1}: From '{current_page_title}', model chose tool '{chosen_tool_name}' with args {chosen_tool_args}. Model text: {tool_call_request.model_text_response}")
        
        move: Optional[Move] = None # Initialize move to None, will be created after tool call

        try:
            # Call the tool requested by the language model
            tool_result: CallToolResult = await self.mcp_client.call_tool(
                tool_name=chosen_tool_name,
                arguments=chosen_tool_args
            )

            # Create Move object now that tool_result is available
            move = Move(
                step=self.state.steps + 1,
                from_page_title=current_page_title,
                to_page_title="Pending processing...", # Will be updated after _process_tool_call_result
                timestamp=datetime.now(), # Timestamp for the event of tool call and processing
                model_response=tool_call_request.model_text_response,
                tool_call_attempt={
                    "tool_name": chosen_tool_name,
                    "arguments": chosen_tool_args
                },
                tool_call_result=tool_result, # Include the raw tool result
                error=None # Initialize with no error
            )
            
            next_page_object = await self._process_tool_call_result(
                tool_result,
                called_tool_name=chosen_tool_name, 
                called_tool_args=chosen_tool_args
            )
            
            if not next_page_object:
                error_detail = "Unknown error during tool call processing."
                if tool_result.isError and tool_result.content and isinstance(tool_result.content[0], TextContent):
                    error_detail = tool_result.content[0].text
                elif tool_result.isError:
                    error_detail = f"Tool returned an error. Raw content: {tool_result.content}"
                
                move.error = f"Failed to process tool call result for '{chosen_tool_name}' with args {chosen_tool_args}. Server message: {error_detail}"
                self.state.move_history.append(move)
                self.state.status = GameStatus.LOST_INVALID_MOVE # Or ERROR depending on desired behavior
                logging.warning(f"Game {self.state.game_id}: Lost due to tool processing error. Details: {move.error}")
                return self._create_game_result(move.error)
            
            self.state.current_page = next_page_object
            move.to_page_title = next_page_object.title # Update the move with the actual title
            self.state.move_history.append(move)
            self.state.steps += 1
            
            if next_page_object.title == self.state.config.target_page_title:
                self.state.status = GameStatus.WON
                logging.info(f"Game {self.state.game_id}: Won! Reached target '{next_page_object.title}' in {self.state.steps} steps.")
                return self._create_game_result("Target page reached!")
                
            if self.state.steps >= self.state.config.max_steps: # Use >= for max_steps
                self.state.status = GameStatus.LOST_MAX_STEPS
                logging.info(f"Game {self.state.game_id}: Lost - Max turns ({self.state.config.max_steps}) reached.")
                return self._create_game_result("Maximum turns reached")
                
            return None # Game continues
            
        except Exception as e:
            error_msg = f"Unhandled exception during turn: {e}"
            logging.error(error_msg, exc_info=True)
            move.error = error_msg
            self.state.status = GameStatus.ERROR
            return self._create_game_result(error_msg)

    def _create_game_result(self, message: Optional[str] = None) -> GameResult:
        """Create a game result from the current state."""
        if not self.state:
            # This should ideally not happen if called from play_turn which has state
            logging.error("_create_game_result called with no game state.")
            return GameResult(
                game_id="unknown_error_state", config=None, status=GameStatus.ERROR,
                steps=0, path_taken=[], duration=0, end_timestamp=datetime.now(),
                error_message="Critical: Game state was None when creating result."
            )
            
        end_time = datetime.now()
        duration = (end_time - self.state.start_timestamp).total_seconds()
        
        # Construct path_taken. It should include the final page if the game ended on a valid page.
        path = [hist_move.from_page_title for hist_move in self.state.move_history]
        if self.state.status == GameStatus.WON and self.state.move_history:
            path.append(self.state.move_history[-1].to_page_title)
        elif self.state.current_page and self.state.status != GameStatus.ERROR and self.state.move_history: # Avoid adding if error on first page load
            # If game ended for other reasons (max_steps, invalid_move after some successful moves)
            # The last `to_page_title` from history is the problematic one, or current_page if it's the first turn fail
            if self.state.move_history[-1].to_page_title:
                path.append(self.state.move_history[-1].to_page_title)

        error_for_result = message
        if self.state.status == GameStatus.ERROR and not error_for_result:
            error_for_result = "Game ended in an error state."
        elif self.state.status == GameStatus.LOST_INVALID_MOVE and not error_for_result:
            error_for_result = "Game lost due to an invalid move or page processing error."
        elif self.state.status == GameStatus.LOST_MAX_STEPS and not error_for_result:
            error_for_result = "Game lost due to exceeding maximum turns."
        
        return GameResult(
            game_id=self.state.game_id,
            config=self.state.config,
            status=self.state.status,
            steps=self.state.steps,
            path_taken=path,
            duration=duration,
            end_timestamp=end_time,
            error_message=error_for_result
        )
