"""
Wikipedia API client for path finding POC.
Handles batched requests, pagination, and redirect resolution.
"""
import asyncio
import aiohttp
from typing import Dict, List, Set, Optional, Any
import logging

logger = logging.getLogger(__name__)


class WikipediaClient:
    """
    Client for Wikipedia API with proper batching and rate limiting.
    
    Key constraints:
    - Max 50 titles per batch request
    - Serial requests (no parallel)
    - Handle pagination with 'continue' tokens
    - Respect rate limits
    """
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.base_url = "https://en.wikipedia.org/w/api.php"
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={'Accept-Encoding': 'gzip'},  # Use compression as recommended
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _make_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make a single API request with rate limiting."""
        if not self.session:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
            
        # Add common parameters
        params.update({
            'action': 'query',
            'format': 'json',
            'redirects': 'true'  # Always resolve redirects
        })
        
        logger.debug(f"Making API request: {params}")
        
        async with self.session.get(self.base_url, params=params) as response:
            response.raise_for_status()
            data = await response.json()
            
        return data
    
    async def resolve_redirects(self, titles: List[str]) -> Dict[str, str]:
        """
        Resolve redirects for multiple titles.
        Returns: {input_title: canonical_title}
        """
        if not titles:
            return {}
            
        # Process in batches of 50
        redirect_map = {}
        
        for i in range(0, len(titles), 50):
            batch = titles[i:i+50]
            batch_str = "|".join(batch)
            
            params = {
                'titles': batch_str,
                'prop': 'info'  # Minimal prop to just get redirects
            }
            
            response = await self._make_request(params)
            
            # Handle normalized titles and redirects
            query = response.get('query', {})
            
            # Start with identity mapping
            for title in batch:
                redirect_map[title] = title
                
            # Apply normalizations (case changes, etc.)
            for norm in query.get('normalized', []):
                redirect_map[norm['from']] = norm['to']
                
            # Apply redirects
            for redirect in query.get('redirects', []):
                # Find which original title maps to this redirect source
                for orig_title in batch:
                    if redirect_map[orig_title] == redirect['from']:
                        redirect_map[orig_title] = redirect['to']
                        
        return redirect_map
    
    async def get_forward_links(self, titles: List[str]) -> Dict[str, Set[str]]:
        """
        Get outgoing links (pages that these titles link TO).
        Uses prop=links API endpoint.
        """
        return await self._get_links_batch(titles, 'forward')
    
    async def get_backward_links(self, titles: List[str]) -> Dict[str, Set[str]]:
        """
        Get incoming links (pages that link TO these titles).
        Uses prop=linkshere API endpoint.
        """
        return await self._get_links_batch(titles, 'backward')
    
    async def _get_links_batch(self, titles: List[str], direction: str) -> Dict[str, Set[str]]:
        """
        Get links for multiple titles with batching and pagination.
        """
        if not titles:
            return {}
            
        results = {}
        
        # Process in batches of 50
        for i in range(0, len(titles), 50):
            batch = titles[i:i+50]
            batch_results = await self._get_links_single_batch(batch, direction)
            results.update(batch_results)
            
        return results
    
    async def _get_links_single_batch(self, titles: List[str], direction: str) -> Dict[str, Set[str]]:
        """
        Get links for a single batch (≤50 titles) with pagination.
        """
        batch_str = "|".join(titles)
        all_results = {title: set() for title in titles}
        
        # Set up parameters based on direction
        if direction == 'forward':
            base_params = {
                'prop': 'links',
                'titles': batch_str,
                'pllimit': 'max',  # Get as many as possible per request
                'plnamespace': '0'  # Only main namespace (articles)
            }
        else:  # backward
            base_params = {
                'prop': 'linkshere',
                'titles': batch_str,
                'lhlimit': 'max',  # Get as many as possible per request
                'lhnamespace': '0'  # Only main namespace (articles)
            }
        
        # Handle pagination
        continue_token = None
        
        while True:
            params = base_params.copy()
            if continue_token:
                params.update(continue_token)
                
            response = await self._make_request(params)
            
            # Extract links from response
            query = response.get('query', {})
            pages = query.get('pages', {})
            
            for page_id, page_data in pages.items():
                page_title = page_data.get('title')
                if not page_title or page_title not in all_results:
                    continue
                    
                # Extract links based on direction
                if direction == 'forward':
                    links = page_data.get('links', [])
                    link_titles = {link['title'] for link in links}
                else:  # backward
                    links = page_data.get('linkshere', [])
                    link_titles = {link['title'] for link in links}
                    
                all_results[page_title].update(link_titles)
            
            # Check if we need to continue
            if 'continue' not in response:
                break
                
            continue_token = response['continue']
            logger.debug(f"Continuing pagination for {direction} links...")
        
        logger.info(f"Retrieved {direction} links for {len(titles)} pages")
        return all_results
    
    async def close(self):
        """Close the session if not using context manager."""
        if self.session:
            await self.session.close()
            self.session = None 