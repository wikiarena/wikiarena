import random
import asyncio
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

from mcp.types import Tool # Assuming Tool is available at this path
from wiki_arena.models import GameState, MoveMetrics, ModelConfig
from .language_model import LanguageModel, ToolCall
from .navigate_tool import NAVIGATE_TOOL


class RandomModel(LanguageModel):
    """
    A language model that randomly selects a link from the current page.
    """

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)
        # No specific settings needed for RandomModel yet

    async def generate_response(
        self,
        tools: List[Tool],  # Parameter kept for compatibility but not used
        game_state: GameState,
    ) -> ToolCall:
        """
        Generates a response by randomly selecting a link.
        """

        start_time = time.time()
        await asyncio.sleep(1.0)
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

        if not game_state.current_page.links:
            return ToolCall(
                model_text_response="No links available on the current page.",
                tool_name=None,
                tool_arguments=None,
                metrics=metrics
            )

        selected_link = random.choice(game_state.current_page.links)
        
        # Use the correct parameter name from the hardcoded tool definition
        return ToolCall(
            model_text_response=f"Randomly selected link: {selected_link}",
            tool_name=NAVIGATE_TOOL.name,
            tool_arguments={"page": selected_link},  # Using "page" as defined in NAVIGATE_TOOL
            metrics=metrics
        )

    async def _format_tools_for_provider(self, tools: Optional[List[Tool]] = None) -> Any:
        """
        RandomModel does not need to format tools for a specific provider.
        """
        return [NAVIGATE_TOOL.to_mcp_tool_format()] 