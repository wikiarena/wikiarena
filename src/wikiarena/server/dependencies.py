from __future__ import annotations

from fastapi import Request

from wikiarena.server.graph_runtime import SolverRuntime


def get_runtime(
    request: Request,
) -> SolverRuntime:
    return request.app.state.runtime
