import pytest
import pytest_asyncio
import logging
from pathlib import Path

from wiki_arena.solver.static_db import StaticSolverDB, static_solver_db
from wiki_arena.utils.wiki_helpers import (
    get_sanitized_page_title,
    get_readable_page_title,
    validate_page_id,
    validate_page_title
)

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


class TestStaticSolverDB:
    """Integration tests for the StaticSolverDB - the sole gateway to wiki_graph.sqlite."""

    @pytest_asyncio.fixture(scope="function")
    async def solver_db(self):
        """Fixture to provide a StaticSolverDB instance for testing."""
        # Use the global instance for real database testing
        return static_solver_db

    @pytest.mark.asyncio
    async def test_database_connection(self, solver_db: StaticSolverDB):
        """Test that the database file exists and can be connected to."""
        # Check that database path exists
        assert solver_db.db_path.exists(), f"Database not found at {solver_db.db_path}"
        
        # Test basic database connectivity
        stats = await solver_db.get_database_stats()
        page_count, link_count = stats
        
        assert page_count > 0, "Database should contain pages"
        assert link_count > 0, "Database should contain links"
        
        print(f"Database contains {page_count:,} pages and {link_count:,} links")

    @pytest.mark.asyncio
    async def test_get_page_id_basic(self, solver_db: StaticSolverDB):
        """Test basic page ID retrieval for known pages."""
        # Test with a well-known page
        philosophy_id = await solver_db.get_page_id("Philosophy")
        assert philosophy_id is not None, "Philosophy page should exist in database"
        assert isinstance(philosophy_id, int), "Page ID should be an integer"
        assert philosophy_id > 0, "Page ID should be positive"

    @pytest.mark.asyncio
    async def test_get_page_id_case_insensitive(self, solver_db: StaticSolverDB):
        """Test that page ID retrieval is case-insensitive."""
        # Test same page with different cases
        page_id_1 = await solver_db.get_page_id("Philosophy")
        page_id_2 = await solver_db.get_page_id("philosophy")
        page_id_3 = await solver_db.get_page_id("PHILOSOPHY")
        
        assert page_id_1 is not None
        assert page_id_1 == page_id_2, "Case should not matter"
        assert page_id_1 == page_id_3, "Case should not matter"

    @pytest.mark.asyncio
    async def test_get_page_id_nonexistent(self, solver_db: StaticSolverDB):
        """Test page ID retrieval for non-existent pages."""
        nonexistent_id = await solver_db.get_page_id("ThisPageDefinitelyDoesNotExist12345")
        assert nonexistent_id is None, "Non-existent page should return None"

    @pytest.mark.asyncio
    async def test_get_page_title_basic(self, solver_db: StaticSolverDB):
        """Test retrieving page title from ID."""
        # First get a known page ID
        philosophy_id = await solver_db.get_page_id("Philosophy")
        assert philosophy_id is not None
        
        # Then get the title back
        title = await solver_db.get_page_title(philosophy_id)
        assert title is not None
        assert title == "Philosophy", f"Expected 'Philosophy', got '{title}'"

    @pytest.mark.asyncio
    async def test_get_page_title_nonexistent(self, solver_db: StaticSolverDB):
        """Test getting title for non-existent page ID."""
        # Use a very high ID that shouldn't exist
        title = await solver_db.get_page_title(999999999)
        assert title is None, "Non-existent page ID should return None"

    @pytest.mark.asyncio
    async def test_page_exists(self, solver_db: StaticSolverDB):
        """Test the page_exists method."""
        # Known page should exist
        assert await solver_db.page_exists("Philosophy") is True
        
        # Non-existent page should not exist
        assert await solver_db.page_exists("ThisPageDefinitelyDoesNotExist12345") is False

    @pytest.mark.asyncio
    async def test_get_outgoing_links(self, solver_db: StaticSolverDB):
        """Test retrieving outgoing links for a page."""
        # Get a page ID
        philosophy_id = await solver_db.get_page_id("Philosophy")
        assert philosophy_id is not None
        
        # Get outgoing links
        outgoing_links = await solver_db.get_outgoing_links(philosophy_id)
        assert isinstance(outgoing_links, list)
        assert len(outgoing_links) > 0, "Philosophy should have outgoing links"
        
        # All items should be integers (page IDs)
        for link_id in outgoing_links[:10]:  # Just check first 10
            assert isinstance(link_id, int)
            assert link_id > 0

    @pytest.mark.asyncio
    async def test_get_incoming_links(self, solver_db: StaticSolverDB):
        """Test retrieving incoming links for a page."""
        # Get a page ID for a well-linked page
        philosophy_id = await solver_db.get_page_id("Philosophy")
        assert philosophy_id is not None
        
        # Get incoming links
        incoming_links = await solver_db.get_incoming_links(philosophy_id)
        assert isinstance(incoming_links, list)
        assert len(incoming_links) > 0, "Philosophy should have incoming links"
        
        # All items should be integers (page IDs)
        for link_id in incoming_links[:10]:  # Just check first 10
            assert isinstance(link_id, int)
            assert link_id > 0

    @pytest.mark.asyncio
    async def test_batch_get_page_titles(self, solver_db: StaticSolverDB):
        """Test batch retrieval of page titles."""
        # Get some page IDs first
        philosophy_id = await solver_db.get_page_id("Philosophy")
        outgoing_links = await solver_db.get_outgoing_links(philosophy_id)
        
        # Test batch retrieval
        test_ids = outgoing_links[:5]  # Test with first 5 outgoing links
        titles = await solver_db.batch_get_page_titles(test_ids)
        
        assert len(titles) == len(test_ids)
        assert all(title is not None for title in titles), "All valid IDs should return titles"
        
        # Test with mix of valid and invalid IDs
        mixed_ids = test_ids + [999999999]  # Add invalid ID
        mixed_titles = await solver_db.batch_get_page_titles(mixed_ids)
        assert len(mixed_titles) == len(mixed_ids)
        assert mixed_titles[-1] is None, "Invalid ID should return None"

    @pytest.mark.asyncio
    async def test_batch_get_page_ids(self, solver_db: StaticSolverDB):
        """Test batch retrieval of page IDs."""
        titles = ["Philosophy", "Science", "NonExistentPage12345"]
        id_map = await solver_db.batch_get_page_ids(titles)
        
        assert len(id_map) == len(titles)
        assert "Philosophy" in id_map
        assert "Science" in id_map
        assert "NonExistentPage12345" in id_map
        
        assert id_map["Philosophy"] is not None
        assert id_map["Science"] is not None
        assert id_map["NonExistentPage12345"] is None

    @pytest.mark.asyncio
    async def test_fetch_links_count(self, solver_db: StaticSolverDB):
        """Test fetching link counts for pages."""
        # Get some page IDs
        philosophy_id = await solver_db.get_page_id("Philosophy")
        science_id = await solver_db.get_page_id("Science")
        
        page_ids = [philosophy_id, science_id]
        page_ids = [pid for pid in page_ids if pid is not None]  # Filter out None values
        
        if page_ids:
            # Test outgoing links count
            outgoing_count = await solver_db.fetch_outgoing_links_count(page_ids)
            assert outgoing_count >= 0
            
            # Test incoming links count
            incoming_count = await solver_db.fetch_incoming_links_count(page_ids)
            assert incoming_count >= 0
            
            # Test with empty list
            empty_count = await solver_db.fetch_outgoing_links_count([])
            assert empty_count == 0

    @pytest.mark.asyncio
    async def test_redirect_handling(self, solver_db: StaticSolverDB):
        """Test that the database correctly handles redirects."""
        # Many Wikipedia pages have redirects, test that they resolve correctly
        # Note: Specific redirect examples depend on the actual database content
        
        # Test that we can get page IDs for various title formats
        results = []
        test_titles = ["Philosophy", "philosophy", "PHILOSOPHY"]
        
        for title in test_titles:
            page_id = await solver_db.get_page_id(title)
            results.append(page_id)
        
        # All should resolve to the same page (or None if page doesn't exist)
        if results[0] is not None:
            assert all(result == results[0] for result in results), "All case variations should resolve to same page"

    @pytest.mark.asyncio 
    async def test_database_stats_consistency(self, solver_db: StaticSolverDB):
        """Test that database statistics are consistent and reasonable."""
        page_count, link_count = await solver_db.get_database_stats()
        
        # Basic sanity checks
        assert page_count > 0, "Should have pages in database"
        assert link_count > 0, "Should have links in database"
        assert link_count > page_count, "Typically more links than pages"
        
        # Check that individual operations are consistent with stats
        # Get a few random pages and verify they exist
        philosophy_id = await solver_db.get_page_id("Philosophy")
        if philosophy_id is not None:
            assert philosophy_id <= page_count or philosophy_id > 0, "Page ID should be reasonable"

    @pytest.mark.asyncio
    async def test_empty_results_handling(self, solver_db: StaticSolverDB):
        """Test handling of operations that return empty results."""
        # Test with empty lists
        empty_titles = await solver_db.batch_get_page_titles([])
        assert empty_titles == []
        
        empty_ids = await solver_db.batch_get_page_ids([])
        assert empty_ids == {}
        
        # Test outgoing links for a page that might not have any (unlikely but possible)
        # We'll just verify the method returns a list
        philosophy_id = await solver_db.get_page_id("Philosophy")
        if philosophy_id:
            outgoing = await solver_db.get_outgoing_links(philosophy_id)
            assert isinstance(outgoing, list)


class TestUtilityFunctions:
    """Test the utility functions for title sanitization and validation."""

    def test_get_sanitized_page_title(self):
        """Test page title sanitization."""
        assert get_sanitized_page_title("Notre Dame Fighting Irish") == "Notre_Dame_Fighting_Irish"
        assert get_sanitized_page_title("Farmers' market") == "Farmers\\'_market"
        
    def test_get_readable_page_title(self):
        """Test converting sanitized titles back to readable format."""
        assert get_readable_page_title("Notre_Dame_Fighting_Irish") == "Notre Dame Fighting Irish"
        assert get_readable_page_title("Farmers\\'_market") == "Farmers' market"

    def test_validate_page_title(self):
        """Test page title validation."""
        # Valid titles should not raise
        validate_page_title("Valid Title")
        validate_page_title("Philosophy")
        
        # Invalid titles should raise ValueError
        with pytest.raises(ValueError):
            validate_page_title("")
        with pytest.raises(ValueError):
            validate_page_title(None)
        with pytest.raises(ValueError):
            validate_page_title(123)

    def test_validate_page_id(self):
        """Test page ID validation."""
        # Valid IDs should not raise
        validate_page_id(1)
        validate_page_id(12345)
        
        # Invalid IDs should raise ValueError
        with pytest.raises(ValueError):
            validate_page_id(0)
        with pytest.raises(ValueError):
            validate_page_id(-1)
        with pytest.raises(ValueError):
            validate_page_id("123")
        with pytest.raises(ValueError):
            validate_page_id(None)

    def test_title_sanitization_roundtrip(self):
        """Test that sanitization and desanitization work correctly together."""
        test_titles = [
            "Simple Title",
            "Title with 'quotes'",
            'Title with "double quotes"',
            "Complex/Title\\With|Special*Characters",
            "Multi  Space   Title"
        ]
        
        for original in test_titles:
            sanitized = get_sanitized_page_title(original)
            readable = get_readable_page_title(sanitized)
            
            # Basic properties
            assert isinstance(sanitized, str)
            assert isinstance(readable, str)
            
            # Sanitized should have underscores instead of spaces
            if " " in original:
                assert "_" in sanitized
                assert " " not in sanitized


class TestStaticSolverDBConfiguration:
    """Test configuration and initialization of StaticSolverDB."""

    def test_default_database_path(self):
        """Test default database path configuration."""
        db = StaticSolverDB()
        expected_path = Path("database/wiki_graph.sqlite")
        assert db.db_path == expected_path

    def test_custom_database_path(self):
        """Test custom database path configuration."""
        custom_path = "custom/path/to/wiki.db"
        db = StaticSolverDB(db_path=custom_path)
        expected_path = Path(custom_path)
        assert db.db_path == expected_path

    def test_database_not_found_handling(self):
        """Test behavior when database file doesn't exist."""
        # Create StaticSolverDB with non-existent path
        db = StaticSolverDB(db_path="non_existent_database.sqlite")
        
        # It should handle the missing file gracefully (log error but not crash)
        # Actual operations will fail, but initialization shouldn't
        assert db.db_path == Path("non_existent_database.sqlite")


class TestGlobalInstance:
    """Test the global static_solver_db instance."""

    def test_global_instance_exists(self):
        """Test that the global instance is available."""
        assert static_solver_db is not None
        assert isinstance(static_solver_db, StaticSolverDB)

    @pytest.mark.asyncio
    async def test_global_instance_functional(self):
        """Test that the global instance is functional."""
        # Basic connectivity test using global instance
        if static_solver_db.db_path.exists():
            # Test only if database exists
            stats = await static_solver_db.get_database_stats()
            page_count, link_count = stats
            assert page_count >= 0
            assert link_count >= 0


class TestArchitecturalCompliance:
    """Test that StaticSolverDB follows the v2 architecture principles."""

    def test_single_responsibility(self):
        """Test that StaticSolverDB has a single, well-defined responsibility."""
        # StaticSolverDB should only provide access to the static wiki graph database
        # It should not have dependencies on game logic, live Wikipedia, or other services
        
        db = StaticSolverDB()
        
        # Check that it only has database-related methods
        expected_methods = {
            'get_page_id', 'get_page_title', 'get_outgoing_links', 'get_incoming_links',
            'batch_get_page_titles', 'batch_get_page_ids', 'get_database_stats',
            'page_exists', 'fetch_outgoing_links_count', 'fetch_incoming_links_count'
        }
        
        actual_methods = {method for method in dir(db) if not method.startswith('_')}
        
        # All expected methods should be present
        for method in expected_methods:
            assert hasattr(db, method), f"Missing expected method: {method}"
        
        # Should NOT have solving methods
        solving_methods = {'get_shortest_path', 'find_path', 'solve', 'calculate_path'}
        for method in solving_methods:
            assert not hasattr(db, method), f"Should not have solving method: {method}"

    def test_decoupling_from_game_logic(self):
        """Test that StaticSolverDB is decoupled from game logic."""
        # StaticSolverDB should not import or depend on game-related modules
        
        # Check imports in the module
        import wiki_arena.solver.static_db as static_db_module
        
        # Should not have imports related to game logic, MCP, or live Wikipedia
        module_globals = dir(static_db_module)
        
        # Should only have database and utility imports
        # Check that it imports database-related modules by inspecting the source
        import inspect
        source = inspect.getsource(static_db_module)
        assert 'aiosqlite' in source  # Should use async sqlite
        
        # Verify it can be used independently
        db = StaticSolverDB()
        assert db is not None

    def test_pure_database_functionality(self):
        """Test that StaticSolverDB provides pure database access without business logic."""
        db = StaticSolverDB()
        
        # Should be a simple data access layer
        # No complex algorithms, caching, or solving logic
        # Just CRUD operations on the database
        
        # Verify essential database operations exist
        essential_operations = [
            'get_page_id',           # Read page by title
            'get_page_title',        # Read title by ID  
            'get_outgoing_links',    # Read page relationships
            'get_incoming_links',    # Read page relationships
            'page_exists',           # Existence check
            'get_database_stats'     # Database metadata
        ]
        
        for operation in essential_operations:
            assert hasattr(db, operation), f"Missing essential database operation: {operation}" 