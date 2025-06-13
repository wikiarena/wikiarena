import pytest
import asyncio
from wiki_arena.wikipedia.live_service import LiveWikiService
from wiki_arena.wikipedia.task_selector import (
    WikipediaTaskSelector,
    get_random_task,
    get_random_task_async,
)
from wiki_arena.models import Task

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration

# A set of known forbidden prefixes for quick checks
FORBIDDEN_PREFIXES = {
    "Tag:", "Category:", "File:", "Template:", "Help:",
    "Wikipedia:", "User:", "User talk:", "Template talk:",
    "Category talk:", "Portal:", "Project:", "MediaWiki:",
    "Module:", "Draft:",
}

@pytest.fixture(scope="module")
def service() -> LiveWikiService:
    """Fixture to provide a LiveWikiService instance for validation."""
    return LiveWikiService(language="en")

@pytest.fixture
def selector(service: LiveWikiService) -> WikipediaTaskSelector:
    """Fixture to provide a fresh WikipediaTaskSelector instance for each test."""
    return WikipediaTaskSelector(live_wiki_service=service)

async def validate_task(task: Task, service: LiveWikiService):
    """Reusable validation logic for a Task object."""
    assert task is not None, "Task should not be None"
    assert isinstance(task, Task), f"Expected Task, got {type(task)}"
    assert task.start_page_title != task.target_page_title, "Start and target pages must be different"

    # Use the live service to verify the selector's choices
    assert await service.has_outgoing_links(task.start_page_title) is True, f"Start page '{task.start_page_title}' should have outgoing links"
    assert await service.has_incoming_links(task.target_page_title) is True, f"Target page '{task.target_page_title}' should have incoming links"

    # Check for forbidden prefixes
    assert not any(task.start_page_title.startswith(p) for p in FORBIDDEN_PREFIXES), f"Start page '{task.start_page_title}' has a forbidden prefix"
    assert not any(task.target_page_title.startswith(p) for p in FORBIDDEN_PREFIXES), f"Target page '{task.target_page_title}' has a forbidden prefix"

@pytest.mark.asyncio
async def test_select_task_async_returns_valid_task(selector: WikipediaTaskSelector, service: LiveWikiService):
    """
    Tests the core logic of WikipediaTaskSelector.select_task_async()
    to ensure it returns a fully validated, playable task.
    """
    task = await selector.select_task_async()
    await validate_task(task, service)

@pytest.mark.asyncio
async def test_get_random_task_async_returns_valid_task(service: LiveWikiService):
    """
    Tests the async convenience function to ensure it returns a
    fully validated, playable task.
    """
    task = await get_random_task_async()
    await validate_task(task, service)

def test_get_random_task_returns_valid_task(service: LiveWikiService):
    """
    Tests the sync convenience function to ensure it returns a
    fully validated, playable task.
    """
    task = get_random_task()
    # We must run our async validation function in an event loop
    asyncio.run(validate_task(task, service)) 