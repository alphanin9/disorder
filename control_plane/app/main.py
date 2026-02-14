from contextlib import asynccontextmanager

from fastapi import FastAPI

from control_plane.app.api.router import api_router
from control_plane.app.core.config import get_settings
from control_plane.app.store import get_blob_store

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_blob_store().ensure_bucket()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(api_router)
