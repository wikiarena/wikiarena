from wikiarena.server.routers.health import router as health_router
from wikiarena.server.routers.meta import router as meta_router
from wikiarena.server.routers.solve import router as solve_router

__all__ = [
    "health_router",
    "meta_router",
    "solve_router",
]
