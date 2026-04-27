from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from wikiarena.server.dependencies import get_runtime
from wikiarena.server.graph_runtime import SolverRuntime
from wikiarena.server.models import TitleValidationResponse

router = APIRouter()


@router.get(
    "/v1/title-validation",
    response_model=TitleValidationResponse,
)
async def validate_title(
    title: Annotated[str, Query(min_length=1)],
    runtime: SolverRuntime = Depends(
        get_runtime,
    ),
) -> TitleValidationResponse:
    return await runtime.validate_title(
        title=title,
    )
