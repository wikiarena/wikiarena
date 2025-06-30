import pytest
from unittest.mock import Mock, AsyncMock
from backend.services.task_selector_service import CustomTaskSelector
from backend.models.api_models import CustomTaskStrategy
from wiki_arena.models import Task

class TestCustomTaskSelector:
    """Test the CustomTaskSelector with validation and random fallback."""
    
    @pytest.fixture
    def mock_service(self):
        """Mock LiveWikiService for testing."""
        service = Mock()
        service.get_page = AsyncMock()
        service.has_outgoing_links = AsyncMock()
        service.has_incoming_links = AsyncMock()
        service.get_random_pages = AsyncMock()
        return service
    
    def test_custom_task_strategy_validation(self):
        """Test that CustomTaskStrategy validates input correctly."""
        # Valid with both pages
        strategy = CustomTaskStrategy(start_page="Philosophy", target_page="Science")
        assert strategy.start_page == "Philosophy"
        assert strategy.target_page == "Science"
        
        # Valid with only start page
        strategy = CustomTaskStrategy(start_page="Philosophy")
        assert strategy.start_page == "Philosophy"
        assert strategy.target_page is None
        
        # Valid with only target page
        strategy = CustomTaskStrategy(target_page="Science")
        assert strategy.start_page is None
        assert strategy.target_page == "Science"
        
        # Valid with neither page
        strategy = CustomTaskStrategy()
        assert strategy.start_page is None
        assert strategy.target_page is None
    
    def test_custom_task_strategy_validation_errors(self):
        """Test that CustomTaskStrategy raises validation errors for invalid input."""
        # Same start and target page
        with pytest.raises(ValueError, match="Start and target pages must be different"):
            CustomTaskStrategy(start_page="Philosophy", target_page="Philosophy")
        
        # Empty string pages
        with pytest.raises(ValueError, match="Page titles must be non-empty if provided"):
            CustomTaskStrategy(start_page="")
        
        with pytest.raises(ValueError, match="Page titles must be non-empty if provided"):
            CustomTaskStrategy(target_page="   ")
    
    @pytest.mark.asyncio
    async def test_both_pages_provided_valid(self, mock_service):
        """Test case where both pages are provided and valid."""
        strategy = CustomTaskStrategy(start_page="Philosophy", target_page="Science")
        selector = CustomTaskSelector(strategy)
        selector.wiki = mock_service
        
        # Mock successful validation
        mock_service.get_page.return_value = Mock()  # Page exists
        mock_service.has_outgoing_links.return_value = True
        mock_service.has_incoming_links.return_value = True
        
        task = await selector.select_task()
        
        assert task is not None
        assert task.start_page_title == "Philosophy"
        assert task.target_page_title == "Science"
        
        # Verify validation calls
        mock_service.get_page.assert_any_call("Philosophy")
        mock_service.get_page.assert_any_call("Science")
        mock_service.has_outgoing_links.assert_called_with("Philosophy")
        mock_service.has_incoming_links.assert_called_with("Science")
    
    @pytest.mark.asyncio
    async def test_both_pages_provided_start_missing(self, mock_service):
        """Test case where start page doesn't exist."""
        strategy = CustomTaskStrategy(start_page="NonExistentPage", target_page="Science")
        selector = CustomTaskSelector(strategy)
        selector.wiki = mock_service
        
        # Mock start page doesn't exist, target page exists
        mock_service.get_page.side_effect = [ValueError("Page does not exist"), Mock()]
        
        task = await selector.select_task()
        
        assert task is None
    
    @pytest.mark.asyncio
    async def test_both_pages_provided_start_no_outgoing_links(self, mock_service):
        """Test case where start page has no outgoing links."""
        strategy = CustomTaskStrategy(start_page="DeadEndPage", target_page="Science")
        selector = CustomTaskSelector(strategy)
        selector.wiki = mock_service
        
        # Mock both pages exist but start has no outgoing links
        mock_service.get_page.return_value = Mock()
        mock_service.has_outgoing_links.return_value = False
        mock_service.has_incoming_links.return_value = True
        
        task = await selector.select_task()
        
        assert task is None
    
    def test_get_strategy_info_both_pages(self):
        """Test strategy info when both pages are provided."""
        strategy = CustomTaskStrategy(start_page="Philosophy", target_page="Science")
        selector = CustomTaskSelector(strategy)
        
        info = selector.get_strategy_info()
        
        assert info["strategy"] == "custom"
        assert info["start_page"] == "Philosophy"
        assert info["target_page"] == "Science"
        assert info["language"] == "en"
    
    def test_get_strategy_info_partial_pages(self):
        """Test strategy info when only some pages are provided."""
        strategy = CustomTaskStrategy(start_page="Philosophy")
        selector = CustomTaskSelector(strategy)
        
        info = selector.get_strategy_info()
        
        assert info["strategy"] == "custom"
        assert info["start_page"] == "Philosophy"
        assert info["target_page"] == "random"
        assert info["language"] == "en"
    
    def test_get_strategy_info_no_pages(self):
        """Test strategy info when no pages are provided."""
        strategy = CustomTaskStrategy()
        selector = CustomTaskSelector(strategy)
        
        info = selector.get_strategy_info()
        
        assert info["strategy"] == "custom"
        assert info["start_page"] == "random"
        assert info["target_page"] == "random"
        assert info["language"] == "en" 