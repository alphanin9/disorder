from fastapi import APIRouter

from control_plane.app.api.routes.auth import router as auth_router
from control_plane.app.api.routes.challenges import router as challenges_router
from control_plane.app.api.routes.ctfs import router as ctfs_router
from control_plane.app.api.routes.health import router as health_router
from control_plane.app.api.routes.integrations import router as integrations_router
from control_plane.app.api.routes.runs import router as runs_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(integrations_router)
api_router.include_router(auth_router)
api_router.include_router(ctfs_router)
api_router.include_router(challenges_router)
api_router.include_router(runs_router)
