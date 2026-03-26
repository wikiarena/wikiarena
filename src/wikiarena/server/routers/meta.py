from __future__ import annotations

from fastapi import APIRouter, Depends

from wikiarena.server.dependencies import get_runtime
from wikiarena.server.graph_runtime import SolverRuntime
from wikiarena.server.models import MetaResponse

router = APIRouter()


@router.get(
    "/v1/meta",
    response_model=MetaResponse,
)
async def get_meta(
    runtime: SolverRuntime = Depends(
        get_runtime,
    ),
) -> MetaResponse:
    return runtime.get_meta()
