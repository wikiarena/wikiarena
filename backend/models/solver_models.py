from pydantic import BaseModel, Field
from typing import List, Optional, Annotated
from datetime import datetime

class SolverRequest(BaseModel):
    start_page: Annotated[str, Field(min_length=1)] = Field(..., description="Starting Wikipedia page title")
    target_page: Annotated[str, Field(min_length=1)] = Field(..., description="Target Wikipedia page title")
    
class SolverResponse(BaseModel):
    paths: List[List[str]] = Field(..., description="Shortest paths from start to target page, list of paths, each path is a list of page titles")
    path_length: int = Field(..., description="Number of steps in the shortest paths (all returned paths will have this length)")
    computation_time_ms: float = Field(..., description="Time taken to compute the path in milliseconds")
    from_cache: bool = Field(..., description="Whether the result was served from cache") # Will always be False for now
    
class SolverStatus(BaseModel):
    database_ready: bool = Field(..., description="Whether the Wikipedia database is loaded")
    total_pages: Optional[int] = Field(None, description="Total number of pages in the database")
    total_links: Optional[int] = Field(None, description="Total number of links in the database")
    last_updated: Optional[datetime] = Field(None, description="When the database was last updated")
    # cache_size field removed as caching is currently disabled/being redesigned.

# PathCacheEntry class removed as it's no longer used by the solver service.
