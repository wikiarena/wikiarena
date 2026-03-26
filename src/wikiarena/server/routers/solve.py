from __future__ import annotations

from fastapi import APIRouter, Depends

from wikiarena.server.dependencies import get_runtime
from wikiarena.server.graph_runtime import SolverRuntime
from wikiarena.server.models import SolveRequest, SolveResponse

router = APIRouter()


@router.post(
    "/v1/solve",
    response_model=SolveResponse,
)
async def solve_path(
    solve_request: SolveRequest,
    runtime: SolverRuntime = Depends(
        get_runtime,
    ),
) -> SolveResponse:
    return await runtime.solve(
        start_title=solve_request.start_title,
        target_title=solve_request.target_title,
    )
