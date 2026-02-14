from contextlib import asynccontextmanager
import time

from fastapi import FastAPI

from control_plane.app.api.router import api_router
from control_plane.app.core.config import get_settings
from control_plane.app.store import get_blob_store

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    last_error: Exception | None = None
    for _ in range(30):
        try:
            get_blob_store().ensure_bucket()
            last_error = None
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2)
    if last_error is not None:
        raise last_error
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(api_router)
