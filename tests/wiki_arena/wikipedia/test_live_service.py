import pytest
from wiki_arena.wikipedia.live_service import LiveWikiService
from wiki_arena.models import Page

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration

@pytest.fixture(scope="module")
def service() -> LiveWikiService:
    """Fixture to provide a LiveWikiService instance for tests."""
    return LiveWikiService(language="en")

@pytest.mark.asyncio
async def test_get_random_pages(service: LiveWikiService):
    """Test fetching a list of random pages."""
    # 1. Input/Output Pair
    count = 5
    
    # 2. Test Steps
    pages = await service.get_random_pages(count=count)
    
    # 3. Assertions
    assert isinstance(pages, list)
    assert len(pages) == count
    for title in pages:
        assert isinstance(title, str)
        assert len(title) > 0

@pytest.mark.asyncio
async def test_random_pages_has_outgoing_links_skip_if_all_have_links(service: LiveWikiService):
    """
    Test checking for outgoing links by fetching a random batch and
    ensuring we can find at least one page with links and one without.
    """
    count = 20
    random_pages = await service.get_random_pages(count=count)
    results = [await service.has_outgoing_links(p) for p in random_pages]
    
    found_true = any(results)
    found_false = not all(results)

    if not found_false:
        pytest.skip(f"Could not find a page with no outgoing links in a random batch of {count}.")
        
    assert found_true and found_false, "Expected to find pages with and without outgoing links."

@pytest.mark.asyncio
async def test_random_pages_has_incoming_links_skip_if_all_have_links(service: LiveWikiService):
    """
    Test checking for incoming links by fetching a random batch and
    ensuring we can find at least one page with links and one without.
    """
    count = 20
    random_pages = await service.get_random_pages(count=count)
    results = [await service.has_incoming_links(p) for p in random_pages]
    
    found_true = any(results)
    found_false = not all(results)

    if not found_false:
        pytest.skip(f"Could not find a page with no incoming links in a random batch of {count}.")
        
    assert found_true and found_false, "Expected to find pages with and without incoming links."

@pytest.mark.asyncio
async def test_get_page_standard(service: LiveWikiService):
    """Test fetching a standard page."""
    page = await service.get_page("Philosophy")
    
    assert isinstance(page, Page)
    assert page.title == "Philosophy"
    assert "https://en.wikipedia.org/wiki/Philosophy" in page.url
    assert isinstance(page.links, list)
    assert len(page.links) > 50  # Philosophy should have many links

@pytest.mark.asyncio
async def test_get_page_redirect(service: LiveWikiService):
    """Test that fetching a page that redirects returns the resolved page."""
    page = await service.get_page("U.S.A.")
    
    assert isinstance(page, Page)
    assert page.title == "United States"
    assert "https://en.wikipedia.org/wiki/United_States" in page.url

@pytest.mark.asyncio
async def test_get_page_not_found_raises_error(service: LiveWikiService):
    """Test that fetching a non-existent page raises a ValueError."""
    with pytest.raises(ValueError, match="Page does not exist"):
        await service.get_page("PageThatDoesNotExist_ABC123XYZ") 