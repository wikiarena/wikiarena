import random
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

from mcp.types import Tool # Assuming Tool is available at this path
from wiki_arena.models import GameState, MoveMetrics, ModelConfig
from .language_model import LanguageModel, ToolCall


class RandomModel(LanguageModel):
    """
    A language model that randomly selects a link from the current page
    if the 'navigate' tool is available.
    """
    TARGET_TOOL_NAME = "navigate"

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)
        # No specific settings needed for RandomModel yet

    async def generate_response(
        self,
        tools: List[Tool],
        game_state: GameState,
    ) -> ToolCall:
        """
        Generates a response by randomly selecting a link.
        """

        # TODO(hunter): add a random delay here
        start_time = time.time()
        time.sleep(1.0)
        end_time = time.time()

        # Create zero metrics since this is not a real API call
        metrics = MoveMetrics(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            estimated_cost_usd=0.0,
            response_time_ms=end_time - start_time,
            request_timestamp=datetime.now()
        )
        
        target_tool_present = any(tool.name == self.TARGET_TOOL_NAME for tool in tools)

        if not target_tool_present:
            # This case should ideally not happen if the game is designed
            # for this tool, or we need a fallback (e.g., error or no-op).
            # For now, let's assume the game expects this tool.
            # Consider raising an error or returning a specific ToolCall
            # indicating no valid action could be taken.
            return ToolCall(
                model_text_response=f"Tool '{self.TARGET_TOOL_NAME}' not available.",
                tool_name=None,
                tool_arguments=None,
                metrics=metrics
            )

        if not game_state.current_page.links:
            return ToolCall(
                model_text_response="No links available on the current page.",
                tool_name=None,
                tool_arguments=None,
                metrics=metrics
            )

        selected_link = random.choice(game_state.current_page.links)
        
        # The tool expects 'page_title' as an argument based on typical usage,
        # ensure this matches the actual tool definition provided by MCP server.
        return ToolCall(
            model_text_response=f"Randomly selected link: {selected_link}",
            tool_name=self.TARGET_TOOL_NAME,
            tool_arguments={"page_title": selected_link},
            metrics=metrics
        )

    async def _format_tools_for_provider(self, tools: List[Tool]) -> Any:
        """
        RandomModel does not need to format tools for a specific provider.
        """
        return tools 