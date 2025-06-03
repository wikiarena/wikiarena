import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.models.solver_models import SolverResponse, SolverStatus

client = TestClient(app)

def test_find_shortest_path():
    """Test the /api/solver/path endpoint."""
    # Test case 1: Path to self
    response = client.post(
        "/api/solver/path",
        json={"start_page": "Philosophy", "target_page": "Philosophy"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["paths"] == [["Philosophy"]]
    assert data["path_length"] == 0
    assert data["from_cache"] is False
    assert data["computation_time_ms"] >= 0

    # Test case 2: Known short path (Philosophy to Banana)
    response = client.post(
        "/api/solver/path",
        json={"start_page": "Philosophy", "target_page": "Banana"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["path_length"] >= 1  # We know it's at least 1 hop
    assert len(data["paths"]) >= 1
    assert all(len(path) == data["path_length"] + 1 for path in data["paths"])
    # Verify the path starts and ends correctly
    assert all(path[0] == "Philosophy" and path[-1] == "Banana" for path in data["paths"])

    # Test case 3: Non-existent start page
    response = client.post(
        "/api/solver/path",
        json={"start_page": "ThisIsASurelyNonExistentStartPage", "target_page": "Philosophy"}
    )
    assert response.status_code == 404
    assert "Start page" in response.json()["detail"]

    # Test case 4: Non-existent target page
    response = client.post(
        "/api/solver/path",
        json={"start_page": "Philosophy", "target_page": "ThisIsASurelyNonExistentTargetPage"}
    )
    assert response.status_code == 404
    assert "Target page" in response.json()["detail"]

def test_get_solver_status():
    """Test the /api/solver/status endpoint."""
    response = client.get("/api/solver/status")
    assert response.status_code == 200
    data = response.json()
    
    # Check response structure
    assert "database_ready" in data
    assert "total_pages" in data
    assert "total_links" in data
    assert "last_updated" in data
    
    # Check data types
    assert isinstance(data["database_ready"], bool)
    assert data["total_pages"] is None or isinstance(data["total_pages"], int)
    assert data["total_links"] is None or isinstance(data["total_links"], int)
    assert data["last_updated"] is None or isinstance(data["last_updated"], str)

def test_validate_page():
    """Test the /api/solver/validate/{page_title} endpoint."""
    # Test case 1: Valid page
    response = client.get("/api/solver/validate/Philosophy")
    assert response.status_code == 200
    data = response.json()
    assert data["page_title"] == "Philosophy"
    assert data["exists"] is True
    assert data["page_id"] is not None
    assert "Page found" in data["message"]

    # Test case 2: Non-existent page
    response = client.get("/api/solver/validate/ThisIsASurelyNonExistentPage")
    assert response.status_code == 200
    data = response.json()
    assert data["page_title"] == "ThisIsASurelyNonExistentPage"
    assert data["exists"] is False
    assert data["page_id"] is None
    assert "not found" in data["message"]

def test_invalid_request_format():
    """Test error handling for invalid request formats."""
    # Test case 1: Missing required fields
    response = client.post(
        "/api/solver/path",
        json={"start_page": "Philosophy"}  # Missing target_page
    )
    assert response.status_code == 422  # FastAPI validation error

    # Test case 2: Invalid field types
    response = client.post(
        "/api/solver/path",
        json={"start_page": 123, "target_page": "Philosophy"}  # start_page should be string
    )
    assert response.status_code == 422

    # Test case 3: Empty strings (handled by service layer as 404)
    response = client.post(
        "/api/solver/path",
        json={"start_page": "", "target_page": "Philosophy"}
    )
    assert response.status_code == 422  # Now expects 422 due to Pydantic min_length=1
