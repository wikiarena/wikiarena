"""
Data models for Wikipedia path finding POC.
"""
from dataclasses import dataclass
from typing import Optional, Set, Dict
from collections import deque


@dataclass
class WikiPage:
    """Represents a Wikipedia page with its link data."""
    title: str  # Canonical title after redirect resolution
    outgoing_links: Optional[Set[str]] = None
    incoming_links: Optional[Set[str]] = None
    fetch_status: str = "not_fetched"  # "fetching", "completed", "error" # TODO(hunter): I don't think we need this anymore for sync search


@dataclass
class SearchState:
    """Tracks state for one direction of bidirectional search."""
    visited: Set[str]
    queue: deque[str]
    distances: Dict[str, int]
    parents: Dict[str, str]  # For path reconstruction
    direction: str  # "forward" or "backward"
    
    def __post_init__(self):
        """Ensure queue is a deque if passed as list."""
        if not isinstance(self.queue, deque):
            self.queue = deque(self.queue) 