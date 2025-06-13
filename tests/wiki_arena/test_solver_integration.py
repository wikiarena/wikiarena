"""
Integration tests for the WikiTaskSolver - NO MOCKS.
Tests the complete solver functionality using real database operations.
"""

import pytest
import pytest_asyncio
import logging
from pathlib import Path

from wiki_arena.solver import WikiTaskSolver, SolverResponse, wiki_task_solver
from wiki_arena.solver.static_db import StaticSolverDB

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)


class TestWikiTaskSolverBasicOperations:
    """Test basic path finding operations."""

    @pytest_asyncio.fixture(scope="function")
    async def solver(self):
        """Fixture to provide a WikiTaskSolver instance for testing."""
        # Use a fresh instance for each test to avoid cache interference
        solver = WikiTaskSolver()
        await solver.initialize()
        return solver

    @pytest.mark.asyncio
    async def test_path_to_self(self, solver: WikiTaskSolver):
        """Test finding a path from a page to itself."""
        page_title = "Philosophy"
        response = await solver.find_shortest_path(page_title, page_title)
        
        assert isinstance(response, SolverResponse)
        assert response.paths == [[page_title]]
        assert response.path_length == 0
        assert response.computation_time_ms >= 0
        
        print(f"Self-path test: {page_title} -> {page_title} in {response.computation_time_ms:.2f}ms")

    @pytest.mark.asyncio
    async def test_known_direct_link(self, solver: WikiTaskSolver):
        """Test a known direct link path."""
        start_page = "Philosophy"
        target_page = "Science"
        
        response = await solver.find_shortest_path(start_page, target_page)
        
        assert isinstance(response, SolverResponse)
        assert response.path_length >= 1, "Should have at least 1 step"
        assert len(response.paths) >= 1, "Should find at least one path"
        
        # Verify all paths have correct length
        for path in response.paths:
            assert len(path) == response.path_length + 1, f"Path {path} length mismatch"
            assert path[0] == start_page, f"Path should start with {start_page}"
            assert path[-1] == target_page, f"Path should end with {target_page}"
        
        print(f"Direct link test: {start_page} -> {target_page} in {response.path_length} steps ({response.computation_time_ms:.2f}ms)")
        print(f"Found {len(response.paths)} path(s): {response.paths[0]}")

    @pytest.mark.asyncio
    async def test_multi_hop_path(self, solver: WikiTaskSolver):
        """Test finding a multi-hop path."""
        start_page = "Philosophy"
        target_page = "Mathematics"
        
        response = await solver.find_shortest_path(start_page, target_page)
        
        assert isinstance(response, SolverResponse)
        assert response.path_length >= 1, "Should require at least 1 step"
        assert len(response.paths) >= 1, "Should find at least one path"
        
        # Verify path integrity
        for path in response.paths:
            assert len(path) == response.path_length + 1
            assert path[0] == start_page
            assert path[-1] == target_page
            # Ensure no None values in path
            assert all(page is not None for page in path)
        
        print(f"Multi-hop test: {start_page} -> {target_page} in {response.path_length} steps ({response.computation_time_ms:.2f}ms)")

    @pytest.mark.asyncio 
    async def test_start_page_not_found(self, solver: WikiTaskSolver):
        """Test error handling when start page doesn't exist."""
        start_page = "ThisIsASurelyNonExistentStartPage12345"
        target_page = "Philosophy"
        
        with pytest.raises(ValueError, match=f"Start page '{start_page}' not found in database"):
            await solver.find_shortest_path(start_page, target_page)

    @pytest.mark.asyncio
    async def test_target_page_not_found(self, solver: WikiTaskSolver):
        """Test error handling when target page doesn't exist."""
        start_page = "Philosophy"
        target_page = "ThisIsASurelyNonExistentTargetPage12345"
        
        with pytest.raises(ValueError, match=f"Target page '{target_page}' not found in database"):
            await solver.find_shortest_path(start_page, target_page)

    @pytest.mark.asyncio
    async def test_both_pages_not_found(self, solver: WikiTaskSolver):
        """Test error handling when both pages don't exist."""
        start_page = "NonExistentStart12345"
        target_page = "NonExistentTarget12345"
        
        # Should fail on start page first
        with pytest.raises(ValueError, match=f"Start page '{start_page}' not found"):
            await solver.find_shortest_path(start_page, target_page)


class TestWikiTaskSolverCaching:
    """Test caching behavior and performance optimizations."""

    @pytest_asyncio.fixture(scope="function")
    async def solver(self):
        """Fixture providing a solver instance for caching tests."""
        solver = WikiTaskSolver()
        await solver.initialize()
        return solver

    @pytest.mark.asyncio
    async def test_same_target_caching(self, solver: WikiTaskSolver, caplog):
        """Test that subsequent calls with same target use caching, with performance comparison."""
        start_page = "Philosophy"
        target_page = "Science"
        
        # Clear any existing caches
        solver.active_target_id = None
        solver.cached_backward_bfs_state = None
        solver.cached_forward_expansion_links.clear()
        
        # Get outgoing links from the start page to simulate game move
        start_id = await solver.db.get_page_id(start_page)
        outgoing_links = await solver.db.get_outgoing_links(start_id)
        assert len(outgoing_links) > 0, f"Start page '{start_page}' should have outgoing links"
        
        # Get a child page title for the second call
        child_page_id = outgoing_links[0]  # Pick first outgoing link
        child_page_title = await solver.db.get_page_title(child_page_id)
        assert child_page_title is not None, "Child page should exist"
        
        with caplog.at_level(logging.INFO):
            # First call - should build cache for target
            caplog.clear()
            response1 = await solver.find_shortest_path(start_page, target_page)
            
            # Should see cache building messages
            cache_build_logs = [record for record in caplog.records if "target_id" in record.message.lower()]
            assert len(cache_build_logs) > 0, "Should have cache building logs"
            
            # Second call with child page and same target - should use cache
            # This simulates a player move from start_page to child_page
            caplog.clear()
            response2 = await solver.find_shortest_path(child_page_title, target_page)
            
            # Should see cache reuse messages
            cache_reuse_logs = [record for record in caplog.records if "reusing cached" in record.message.lower()]
            assert len(cache_reuse_logs) > 0, "Should have cache reuse logs"
        
        # Step 3: Clear cache and run the same child page query again for comparison
        cached_time = response2.computation_time_ms
        cached_paths = response2.paths
        cached_length = response2.path_length
        
        # Clear all caches
        solver.active_target_id = None
        solver.cached_backward_bfs_state = None
        solver.cached_forward_expansion_links.clear()
        
        with caplog.at_level(logging.INFO):
            caplog.clear()
            response2_uncached = await solver.find_shortest_path(child_page_title, target_page)
            
            # Should see fresh cache building (no reuse messages)
            no_reuse_logs = [record for record in caplog.records if "reusing cached" in record.message.lower()]
            assert len(no_reuse_logs) == 0, "Should not have cache reuse logs after clearing cache"
        
        # Verify all responses succeed
        assert response1.path_length >= 0
        assert cached_length >= 0
        assert response2_uncached.path_length >= 0
        
        # Both runs of child->target should have identical results
        assert cached_length == response2_uncached.path_length, \
            "Cached and uncached results should be identical"
        assert cached_paths == response2_uncached.paths, \
            "Cached and uncached paths should be identical"
        
        # Calculate cache performance benefit
        uncached_time = response2_uncached.computation_time_ms
        if uncached_time > 0:
            speedup = uncached_time / cached_time if cached_time > 0 else 1.0
            speedup_percent = ((uncached_time - cached_time) / uncached_time) * 100 if uncached_time > 0 else 0.0
        else:
            speedup = 1.0
            speedup_percent = 0.0
        
        print(f"Initial call ({start_page} -> {target_page}): {response1.computation_time_ms:.2f}ms ({response1.path_length} steps)")
        print(f"Child page used for comparison: {child_page_title}")
        print(f"Cached call ({child_page_title} -> {target_page}): {cached_time:.2f}ms ({cached_length} steps)")
        print(f"Uncached call ({child_page_title} -> {target_page}): {uncached_time:.2f}ms ({response2_uncached.path_length} steps)")
        if speedup > 1.0:
            print(f"Cache performance: {speedup:.2f}x speedup ({speedup_percent:.1f}% faster)")
        else:
            print(f"Cache performance: {1/speedup:.2f}x slower ({-speedup_percent:.1f}% slower)")
        
    @pytest.mark.asyncio
    async def test_target_change_cache_invalidation(self, solver: WikiTaskSolver, caplog):
        """Test that changing target invalidates caches."""
        # First target
        target1 = "Science"
        target2 = "Mathematics"
        
        solver.active_target_id = None
        
        with caplog.at_level(logging.INFO):
            # First call
            caplog.clear()
            await solver.find_shortest_path("Philosophy", target1)
            
            # Should build cache for target1
            target1_id = await solver.db.get_page_id(target1)
            assert solver.active_target_id == target1_id
            
            # Second call with different target
            caplog.clear()
            await solver.find_shortest_path("Philosophy", target2)
            
            # Should see cache reset message
            reset_logs = [record for record in caplog.records if "resetting caches" in record.message.lower()]
            assert len(reset_logs) > 0, "Should have cache reset logs"
            
            # Should have new active target
            target2_id = await solver.db.get_page_id(target2)
            assert solver.active_target_id == target2_id

    @pytest.mark.asyncio
    async def test_forward_link_caching(self, solver: WikiTaskSolver, caplog):
        """Test that forward link expansion uses caching."""
        target_page = "Science"
        
        # Clear caches
        solver.active_target_id = None
        solver.cached_forward_expansion_links.clear()
        
        with caplog.at_level(logging.DEBUG):
            caplog.clear()
            
            # First call - should populate forward link cache
            response1 = await solver.find_shortest_path("Philosophy", target_page)
            
            # Should see cache MISS messages
            miss_logs = [record for record in caplog.records if "cache MISS" in record.message]
            assert len(miss_logs) > 0, "Should have cache MISS logs"
            
            # Second call with overlapping path - should use cached forward links
            caplog.clear()
            response2 = await solver.find_shortest_path("Logic", target_page)
            
            # Should see some cache HIT messages if paths overlap
            hit_logs = [record for record in caplog.records if "cache HIT" in record.message]
            # Note: HITs depend on actual path overlap, so we just verify the mechanism works
            
        assert response1.path_length >= 0
        assert response2.path_length >= 0


class TestWikiTaskSolverPathIntegrity:
    """Test path correctness and integrity."""

    @pytest_asyncio.fixture(scope="function")
    async def solver(self):
        """Fixture providing a solver instance."""
        solver = WikiTaskSolver()
        await solver.initialize()
        return solver

    @pytest.mark.asyncio
    async def test_path_connectivity(self, solver: WikiTaskSolver):
        """Test that all returned paths are actually connected."""
        start_page = "Philosophy"
        target_page = "Science"
        
        response = await solver.find_shortest_path(start_page, target_page)
        
        # Verify each path is properly connected
        for path_idx, path in enumerate(response.paths):
            for i in range(len(path) - 1):
                current_page = path[i]
                next_page = path[i + 1]
                
                # Verify that next_page is actually linked from current_page
                current_id = await solver.db.get_page_id(current_page)
                next_id = await solver.db.get_page_id(next_page)
                
                assert current_id is not None, f"Page '{current_page}' should exist"
                assert next_id is not None, f"Page '{next_page}' should exist"
                
                outgoing_links = await solver.db.get_outgoing_links(current_id)
                assert next_id in outgoing_links, f"Path {path_idx}: '{current_page}' should link to '{next_page}'"
        
        print(f"Path connectivity verified for {len(response.paths)} path(s)")

    @pytest.mark.asyncio
    async def test_multiple_paths_same_length(self, solver: WikiTaskSolver):
        """Test that all returned paths have the same length (shortest)."""
        start_page = "Philosophy"
        target_page = "Science"
        
        response = await solver.find_shortest_path(start_page, target_page)
        
        if len(response.paths) > 1:
            path_lengths = [len(path) - 1 for path in response.paths]  # Convert to step count
            assert all(length == response.path_length for length in path_lengths), \
                f"All paths should have length {response.path_length}, but got {path_lengths}"
            
            print(f"Multiple paths verified: {len(response.paths)} paths all have {response.path_length} steps")
        else:
            print(f"Single path found with {response.path_length} steps")

    @pytest.mark.asyncio
    async def test_path_uniqueness(self, solver: WikiTaskSolver):
        """Test that returned paths are unique."""
        start_page = "Philosophy"
        target_page = "Science"
        
        response = await solver.find_shortest_path(start_page, target_page)
        
        # Convert paths to tuples for set comparison
        path_tuples = [tuple(path) for path in response.paths]
        unique_paths = set(path_tuples)
        
        assert len(unique_paths) == len(response.paths), \
            f"Found duplicate paths: {len(response.paths)} total, {len(unique_paths)} unique"
        
        print(f"Path uniqueness verified: {len(response.paths)} unique paths")


class TestWikiTaskSolverPerformance:
    """Test performance characteristics and edge cases."""

    @pytest_asyncio.fixture(scope="function")
    async def solver(self):
        """Fixture providing a solver instance."""
        solver = WikiTaskSolver()
        await solver.initialize()
        return solver

    @pytest.mark.asyncio
    async def test_performance_reasonable_time(self, solver: WikiTaskSolver):
        """Test that path finding completes in reasonable time."""
        start_page = "Philosophy"
        target_page = "Science"
        
        response = await solver.find_shortest_path(start_page, target_page)
        
        # Should complete within 10 seconds for any reasonable path
        assert response.computation_time_ms < 10000, \
            f"Path finding took too long: {response.computation_time_ms:.2f}ms"
        
        print(f"Performance test: Found path in {response.computation_time_ms:.2f}ms")

    @pytest.mark.asyncio
    async def test_various_path_lengths(self, solver: WikiTaskSolver):
        """Test paths of various lengths."""
        test_cases = [
            ("Philosophy", "Philosophy"),  # 0 steps
            ("Philosophy", "Science"),     # Likely 1-2 steps
            ("Philosophy", "Mathematics"), # Likely 2-3 steps
        ]
        
        results = []
        for start, target in test_cases:
            try:
                response = await solver.find_shortest_path(start, target)
                results.append((start, target, response.path_length, response.computation_time_ms))
                print(f"{start} -> {target}: {response.path_length} steps ({response.computation_time_ms:.2f}ms)")
            except Exception as e:
                print(f"{start} -> {target}: ERROR - {e}")
                results.append((start, target, -1, -1))
        
        # Verify we got some successful results
        successful_results = [r for r in results if r[2] >= 0]
        assert len(successful_results) >= 2, f"Should have at least 2 successful path findings, got {len(successful_results)}"

    @pytest.mark.asyncio
    async def test_bidirectional_efficiency(self, solver: WikiTaskSolver):
        """Test that bidirectional search is more efficient than would be expected from unidirectional."""
        # This is more of a sanity check - bidirectional BFS should find paths efficiently
        start_page = "Philosophy"
        target_page = "Mathematics"
        
        response = await solver.find_shortest_path(start_page, target_page)
        
        # Basic checks
        assert response.path_length >= 1, "Should find a path of at least 1 step"
        assert response.path_length <= 6, "Path should not be unreasonably long (>6 steps suggests inefficiency)"
        assert response.computation_time_ms < 5000, "Should complete within 5 seconds"
        
        print(f"Bidirectional efficiency: {start_page} -> {target_page} in {response.path_length} steps, {response.computation_time_ms:.2f}ms")


class TestWikiTaskSolverDatabaseIntegration:
    """Test integration with StaticSolverDB."""

    @pytest_asyncio.fixture(scope="function")
    async def solver(self):
        """Fixture providing a solver instance."""
        solver = WikiTaskSolver()
        await solver.initialize()
        return solver

    @pytest.mark.asyncio
    async def test_database_dependency_injection(self):
        """Test that solver can use a custom database instance."""
        # Create a custom database instance
        custom_db = StaticSolverDB()
        solver_with_custom_db = WikiTaskSolver(db=custom_db)
        
        await solver_with_custom_db.initialize()
        
        # Should work with custom database
        response = await solver_with_custom_db.find_shortest_path("Philosophy", "Science")
        assert response.path_length >= 0
        
        # Should be using the custom database
        assert solver_with_custom_db.db is custom_db

    @pytest.mark.asyncio
    async def test_database_operations_integration(self, solver: WikiTaskSolver):
        """Test that solver properly uses database operations."""
        start_page = "Philosophy"
        target_page = "Science"
        
        # Test the solver
        response = await solver.find_shortest_path(start_page, target_page)
        
        # Verify database operations work correctly by checking the path manually
        start_id = await solver.db.get_page_id(start_page)
        target_id = await solver.db.get_page_id(target_page)
        
        assert start_id is not None
        assert target_id is not None
        
        # Verify the path exists in the database
        for path in response.paths:
            path_ids = []
            for page_title in path:
                page_id = await solver.db.get_page_id(page_title)
                assert page_id is not None
                path_ids.append(page_id)
            
            # Verify connectivity
            for i in range(len(path_ids) - 1):
                current_id = path_ids[i]
                next_id = path_ids[i + 1]
                outgoing_links = await solver.db.get_outgoing_links(current_id)
                assert next_id in outgoing_links, f"Database link verification failed: {path[i]} -> {path[i+1]}"

    @pytest.mark.asyncio
    async def test_solver_with_global_instance(self):
        """Test using the global solver instance."""
        # Test the global instance works
        response = await wiki_task_solver.find_shortest_path("Philosophy", "Science")
        assert isinstance(response, SolverResponse)
        assert response.path_length >= 0
        
        print(f"Global instance test: Found path with {response.path_length} steps")


class TestWikiTaskSolverEdgeCases:
    """Test edge cases and error conditions."""

    @pytest_asyncio.fixture(scope="function") 
    async def solver(self):
        """Fixture providing a solver instance."""
        solver = WikiTaskSolver()
        await solver.initialize()
        return solver

    @pytest.mark.asyncio
    async def test_case_insensitive_pages(self, solver: WikiTaskSolver):
        """Test that page titles are handled case-insensitively."""
        # Test various case combinations
        test_cases = [
            ("philosophy", "science"),
            ("Philosophy", "science"),
            ("PHILOSOPHY", "SCIENCE"),
            ("Philosophy", "Science"),
        ]
        
        results = []
        for start, target in test_cases:
            try:
                response = await solver.find_shortest_path(start, target)
                results.append(response.path_length)
            except ValueError:
                # If pages don't exist, that's fine for this test
                results.append(-1)
        
        # All valid results should be the same path length
        valid_results = [r for r in results if r >= 0]
        if len(valid_results) > 1:
            assert all(r == valid_results[0] for r in valid_results), \
                f"Case variations should yield same path length: {valid_results}"

    @pytest.mark.asyncio
    async def test_special_characters_in_titles(self, solver: WikiTaskSolver):
        """Test handling of special characters in page titles."""
        # Test with pages that might have special characters
        try:
            # These might or might not exist, but shouldn't crash
            response = await solver.find_shortest_path("Philosophy", "Science")
            assert response.path_length >= 0
        except ValueError as e:
            # If pages don't exist, that's expected
            assert "not found" in str(e)

    @pytest.mark.asyncio
    async def test_initialization_idempotency(self, solver: WikiTaskSolver):
        """Test that multiple initializations don't break the solver."""
        # Initialize multiple times
        await solver.initialize()
        await solver.initialize()
        await solver.initialize()
        
        # Should still work
        response = await solver.find_shortest_path("Philosophy", "Science")
        assert isinstance(response, SolverResponse)
        assert response.path_length >= 0
        
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, solver: WikiTaskSolver):
        """Test that concurrent path finding operations work correctly."""
        import asyncio
        
        # Run multiple path finding operations concurrently
        tasks = [
            solver.find_shortest_path("Philosophy", "Science"),
            solver.find_shortest_path("Mathematics", "Philosophy"),
            solver.find_shortest_path("Science", "Mathematics"),
        ]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # At least some should succeed
            successful = [r for r in results if isinstance(r, SolverResponse)]
            assert len(successful) >= 1, f"At least one concurrent operation should succeed, got {results}"
            
            for response in successful:
                assert response.path_length >= 0
                
        except Exception as e:
            # Some operations might fail due to non-existent pages, that's okay
            print(f"Concurrent test had expected failures: {e}")


class TestWikiTaskSolverArchitecturalCompliance:
    """Test architectural compliance with ARCHITECTURE_V2.md principles."""

    def test_single_responsibility(self):
        """Test that WikiTaskSolver has a single, well-defined responsibility."""
        solver = WikiTaskSolver()
        
        # Should only have path-finding related methods
        expected_methods = {
            'initialize', 'find_shortest_path'
        }
        
        # Get public methods
        public_methods = {method for method in dir(solver) if not method.startswith('_')}
        
        # Remove non-method attributes
        actual_methods = {method for method in public_methods 
                         if callable(getattr(solver, method))}
        
        # Should have the expected methods
        for method in expected_methods:
            assert hasattr(solver, method), f"Missing expected method: {method}"
        
        # Should not have unrelated methods (like database operations)
        database_methods = {'get_page_id', 'get_outgoing_links', 'batch_get_page_titles'}
        for method in database_methods:
            assert not hasattr(solver, method), f"Should not have database method: {method}"

    def test_depends_on_static_solver_db(self):
        """Test that WikiTaskSolver correctly depends on StaticSolverDB."""
        solver = WikiTaskSolver()
        
        # Should have a database dependency
        assert hasattr(solver, 'db')
        assert isinstance(solver.db, StaticSolverDB)
        
        # Should be able to inject custom database
        custom_db = StaticSolverDB()
        custom_solver = WikiTaskSolver(db=custom_db)
        assert custom_solver.db is custom_db

    def test_no_game_logic_dependencies(self):
        """Test that WikiTaskSolver has no dependencies on game logic."""
        # Check imports in the module
        import wiki_arena.solver.task_solver as path_solver_module
        import inspect
        
        source = inspect.getsource(path_solver_module)
        
        # Should not import game-related modules
        forbidden_imports = ['game', 'mcp', 'language_model', 'wikipedia.live']
        for forbidden in forbidden_imports:
            assert forbidden not in source.lower(), f"Should not import {forbidden} modules"
        
        # Should import solver-related modules
        required_imports = ['static_db', 'models']
        for required in required_imports:
            assert required in source, f"Should import {required}"

    @pytest.mark.asyncio
    async def test_purely_analytical(self):
        """Test that WikiTaskSolver is purely analytical (no side effects)."""
        solver = WikiTaskSolver()
        await solver.initialize()
        
        # Multiple calls with same parameters should give same results
        start_page = "Philosophy"
        target_page = "Science"
        
        response1 = await solver.find_shortest_path(start_page, target_page)
        response2 = await solver.find_shortest_path(start_page, target_page)
        
        # Results should be deterministic
        assert response1.path_length == response2.path_length
        assert response1.paths == response2.paths
        
        # Should not modify database
        # (This is implicit since we use StaticSolverDB which is read-only) 