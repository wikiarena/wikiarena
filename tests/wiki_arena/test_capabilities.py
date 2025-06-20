"""
Tests for capability interfaces and implementations.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from wiki_arena.capabilities.navigation import NavigationResult, INavigationCapability
from wiki_arena.models import Page


class TestNavigationResult:
    """Test NavigationResult dataclass."""
    
    def test_success_result(self):
        """Test successful navigation result."""
        page = Page(title="Test", url="http://test.com", text="", links=["Link1"])
        result = NavigationResult(success=True, page=page)
        
        assert result.is_success
        assert result.page == page
        assert result.error_message is None
    
    def test_error_result(self):
        """Test error navigation result."""
        result = NavigationResult(success=False, error_message="Test error")
        
        assert not result.is_success
        assert result.page is None
        assert result.error_message == "Test error"
    
    def test_success_without_page(self):
        """Test that success=True but no page is considered failure."""
        result = NavigationResult(success=True, page=None)
        
        assert not result.is_success


class MockNavigationCapability(INavigationCapability):
    """Mock implementation for testing."""
    
    def __init__(self):
        self.navigate_calls = []
        self.available = True
    
    async def navigate_to_page(self, page_title: str) -> NavigationResult:
        self.navigate_calls.append(page_title)
        
        if page_title == "error_page":
            return NavigationResult(success=False, error_message="Mock error")
        
        page = Page(
            title=page_title,
            url=f"http://test.com/{page_title}",
            text="Mock content",
            links=["Link1", "Link2"]
        )
        return NavigationResult(success=True, page=page)
    
    async def get_capability_info(self) -> dict:
        return {"type": "mock", "features": ["test"]}
    
    def is_available(self) -> bool:
        return self.available


class TestNavigationCapabilityInterface:
    """Test navigation capability interface."""
    
    @pytest.fixture
    def mock_capability(self):
        return MockNavigationCapability()
    
    @pytest.mark.asyncio
    async def test_successful_navigation(self, mock_capability):
        """Test successful page navigation."""
        result = await mock_capability.navigate_to_page("Test Page")
        
        assert result.is_success
        assert result.page.title == "Test Page"
        assert result.page.links == ["Link1", "Link2"]
        assert "Test Page" in mock_capability.navigate_calls
    
    @pytest.mark.asyncio
    async def test_error_navigation(self, mock_capability):
        """Test error handling in navigation."""
        result = await mock_capability.navigate_to_page("error_page")
        
        assert not result.is_success
        assert result.error_message == "Mock error"
        assert result.page is None
    
    @pytest.mark.asyncio
    async def test_capability_info(self, mock_capability):
        """Test capability info retrieval."""
        info = await mock_capability.get_capability_info()
        
        assert info["type"] == "mock"
        assert info["features"] == ["test"]
    
    def test_availability_check(self, mock_capability):
        """Test availability checking."""
        assert mock_capability.is_available()
        
        mock_capability.available = False
        assert not mock_capability.is_available() 