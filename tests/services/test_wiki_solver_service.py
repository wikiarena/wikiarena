import pytest
import pytest_asyncio

from backend.services.wiki_solver_service import wiki_solver, WikiPathSolver
from backend.services.wiki_db_service import WikiGraphDatabase # For type hinting if needed
from backend.models.solver_models import SolverResponse

# It might be beneficial to have a shared db_service fixture if tests here also need direct db access
# For now, wiki_solver uses the global wiki_db instance which is configured by its own module.
# Ensure that wiki_db is pointing to the correct TEST_DB_PATH if it was parameterized.
# For simplicity, we rely on wiki_db being initialized correctly by its module-level instantiation.

@pytest_asyncio.fixture(scope="module")
async def solver_service():
    """Fixture to provide an instance of WikiPathSolver for the test module."""
    service = WikiPathSolver()
    # Initialize the service if it has an explicit async setup (it does)
    await service.initialize() 
    return service

@pytest.mark.asyncio
async def test_path_to_self(solver_service: WikiPathSolver):
    """Test finding a path from a page to itself."""
    page_title = "Philosophy"
    response = await solver_service.find_shortest_path(page_title, page_title)
    
    assert isinstance(response, SolverResponse)
    assert response.paths == [[page_title]]
    assert response.path_length == 0
    assert response.from_cache is False # Caching is currently disabled
    assert response.computation_time_ms >= 0

@pytest.mark.asyncio
async def test_path_known_short_path_uk_london(solver_service: WikiPathSolver):
    """Test a known short path (e.g., United Kingdom to London)."""
    start_page = "United Kingdom"
    target_page = "London"
    
    # Before running, manually verify or explore that "London" is a direct link from "United Kingdom"
    # or what the actual shortest path is in your sdow.sqlite version.
    # Assuming a 1-hop path for this example.
    expected_path = [[start_page, target_page]] 
    expected_length = 1

    response = await solver_service.find_shortest_path(start_page, target_page)
    
    assert isinstance(response, SolverResponse)
    assert response.path_length == expected_length
    assert response.from_cache is False
    # Check if any of the found paths match the (or one of the) expected shortest path(s)
    assert any(path == expected_path[0] for path in response.paths) 
    # Or if multiple shortest paths are possible, and we know them all:
    # assert sorted(response.paths) == sorted(expected_paths_list)
    assert len(response.paths) >= 1 # Should find at least one path
    for path in response.paths:
        assert len(path) == expected_length + 1

@pytest.mark.asyncio
async def test_path_another_short_path_cat_feline(solver_service: WikiPathSolver):
    """Test another known short path (e.g., Cat to Feline)."""
    start_page = "Philosophy"
    target_page = "Banana" # "Feline" might be a redirect or part of "Felidae"
                          # Using "Felidae" as it's the family of cats.
    
    # Manually verify this path in your DB. Assuming 1-hop for example.
    # Cat -> Felidae is a common link.
    expected_path_example = [start_page, target_page]
    expected_length = 1

    response = await solver_service.find_shortest_path(start_page, target_page)
    
    assert isinstance(response, SolverResponse)
    assert response.path_length == expected_length
    assert response.from_cache is False
    assert any(path == expected_path_example for path in response.paths)
    for path in response.paths:
        assert len(path) == expected_length + 1

@pytest.mark.asyncio
async def test_path_start_page_not_found(solver_service: WikiPathSolver):
    """Test path finding when the start page does not exist."""
    start_page = "ThisIsASurelyNonExistentStartPage"
    target_page = "Philosophy"
    
    with pytest.raises(ValueError, match=f"Start page '{start_page}' not found in database."):
        await solver_service.find_shortest_path(start_page, target_page)

@pytest.mark.asyncio
async def test_path_target_page_not_found(solver_service: WikiPathSolver):
    """Test path finding when the target page does not exist."""
    start_page = "Philosophy"
    target_page = "ThisIsASurelyNonExistentTargetPage"
    
    with pytest.raises(ValueError, match=f"Target page '{target_page}' not found in database."):
        await solver_service.find_shortest_path(start_page, target_page)

@pytest.mark.asyncio
async def test_path_no_path_found_simulated(solver_service: WikiPathSolver, monkeypatch):
    """Test behavior when BFS returns no paths. (Requires mocking BFS)."""
    start_page = "Philosophy"
    target_page = "Banana" # Assume these are far apart or we want to simulate no path

    # Mock the internal _adapted_sdow_bfs to return an empty list
    async def mock_bfs(start_id, target_id):
        return []

    monkeypatch.setattr(solver_service, "_adapted_sdow_bfs", mock_bfs)

    with pytest.raises(ValueError, match=f"No path found between '{start_page}' and '{target_page}'."):
        await solver_service.find_shortest_path(start_page, target_page)

# More complex paths to consider testing (these will require verification in your sdow.sqlite):
# - "Earth" to "Moon" (expected length 1)
# - "Knight" to "Castle" (likely short)
# - "Algorithm" to "Computer Science" (likely short)
# - A pair known to be 2 or 3 hops apart.
# - A pair that might have multiple distinct shortest paths.

# Example: Test a 2-hop path (this is hypothetical, needs verification)
# @pytest.mark.asyncio
# async def test_path_known_2_hop(solver_service: WikiPathSolver):
#     start_page = "A"
#     intermediate_page = "B"
#     target_page = "C"
#     # Assuming A -> B -> C is one of the shortest paths and is 2 hops.
#     # This requires A, B, C to exist and be linked appropriately.
#     # And that there isn't a direct A -> C link.

#     # Manually determine IDs for A, B, C to verify in DB if needed.
#     # For this test, we mainly care about the solver_service output.

#     expected_paths = [[start_page, intermediate_page, target_page]]
#     expected_length = 2

#     response = await solver_service.find_shortest_path(start_page, target_page)
    
#     assert isinstance(response, SolverResponse)
#     assert response.path_length == expected_length
#     assert response.from_cache is False
#     # Check if any of the found paths match one of the expected shortest paths
#     found_match = False
#     for expected_path in expected_paths:
#         if expected_path in response.paths:
#             found_match = True
#             break
#     assert found_match, f"Expected one of {expected_paths} in {response.paths}"
#     for path in response.paths:
#        assert len(path) == expected_length + 1 