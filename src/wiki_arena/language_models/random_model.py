import asyncio
import random
import time
import uuid
import ast
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from wiki_arena.models import (
    AssistantMessage,
    AssistantToolCall,
    ContextMessage,
    ModelCallMetrics,
    ModelConfig,
    GameState,
)
from .language_model import LanguageModel


class RandomModel(LanguageModel):
    """
    A language model that randomly selects a link from the current page.
    """

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)

    def _calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        """RandomModel has no cost."""
        return 0.0

    def _format_tools(self, mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """No-op for RandomModel."""
        return mcp_tools

    def _format_context(self, context: List[ContextMessage]) -> Any:
        """No-op for RandomModel."""
        return None

    # TODO(hunter): I completely broke this haha. we should probably just pass in game state too so I can can cheap out on context
    async def generate_response(
        self,
        tools: List[Dict[str, Any]],
        context: List[ContextMessage],
        game_state: GameState,
    ) -> AssistantMessage:
        """Generates a response by randomly selecting a link from the context."""
        start_time = time.time()
        await asyncio.sleep(1.0)

        # 2. Create zero-cost metrics since this is not a real API call
        metrics = ModelCallMetrics(
            response_time_ms=(time.time() - start_time) * 1000,
            request_timestamp=datetime.now()
        )

        # 3. If no links are available, return a message with no tool call
        if not game_state.current_page.links:
            return AssistantMessage(
                content="No links available on the current page to choose from.",
                metrics=metrics
            )

        # Find the navigate tool (assuming it exists)
        navigate_tool = None
        for tool in tools:
            if tool["name"] == "navigate":
                navigate_tool = tool
                break
        
        if not navigate_tool:
            return AssistantMessage(
                content="No navigate tool available.",
                metrics=metrics
            )
        
        # 4. Randomly select a link and create a tool call
        selected_link = random.choice(game_state.current_page.links)
        tool_call = AssistantToolCall(
            id=f"tool_{uuid.uuid4().hex[:10]}",
            name="navigate",
            arguments={"to_page_title": selected_link}
        )
        # 5. Return the AssistantMessage
        return AssistantMessage(
            content=f"Randomly selected link: {selected_link}",
            tool_calls=[tool_call],
            metrics=metrics
        )