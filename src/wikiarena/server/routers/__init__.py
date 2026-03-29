from wikiarena.server.routers.health import router as health_router
from wikiarena.server.routers.meta import router as meta_router
from wikiarena.server.routers.random_page_titles import (
    router as random_page_titles_router,
)
from wikiarena.server.routers.solve import router as solve_router

__all__ = [
    "health_router",
    "meta_router",
    "random_page_titles_router",
    "solve_router",
]
