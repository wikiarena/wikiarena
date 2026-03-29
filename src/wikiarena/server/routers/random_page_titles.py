from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from wikiarena.server.dependencies import get_runtime
from wikiarena.server.graph_runtime import SolverRuntime
from wikiarena.server.models import RandomPageTitlesResponse

router = APIRouter()


@router.get(
    "/v1/random-page-titles",
    response_model=RandomPageTitlesResponse,
)
async def get_random_page_titles(
    count: Annotated[int, Query(ge=1, le=500)] = 200,
    runtime: SolverRuntime = Depends(
        get_runtime,
    ),
) -> RandomPageTitlesResponse:
    return await runtime.random_page_titles(
        count=count,
    )
