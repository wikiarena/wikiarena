from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from wikiarena.server.dependencies import get_runtime
from wikiarena.server.graph_runtime import SolverRuntime
from wikiarena.server.models import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
)
async def health_check(
    runtime: SolverRuntime = Depends(
        get_runtime,
    ),
) -> JSONResponse:
    health_response = HealthResponse(
        status=runtime.get_health_status(),
    )
    return JSONResponse(
        status_code=200 if runtime.is_ready() else 503,
        content=health_response.model_dump(),
    )
