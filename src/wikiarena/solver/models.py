"""
Solver models for path finding functionality.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Annotated


class SolverRequest(BaseModel):
    """Request model for shortest path finding."""
    start_page: Annotated[str, Field(min_length=1)] = Field(..., description="Starting Wikipedia page title")
    target_page: Annotated[str, Field(min_length=1)] = Field(..., description="Target Wikipedia page title")
    

class SolverResponse(BaseModel):
    """Response model for shortest path finding results."""
    paths: List[List[str]] = Field(..., description="Shortest paths from start to target page, list of paths, each path is a list of page titles")
    path_length: int = Field(..., description="Number of steps in the shortest paths (all returned paths will have this length)")
    computation_time_ms: float = Field(..., description="Time taken to compute the path in milliseconds") 