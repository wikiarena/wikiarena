"""
Comprehensive unit tests for the Wikipedia Page Selector module.

Tests all functionality including:
- PagePair data class validation
- LinkValidationConfig configuration
- WikipediaPageSelector class methods
- Synchronous and asynchronous functionality
- Error handling and edge cases
- API mocking for reliable testing
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass
from typing import Optional, List, Set

from wiki_arena.wikipedia.page_selector import (
    PagePair,
    LinkValidationConfig,
    WikipediaPageSelector,
    get_random_page_pair,
    get_random_page_pair_async
)


class TestPagePair:
    """Test the PagePair data class."""
    
    def test_valid_page_pair_creation(self):
        """Test creating a valid page pair with different pages."""
        pair = PagePair(start_page="Page A", target_page="Page B")
        assert pair.start_page == "Page A"
        assert pair.target_page == "Page B"
    
    def test_page_pair_rejects_same_pages(self):
        """Test that PagePair raises ValueError when start and target are the same."""
        with pytest.raises(ValueError, match="Start page and target page must be different"):
            PagePair(start_page="Same Page", target_page="Same Page")
    
    def test_page_pair_empty_strings(self):
        """Test PagePair with empty strings (should be allowed by validation)."""
        # Empty strings are different, so this should work
        pair = PagePair(start_page="", target_page="Non-empty")
        assert pair.start_page == ""
        assert pair.target_page == "Non-empty"
    
    def test_page_pair_whitespace_differences(self):
        """Test that whitespace differences are considered different pages."""
        pair = PagePair(start_page="Page", target_page="Page ")  # Note trailing space
        assert pair.start_page == "Page"
        assert pair.target_page == "Page "


class TestLinkValidationConfig:
    """Test the LinkValidationConfig data class."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = LinkValidationConfig()
        assert config.require_outgoing_links is True
        assert config.require_incoming_links is True
        assert config.min_outgoing_links == 1
        assert config.min_incoming_links == 1
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = LinkValidationConfig(
            require_outgoing_links=False,
            require_incoming_links=True,
            min_outgoing_links=10,
            min_incoming_links=5
        )
        assert config.require_outgoing_links is False
        assert config.require_incoming_links is True
        assert config.min_outgoing_links == 10
        assert config.min_incoming_links == 5


class TestWikipediaPageSelector:
    """Test the WikipediaPageSelector class."""
    
    def test_init_default_values(self):
        """Test initialization with default values."""
        selector = WikipediaPageSelector()
        assert selector.language == "en"
        assert selector.max_retries == 3
        assert selector.base_url == "https://en.wikipedia.org/w/api.php"
        assert "Category:" in selector.excluded_prefixes
        assert "File:" in selector.excluded_prefixes
    
    def test_init_custom_values(self):
        """Test initialization with custom values."""
        custom_excluded = {"Custom:", "Test:"}
        link_config = LinkValidationConfig(require_outgoing_links=False)
        
        selector = WikipediaPageSelector(
            language="de",
            max_retries=5,
            excluded_prefixes=custom_excluded,
            link_validation=link_config
        )
        
        assert selector.language == "de"
        assert selector.max_retries == 5
        assert selector.base_url == "https://de.wikipedia.org/w/api.php"
        assert selector.excluded_prefixes == custom_excluded
        assert selector.link_validation.require_outgoing_links is False
    
    def test_is_valid_page_title(self):
        """Test page title validation logic."""
        selector = WikipediaPageSelector()
        
        # Valid titles
        assert selector._is_valid_page_title("Regular Article") is True
        assert selector._is_valid_page_title("Article with numbers 123") is True
        assert selector._is_valid_page_title("Article-with-hyphens") is True
        
        # Invalid titles (excluded prefixes)
        assert selector._is_valid_page_title("Category:Test") is False
        assert selector._is_valid_page_title("File:Image.jpg") is False
        assert selector._is_valid_page_title("Template:TestTemplate") is False
        assert selector._is_valid_page_title("User:Username") is False
        
        # Edge cases
        assert selector._is_valid_page_title("") is False
        assert selector._is_valid_page_title("   ") is False
        assert selector._is_valid_page_title(None) is False
    
    def test_is_valid_page_title_custom_exclusions(self):
        """Test page title validation with custom exclusions."""
        custom_excluded = {"List of", "Timeline of"}
        selector = WikipediaPageSelector(excluded_prefixes=custom_excluded)
        
        assert selector._is_valid_page_title("Regular Article") is True
        assert selector._is_valid_page_title("List of countries") is False
        assert selector._is_valid_page_title("Timeline of events") is False
        assert selector._is_valid_page_title("Category:Test") is True  # Not in custom exclusions
    
    @patch('requests.get')
    def test_get_random_pages_success(self, mock_get):
        """Test successful random page fetching."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "query": {
                "random": [
                    {"title": "Page 1"},
                    {"title": "Page 2"},
                    {"title": "Page 3"}
                ]
            }
        }
        mock_get.return_value = mock_response
        
        selector = WikipediaPageSelector()
        pages = selector.get_random_pages(count=3)
        
        assert pages == ["Page 1", "Page 2", "Page 3"]
        mock_get.assert_called_once()
        
        # Verify API call parameters
        call_args = mock_get.call_args
        assert call_args[1]["params"]["action"] == "query"
        assert call_args[1]["params"]["rnlimit"] == "3"
    
    @patch('requests.get')
    def test_get_random_pages_api_error(self, mock_get):
        """Test handling of API errors during random page fetching."""
        mock_get.side_effect = Exception("Network error")
        
        selector = WikipediaPageSelector()
        
        with pytest.raises(Exception, match="Network error"):
            selector.get_random_pages(count=5)
    
    @patch('requests.get')
    def test_get_random_pages_invalid_response(self, mock_get):
        """Test handling of invalid API response format."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"error": "Invalid response"}
        mock_get.return_value = mock_response
        
        selector = WikipediaPageSelector()
        
        with pytest.raises(Exception, match="Unexpected API response format"):
            selector.get_random_pages(count=5)
    
    @patch('requests.get')
    def test_has_outgoing_links_true(self, mock_get):
        """Test checking outgoing links when they exist."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "query": {
                "pages": {
                    "123": {
                        "links": [{"title": "Link 1"}, {"title": "Link 2"}]
                    }
                }
            }
        }
        mock_get.return_value = mock_response
        
        selector = WikipediaPageSelector()
        result = selector._has_outgoing_links("Test Page")
        
        assert result is True
    
    @patch('requests.get')
    def test_has_outgoing_links_false(self, mock_get):
        """Test checking outgoing links when they don't exist."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "query": {
                "pages": {
                    "123": {}  # No links key
                }
            }
        }
        mock_get.return_value = mock_response
        
        selector = WikipediaPageSelector()
        result = selector._has_outgoing_links("Test Page")
        
        assert result is False
    
    @patch('requests.get')
    def test_has_outgoing_links_api_error(self, mock_get):
        """Test handling of API errors when checking outgoing links."""
        mock_get.side_effect = Exception("Network error")
        
        selector = WikipediaPageSelector()
        result = selector._has_outgoing_links("Test Page")
        
        assert result is False  # Should return False on error
    
    @patch('requests.get')
    def test_has_incoming_links_true(self, mock_get):
        """Test checking incoming links when they exist."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "query": {
                "backlinks": [
                    {"title": "Page 1"},
                    {"title": "Page 2"}
                ]
            }
        }
        mock_get.return_value = mock_response
        
        selector = WikipediaPageSelector()
        result = selector._has_incoming_links("Test Page")
        
        assert result is True
    
    @patch('requests.get')
    def test_has_incoming_links_false(self, mock_get):
        """Test checking incoming links when they don't exist."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "query": {
                "backlinks": []  # Empty backlinks
            }
        }
        mock_get.return_value = mock_response
        
        selector = WikipediaPageSelector()
        result = selector._has_incoming_links("Test Page")
        
        assert result is False
    
    @patch('requests.get')
    def test_has_incoming_links_api_error(self, mock_get):
        """Test handling of API errors when checking incoming links."""
        mock_get.side_effect = Exception("Network error")
        
        selector = WikipediaPageSelector()
        result = selector._has_incoming_links("Test Page")
        
        assert result is False  # Should return False on error
    
    def test_find_valid_start_page_no_validation(self):
        """Test finding start page when validation is disabled."""
        config = LinkValidationConfig(require_outgoing_links=False)
        selector = WikipediaPageSelector(link_validation=config)
        
        candidates = ["Page 1", "Page 2", "Page 3"]
        result = selector._find_valid_start_page(candidates)
        
        assert result == "Page 1"  # Should return first candidate
    
    def test_find_valid_start_page_empty_candidates(self):
        """Test finding start page with empty candidates list."""
        selector = WikipediaPageSelector()
        
        result = selector._find_valid_start_page([])
        
        assert result is None
    
    @patch.object(WikipediaPageSelector, '_has_outgoing_links')
    def test_find_valid_start_page_with_validation(self, mock_has_links):
        """Test finding start page with validation enabled."""
        # Mock that second page has outgoing links
        mock_has_links.side_effect = [False, True, False]
        
        selector = WikipediaPageSelector()  # Default has validation enabled
        candidates = ["Page 1", "Page 2", "Page 3"]
        result = selector._find_valid_start_page(candidates)
        
        assert result == "Page 2"
        assert mock_has_links.call_count == 2  # Should stop after finding valid page
    
    @patch.object(WikipediaPageSelector, '_has_outgoing_links')
    def test_find_valid_start_page_none_valid(self, mock_has_links):
        """Test finding start page when none are valid."""
        mock_has_links.return_value = False
        
        selector = WikipediaPageSelector()
        candidates = ["Page 1", "Page 2"]
        result = selector._find_valid_start_page(candidates)
        
        assert result is None
    
    def test_find_valid_target_page_no_validation(self):
        """Test finding target page when validation is disabled."""
        config = LinkValidationConfig(require_incoming_links=False)
        selector = WikipediaPageSelector(link_validation=config)
        
        candidates = ["Page 1", "Page 2", "Page 3"]
        result = selector._find_valid_target_page(candidates, exclude_page="Page 1")
        
        assert result == "Page 2"  # Should return first non-excluded candidate
    
    def test_find_valid_target_page_excludes_start_page(self):
        """Test that target page finder excludes the start page."""
        config = LinkValidationConfig(require_incoming_links=False)
        selector = WikipediaPageSelector(link_validation=config)
        
        candidates = ["Start Page", "Target Page"]
        result = selector._find_valid_target_page(candidates, exclude_page="Start Page")
        
        assert result == "Target Page"
    
    def test_find_valid_target_page_no_available_candidates(self):
        """Test finding target page when all candidates are excluded."""
        selector = WikipediaPageSelector()
        
        candidates = ["Page 1"]
        result = selector._find_valid_target_page(candidates, exclude_page="Page 1")
        
        assert result is None
    
    @patch.object(WikipediaPageSelector, '_has_incoming_links')
    def test_find_valid_target_page_with_validation(self, mock_has_links):
        """Test finding target page with validation enabled."""
        # Mock that third page has incoming links
        mock_has_links.side_effect = [False, True]
        
        selector = WikipediaPageSelector()  # Default has validation enabled
        candidates = ["Start", "Page 1", "Page 2"]
        result = selector._find_valid_target_page(candidates, exclude_page="Start")
        
        assert result == "Page 2"
        assert mock_has_links.call_count == 2
    
    @patch.object(WikipediaPageSelector, 'get_random_pages')
    @patch.object(WikipediaPageSelector, '_find_valid_start_page')
    @patch.object(WikipediaPageSelector, '_find_valid_target_page')
    def test_select_page_pair_success(self, mock_find_target, mock_find_start, mock_get_random):
        """Test successful page pair selection."""
        mock_get_random.return_value = ["Category:Invalid", "Valid Start", "Valid Target", "File:Invalid"]
        mock_find_start.return_value = "Valid Start"
        mock_find_target.return_value = "Valid Target"
        
        selector = WikipediaPageSelector()
        result = selector.select_page_pair()
        
        assert result is not None
        assert result.start_page == "Valid Start"
        assert result.target_page == "Valid Target"
        
        # Verify method calls
        mock_get_random.assert_called_once_with(count=20)
        mock_find_start.assert_called_once_with(["Valid Start", "Valid Target"])
        mock_find_target.assert_called_once_with(["Valid Start", "Valid Target"], exclude_page="Valid Start")
    
    @patch.object(WikipediaPageSelector, 'get_random_pages')
    def test_select_page_pair_insufficient_valid_pages(self, mock_get_random):
        """Test page pair selection when not enough valid pages are found."""
        # Return only invalid pages
        mock_get_random.return_value = ["Category:Invalid", "File:Invalid"]
        
        selector = WikipediaPageSelector(max_retries=1)
        result = selector.select_page_pair()
        
        assert result is None
    
    @patch.object(WikipediaPageSelector, 'get_random_pages')
    @patch.object(WikipediaPageSelector, '_find_valid_start_page')
    def test_select_page_pair_no_valid_start_page(self, mock_find_start, mock_get_random):
        """Test page pair selection when no valid start page is found."""
        mock_get_random.return_value = ["Page 1", "Page 2", "Page 3"]
        mock_find_start.return_value = None  # No valid start page
        
        selector = WikipediaPageSelector(max_retries=1)
        result = selector.select_page_pair()
        
        assert result is None
    
    @patch.object(WikipediaPageSelector, 'get_random_pages')
    @patch.object(WikipediaPageSelector, '_find_valid_start_page')
    @patch.object(WikipediaPageSelector, '_find_valid_target_page')
    def test_select_page_pair_no_valid_target_page(self, mock_find_target, mock_find_start, mock_get_random):
        """Test page pair selection when no valid target page is found."""
        mock_get_random.return_value = ["Page 1", "Page 2"]
        mock_find_start.return_value = "Page 1"
        mock_find_target.return_value = None  # No valid target page
        
        selector = WikipediaPageSelector(max_retries=1)
        result = selector.select_page_pair()
        
        assert result is None
    
    @patch.object(WikipediaPageSelector, 'get_random_pages')
    def test_select_page_pair_retries_on_failure(self, mock_get_random):
        """Test that page pair selection retries on failure."""
        # First two calls return insufficient valid pages, third call succeeds
        mock_get_random.side_effect = [
            ["Category:Invalid", "File:Invalid"],  # First attempt: no valid pages after filtering  
            ["Template:Invalid"],  # Second attempt: still no valid pages
            ["Valid Start", "Valid Target", "Extra Page"]  # Third attempt: success
        ]
        
        # Disable link validation to avoid API calls
        config = LinkValidationConfig(
            require_outgoing_links=False,
            require_incoming_links=False
        )
        selector = WikipediaPageSelector(max_retries=3, link_validation=config)
        result = selector.select_page_pair()
        
        # Should succeed on third attempt
        assert result is not None
        assert result.start_page == "Valid Start"
        assert result.target_page == "Valid Target" 
        assert mock_get_random.call_count == 3
    
    @patch.object(WikipediaPageSelector, 'get_random_pages')
    def test_select_page_pair_exception_handling(self, mock_get_random):
        """Test exception handling during page pair selection."""
        mock_get_random.side_effect = Exception("API Error")
        
        selector = WikipediaPageSelector(max_retries=1)
        result = selector.select_page_pair()
        
        assert result is None
    
    @pytest.mark.asyncio
    @patch.object(WikipediaPageSelector, 'select_page_pair')
    async def test_select_page_pair_async(self, mock_select_sync):
        """Test async version of page pair selection."""
        expected_pair = PagePair("Start", "Target")
        mock_select_sync.return_value = expected_pair
        
        selector = WikipediaPageSelector()
        result = await selector.select_page_pair_async()
        
        assert result == expected_pair
        mock_select_sync.assert_called_once()


class TestConvenienceFunctions:
    """Test the convenience functions for page selection."""
    
    @patch.object(WikipediaPageSelector, 'select_page_pair')
    def test_get_random_page_pair_sync(self, mock_select):
        """Test synchronous convenience function."""
        expected_pair = PagePair("Start", "Target")
        mock_select.return_value = expected_pair
        
        result = get_random_page_pair(
            language="de",
            max_retries=5,
            excluded_prefixes={"Custom:"}
        )
        
        assert result == expected_pair
        mock_select.assert_called_once()
    
    @pytest.mark.asyncio
    @patch.object(WikipediaPageSelector, 'select_page_pair_async')
    async def test_get_random_page_pair_async(self, mock_select_async):
        """Test asynchronous convenience function."""
        expected_pair = PagePair("Start", "Target")
        mock_select_async.return_value = expected_pair
        
        result = await get_random_page_pair_async(
            language="fr",
            max_retries=10,
            excluded_prefixes={"Special:"}
        )
        
        assert result == expected_pair
        mock_select_async.assert_called_once()
    
    @patch.object(WikipediaPageSelector, 'select_page_pair')
    def test_get_random_page_pair_with_link_validation(self, mock_select):
        """Test convenience function with link validation config."""
        expected_pair = PagePair("Start", "Target")
        mock_select.return_value = expected_pair
        
        link_config = LinkValidationConfig(
            require_outgoing_links=True,
            min_outgoing_links=5
        )
        
        result = get_random_page_pair(link_validation=link_config)
        
        assert result == expected_pair
        mock_select.assert_called_once()


class TestEdgeCasesAndErrorScenarios:
    """Test edge cases and error scenarios."""
    
    def test_selector_with_empty_excluded_prefixes(self):
        """Test selector with empty excluded prefixes set."""
        selector = WikipediaPageSelector(excluded_prefixes=set())
        
        # All page types should be valid now
        assert selector._is_valid_page_title("Category:Test") is True
        assert selector._is_valid_page_title("File:Image.jpg") is True
        assert selector._is_valid_page_title("Template:Test") is True
    
    def test_selector_with_none_excluded_prefixes(self):
        """Test that None excluded_prefixes gets replaced with defaults."""
        selector = WikipediaPageSelector(excluded_prefixes=None)
        
        # Should use default exclusions
        assert len(selector.excluded_prefixes) > 0
        assert "Category:" in selector.excluded_prefixes
    
    @patch('requests.get')
    def test_api_timeout_handling(self, mock_get):
        """Test handling of API timeouts."""
        import requests
        mock_get.side_effect = requests.Timeout("Request timed out")
        
        selector = WikipediaPageSelector()
        
        with pytest.raises(Exception, match="Wikipedia API request failed"):
            selector.get_random_pages()
    
    @patch('requests.get')
    def test_api_http_error_handling(self, mock_get):
        """Test handling of HTTP errors from API."""
        import requests
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = mock_response
        
        selector = WikipediaPageSelector()
        
        with pytest.raises(Exception, match="Wikipedia API request failed"):
            selector.get_random_pages()
    
    def test_find_page_with_unicode_titles(self):
        """Test handling of Unicode page titles."""
        selector = WikipediaPageSelector()
        
        unicode_titles = ["Café", "München", "北京", "🌟 Star Page"]
        
        for title in unicode_titles:
            # Should not throw exceptions with Unicode
            result = selector._is_valid_page_title(title)
            assert isinstance(result, bool)
    
    @patch.object(WikipediaPageSelector, 'get_random_pages')
    def test_max_retries_exhausted(self, mock_get_random):
        """Test behavior when max retries are exhausted."""
        # Always return insufficient valid pages
        mock_get_random.return_value = ["Category:Invalid"]
        
        selector = WikipediaPageSelector(max_retries=2)
        result = selector.select_page_pair()
        
        assert result is None
        assert mock_get_random.call_count == 2  # Should retry exactly max_retries times
    
    def test_concurrent_access_thread_safety(self):
        """Test that multiple selectors can work concurrently."""
        import threading
        import time
        
        results = []
        errors = []
        
        def select_page():
            try:
                with patch.object(WikipediaPageSelector, 'get_random_pages') as mock_get, \
                     patch.object(WikipediaPageSelector, '_find_valid_start_page') as mock_start, \
                     patch.object(WikipediaPageSelector, '_find_valid_target_page') as mock_target:
                    
                    mock_get.return_value = ["Page1", "Page2"]
                    mock_start.return_value = "Page1"
                    mock_target.return_value = "Page2"
                    
                    selector = WikipediaPageSelector()
                    result = selector.select_page_pair()
                    results.append(result)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = [threading.Thread(target=select_page) for _ in range(5)]
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 5
        assert all(result is not None for result in results)


class TestLinkValidationIntegration:
    """Test integration of link validation with page selection."""
    
    @patch.object(WikipediaPageSelector, 'get_random_pages')
    @patch.object(WikipediaPageSelector, '_has_outgoing_links')
    @patch.object(WikipediaPageSelector, '_has_incoming_links')
    def test_full_validation_enabled(self, mock_incoming, mock_outgoing, mock_get_random):
        """Test page selection with full link validation enabled."""
        mock_get_random.return_value = ["Page1", "Page2", "Page3"]
        mock_outgoing.side_effect = [False, True, False]  # Page2 has outgoing links
        # For target selection, check Page1 first (excluded Page2), then Page3
        mock_incoming.side_effect = [False, True]  # Page1 no links, Page3 has links
        
        config = LinkValidationConfig(
            require_outgoing_links=True,
            require_incoming_links=True
        )
        selector = WikipediaPageSelector(link_validation=config)
        result = selector.select_page_pair()
        
        assert result is not None
        assert result.start_page == "Page2"  # Has outgoing links
        assert result.target_page == "Page3"  # Has incoming links
    
    @patch.object(WikipediaPageSelector, 'get_random_pages')
    def test_validation_disabled(self, mock_get_random):
        """Test page selection with all validation disabled."""
        mock_get_random.return_value = ["Page1", "Page2"]
        
        config = LinkValidationConfig(
            require_outgoing_links=False,
            require_incoming_links=False
        )
        selector = WikipediaPageSelector(link_validation=config)
        result = selector.select_page_pair()
        
        assert result is not None
        assert result.start_page == "Page1"  # First page, no validation
        assert result.target_page == "Page2"  # Second page, no validation


if __name__ == "__main__":
    pytest.main([__file__]) 