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
from mcp.types import CallToolResult, TextContent

class GameManager:
    def __init__(self, mcp_client: MCPClient):
        """Initialize the game manager with an MCP client."""
        self.mcp_client = mcp_client
        self.state: Optional[GameState] = None

    async def _process_tool_call_result(self, tool_result: CallToolResult, page_title: str) -> Optional[Page]:
        """Processes the result of a tool call, creating a Page object or handling errors."""
        if tool_result.isError: # TODO(hunter): let the model retry once or twice and call another page title
            # TODO(hunter): also simplify and just assume that ToolCallResult.content always exists and has a TextContent
            error_message = f"Tool call for page '{page_title}' resulted in an error."
            if tool_result.content and isinstance(tool_result.content[0], TextContent):
                error_message += f" Server message: {tool_result.content[0].text}"
            else:
                error_message += f" Raw error content: {tool_result.content}"
            logging.error(error_message)
            return None

        if not tool_result.content or not isinstance(tool_result.content[0], TextContent):
            logging.error(f"Tool call for page '{page_title}' returned no content or unexpected content format.")
            return None
        
        links_text = tool_result.content[0].text
        page_links = links_text.split("\\n") if links_text else []
        
        return Page(
            title=page_title,
            url=f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}", # ensure spaces are handled for URLs
            links=page_links
        )

    async def start_game(self, config: GameConfig) -> GameState:
        """Start a new game with the given configuration."""
        self.state = GameState(
            game_id=f"game_{int(datetime.now().timestamp())}", # TODO(hunter): parallel games start at same timestamp so include model too?
            config=config,
            status=GameStatus.NOT_STARTED
        )

        try:
            tool_result = await self.mcp_client.call_tool(
                "get_wikipedia_page_links_titles",
                {"page_title": config.start_page_title}
            )
            
            initial_page = await self._process_tool_call_result(tool_result, config.start_page_title)
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
        """Play a single turn of the game using random selection."""
        if not self.state or self.state.status != GameStatus.IN_PROGRESS:
            # This case should ideally not be reached if main loop checks status
            logging.warning("play_turn called with no active game or game not in progress.")
            if self.state:
                return self._create_game_result(f"Game error: play_turn called when status was {self.state.status.value}")
            return GameResult(
                game_id="unknown", config=None, status=GameStatus.ERROR, 
                steps=0, path_taken=[], duration=0, end_timestamp=datetime.now(),
                error_message="play_turn called with no state"
            )

        current_page_title = self.state.current_page.title
        current_links = self.state.current_page.links

        if not current_links:
            self.state.status = GameStatus.LOST_INVALID_MOVE
            logging.info(f"Game {self.state.game_id}: Lost - No links on page '{current_page_title}'.")
            return self._create_game_result("No links available on current page")

        next_page_title = random.choice(current_links)
        logging.info(f"Game {self.state.game_id} Turn {self.state.steps + 1}: From '{current_page_title}', trying '{next_page_title}' randomly.")
        
        move = Move(
            step=self.state.steps + 1,
            from_page_title=current_page_title,
            to_page_title=next_page_title,
            timestamp=datetime.now(),
            model_response="Random selection",
            tool_call_attempt={"tool_name": "get_wikipedia_page_links_titles", "parameters": {"page_title": next_page_title}}
        )

        try:
            tool_result = await self.mcp_client.call_tool(
                "get_wikipedia_page_links_titles",
                {"page_title": next_page_title}
            )
            move.tool_call_result = tool_result # Store raw result for debugging/history
            
            next_page_object = await self._process_tool_call_result(tool_result, next_page_title)
            
            if not next_page_object:
                error_detail = "Unknown error during tool call processing."
                if tool_result.isError and tool_result.content and isinstance(tool_result.content[0], TextContent):
                    error_detail = tool_result.content[0].text
                elif tool_result.isError:
                    error_detail = f"Raw error content: {tool_result.content}"
                
                move.error = f"Failed to process tool call result for {next_page_title}. Server message: {error_detail}"
                self.state.move_history.append(move)
                self.state.status = GameStatus.LOST_INVALID_MOVE # Or ERROR depending on desired behavior
                logging.warning(f"Game {self.state.game_id}: Lost - Failed to retrieve/process page '{next_page_title}'. Server message: {error_detail}")
                return self._create_game_result(move.error)
            
            self.state.current_page = next_page_object
            self.state.move_history.append(move)
            self.state.steps += 1
            
            if next_page_title == self.state.config.target_page_title:
                self.state.status = GameStatus.WON
                logging.info(f"Game {self.state.game_id}: Won! Reached target '{next_page_title}' in {self.state.steps} steps.")
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
            self.state.move_history.append(move)
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
