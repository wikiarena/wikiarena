import pytest
from fastapi.testclient import TestClient
import logging
from backend.main import app

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = TestClient(app)

# Helper function to get ground truth path length from the solver
def get_path_length_from_solver(start_page: str, target_page: str) -> int:
    """Uses the solver API to get the authoritative shortest path length."""
    if start_page == target_page:
        return 0
    
    response = client.post(
        "/api/solver/path",
        json={"start_page": start_page, "target_page": target_page}
    )
    response.raise_for_status()
    data = response.json()
    return data["path_length"]

@pytest.mark.integration
def test_start_game_includes_initial_path_info():
    """
    Tests that the response from starting a game includes the
    initial optimal path length and the paths themselves.
    """
    start_page = "United Kingdom"
    target_page = "London"
    game_id = None
    
    try:
        # Ground truth from solver
        expected_path_length = get_path_length_from_solver(start_page, target_page)
        logger.info(f"Ground truth path length for {start_page} -> {target_page} is {expected_path_length}")

        response = client.post(
            "/api/games",
            json={
                "start_page": start_page,
                "target_page": target_page,
                "model_provider": "random", # using a real model
                "model_name": "random"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        game_id = data["game_id"]
        
        assert "game_state" in data
        game_state = data["game_state"]
        
        assert "optimal_path_length" in game_state
        assert game_state["optimal_path_length"] == expected_path_length
        
        assert "optimal_paths" in game_state
        assert isinstance(game_state["optimal_paths"], list)
        if game_state["optimal_paths"]:
            assert isinstance(game_state["optimal_paths"][0], list)
            # Verify the path starts and ends correctly
            assert all(
                path[0] == start_page and path[-1] == target_page for path in game_state["optimal_paths"]
            )
    finally:
        if game_id:
            delete_response = client.delete(f"/api/games/{game_id}")
            assert delete_response.status_code == 204

@pytest.mark.integration
def test_play_turn_updates_path_info_and_move_quality():
    """
    Tests the full flow:
    1. Start a game.
    2. Get the initial path length.
    3. Play one turn.
    4. Verify the move has a 'quality' and 'optimal_path_length_after'.
    5. Verify the new game state has an updated 'optimal_path_length'.
    """
    start_page = "Philosophy"
    target_page = "Science"
    game_id = None
    
    try:
        # 1. Start game and get initial path length
        start_response = client.post(
            "/api/games",
            json={"start_page": start_page, "target_page": target_page, "model_provider": "random"}
        )
        assert start_response.status_code == 200
        game_id = start_response.json()["game_id"]
        initial_path_length = start_response.json()["game_state"]["optimal_path_length"]
        logger.info(f"Initial path length for {start_page} -> {target_page} is {initial_path_length}")
        
        # 2. Play one turn
        turn_response = client.post(f"/api/games/{game_id}/turn")
        assert turn_response.status_code == 200
        
        game_state = turn_response.json()
        assert len(game_state["moves"]) == 1
        last_move = game_state["moves"][0]
        
        # 3. Verify the move's content
        assert "to_page_title" in last_move
        new_page = last_move["to_page_title"]
        logger.info(f"Model moved from {start_page} to {new_page}")
        
        assert "optimal_path_length_after" in last_move
        path_length_after_move = last_move["optimal_path_length_after"]
        
        # 4. Get ground truth for the new path length
        ground_truth_new_length = get_path_length_from_solver(new_page, target_page)
        logger.info(f"Ground truth path length for new page {new_page} -> {target_page} is {ground_truth_new_length}")
        
        assert path_length_after_move == ground_truth_new_length
        
        # 5. Determine expected quality and verify
        assert "quality" in last_move
        expected_quality = "SAME"
        if ground_truth_new_length < initial_path_length:
            expected_quality = "IMPROVED"
        elif ground_truth_new_length > initial_path_length:
            expected_quality = "WORSENED"
            
        logger.info(f"Move quality: initial={initial_path_length}, after={ground_truth_new_length}, expected={expected_quality}, actual={last_move['quality']}")
        assert last_move["quality"] == expected_quality
        
        # 6. Verify the new top-level game state
        assert game_state["current_page"] == new_page
        assert game_state["optimal_path_length"] == ground_truth_new_length
    finally:
        if game_id:
            delete_response = client.delete(f"/api/games/{game_id}")
            assert delete_response.status_code in [204, 404] # 404 is ok if game finished and was auto-cleaned