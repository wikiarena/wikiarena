from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from wikiarena.server.config import ServerConfig
from wikiarena.server.errors import GraphNotReadyError, UnknownTitleError
from wikiarena.server.graph_runtime import GraphSolverRuntime, SolverRuntime
from wikiarena.server.models import ErrorResponse
from wikiarena.server.routers.health import router as health_router
from wikiarena.server.routers.meta import router as meta_router
from wikiarena.server.routers.random_page_titles import (
    router as random_page_titles_router,
)
from wikiarena.server.routers.solve import router as solve_router

logger = logging.getLogger(
    __name__,
)


def create_app(
    *,
    config: ServerConfig | None = None,
    runtime: SolverRuntime | None = None,
) -> FastAPI:
    resolved_config = config if config is not None else ServerConfig.from_env()
    resolved_runtime = (
        runtime
        if runtime is not None
        else GraphSolverRuntime(
            resolved_config,
        )
    )

    @asynccontextmanager
    async def lifespan(
        app: FastAPI,
    ):
        app.state.runtime = resolved_runtime
        await resolved_runtime.startup()
        yield
        await resolved_runtime.shutdown()

    app = FastAPI(
        title="WikiArena Solver API",
        version=resolved_config.service_version,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(
            resolved_config.cors_origins,
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(
        health_router,
    )
    app.include_router(
        meta_router,
    )
    app.include_router(
        random_page_titles_router,
    )
    app.include_router(
        solve_router,
    )

    _register_exception_handlers(
        app,
    )

    return app


def _register_exception_handlers(
    app: FastAPI,
) -> None:
    @app.exception_handler(
        GraphNotReadyError,
    )
    async def handle_graph_not_ready(
        request: Request,
        exc: GraphNotReadyError,
    ) -> JSONResponse:
        del request
        del exc
        return _error_response(
            status_code=503,
            code="graph_not_ready",
            message="Graph is not ready.",
        )

    @app.exception_handler(
        UnknownTitleError,
    )
    async def handle_unknown_title(
        request: Request,
        exc: UnknownTitleError,
    ) -> JSONResponse:
        del request
        title_role_prefix = exc.title_role.casefold()
        if title_role_prefix == "start":
            return _error_response(
                status_code=404,
                code="start_title_not_found",
                message="Start title was not found in the loaded graph snapshot.",
            )
        return _error_response(
            status_code=404,
            code="target_title_not_found",
            message="Target title was not found in the loaded graph snapshot.",
        )

    @app.exception_handler(
        RequestValidationError,
    )
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del request
        logger.debug(
            "Invalid solver API request: %s",
            exc,
        )
        return _error_response(
            status_code=422,
            code="invalid_request",
            message="Invalid request body.",
        )

    @app.exception_handler(
        Exception,
    )
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception(
            "Unhandled exception for %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return _error_response(
            status_code=500,
            code="internal_error",
            message="Internal server error.",
        )


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            code=code,
            message=message,
        ).model_dump(),
    )


app = create_app()
