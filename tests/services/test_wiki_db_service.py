import pytest
import pytest_asyncio

from backend.services.wiki_db_service import wiki_db, WikiGraphDatabase
from common.utils.wiki_helpers import get_readable_page_title, get_sanitized_page_title

# Database path for tests - ensure this path is correct relative to where tests are run
# Or configure via environment variable / conftest.py
TEST_DB_PATH = "database/sdow.sqlite"

@pytest_asyncio.fixture(scope="module")
async def db_service():
    """Fixture to provide an instance of WikiGraphDatabase for the test module."""
    # This ensures we use the same DB path as the main service if it's not default
    # Forcing the path here for consistency in tests
    service = WikiGraphDatabase(db_path=TEST_DB_PATH)
    # No explicit initialize/close needed for aiosqlite connections used per-method
    # If there were a shared connection pool managed by the service, we'd init/close here.
    return service

@pytest.mark.asyncio
async def test_get_page_id_existing_exact(db_service: WikiGraphDatabase):
    """Test fetching ID for an existing page with exact title match."""
    page_title = "Philosophy" 
    page_id = await db_service.get_page_id(page_title)
    assert page_id is not None
    assert isinstance(page_id, int)
    # We could assert a specific ID if known and stable in the test DB
    # e.g. assert page_id == EXPECTED_PHILOSOPHY_ID

@pytest.mark.asyncio
async def test_get_page_id_existing_case_variation(db_service: WikiGraphDatabase):
    """Test fetching ID for an existing page with case variation."""
    page_title_db_case = "Philosophy" # Assuming this is how it's mostly stored
    page_title_test = "philosophy"
    
    page_id_db_case = await db_service.get_page_id(page_title_db_case)
    page_id_test_case = await db_service.get_page_id(page_title_test)
    
    assert page_id_db_case is not None
    assert page_id_test_case is not None
    assert page_id_test_case == page_id_db_case

@pytest.mark.asyncio
async def test_get_page_id_redirect(db_service: WikiGraphDatabase):
    """Test fetching ID for a page title that is a redirect."""
    redirect_title = "USA" # Likely redirects to "United States"
    expected_target_title = "United States"
    
    redirect_page_id = await db_service.get_page_id(redirect_title)
    target_page_id = await db_service.get_page_id(expected_target_title)
    
    assert redirect_page_id is not None
    assert target_page_id is not None
    assert redirect_page_id == target_page_id, f"Expected '{redirect_title}' to redirect to the same ID as '{expected_target_title}'"

@pytest.mark.asyncio
async def test_get_page_id_non_existent(db_service: WikiGraphDatabase):
    """Test fetching ID for a non-existent page."""
    page_title = "ThisIsSurelyANonExistentPage12345XYZ"
    page_id = await db_service.get_page_id(page_title)
    assert page_id is None

@pytest.mark.asyncio
async def test_get_page_title_existing(db_service: WikiGraphDatabase):
    """Test fetching title for an existing page ID."""
    page_title_known = "Banana"
    page_id = await db_service.get_page_id(page_title_known) # Get ID first
    assert page_id is not None, f"Setup for test_get_page_title_existing failed: '{page_title_known}' not found."
    
    fetched_title = await db_service.get_page_title(page_id)
    assert fetched_title is not None
    assert fetched_title == page_title_known # sdow titles might have specific casing

@pytest.mark.asyncio
async def test_get_page_title_non_existent_id(db_service: WikiGraphDatabase):
    """Test fetching title for a non-existent page ID."""
    non_existent_id = 999999999 # An ID that's extremely unlikely to exist
    fetched_title = await db_service.get_page_title(non_existent_id)
    assert fetched_title is None

@pytest.mark.asyncio
async def test_page_exists_true(db_service: WikiGraphDatabase):
    """Test page_exists for a page that exists."""
    assert await db_service.page_exists("Philosophy") is True

@pytest.mark.asyncio
async def test_page_exists_false(db_service: WikiGraphDatabase):
    """Test page_exists for a page that does not exist."""
    assert await db_service.page_exists("ThisIsSurelyANonExistentPage12345XYZ") is False

@pytest.mark.asyncio
async def test_page_exists_redirect(db_service: WikiGraphDatabase):
    """Test page_exists for a page that is a redirect (should resolve and return True)."""
    assert await db_service.page_exists("USA") is True

# More tests to be added for:
# - get_outgoing_links
# - get_incoming_links
# - batch_get_page_titles
# - batch_get_page_ids
# - get_database_stats
# - fetch_outgoing_links_count
# - fetch_incoming_links_count
# - Edge cases for title sanitization if not covered by get_page_id tests already.

# Example for checking links (requires knowing actual link structure for a test page)
# @pytest.mark.asyncio
# async def test_get_outgoing_links_philosophy(db_service: WikiGraphDatabase):
#     philosophy_id = await db_service.get_page_id("Philosophy")
#     assert philosophy_id is not None
#     links = await db_service.get_outgoing_links(philosophy_id)
#     assert isinstance(links, list)
#     assert len(links) > 0 # Philosophy should have many links
#     for link_id in links:
#         assert isinstance(link_id, int)
#     # We could assert specific known linked IDs if the DB is static for tests
#     # e.g. PLATO_ID = await db_service.get_page_id("Plato")
#     # assert PLATO_ID in links

# @pytest.mark.asyncio
# async def test_get_database_stats(db_service: WikiGraphDatabase):
#     page_count, link_count = await db_service.get_database_stats()
#     assert isinstance(page_count, int)
#     assert isinstance(link_count, int)
#     assert page_count > 10000 # Expect a significant number of pages
#     assert link_count > 100000 # Expect a significant number of links

# To run these tests, navigate to your project root in the terminal and run:
# pytest
# or specifically:
# pytest tests/services/test_wiki_db_service.py 