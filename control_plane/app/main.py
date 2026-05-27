from contextlib import asynccontextmanager
import asyncio
import time

from fastapi import FastAPI

from control_plane.app.api.router import api_router
from control_plane.app.core.config import get_settings
from control_plane.app.db.session import SessionLocal
from control_plane.app.services.auth_service import check_codex_auth_health
from control_plane.app.store import get_blob_store

settings = get_settings()


async def _codex_auth_health_loop() -> None:
    interval = max(60, settings.codex_auth_health_check_interval_seconds)
    while True:
        await asyncio.sleep(interval)
        try:
            def _check() -> None:
                with SessionLocal() as db:
                    check_codex_auth_health(db)

            await asyncio.to_thread(_check)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Health state is advisory; API status and explicit checks still surface errors.
            continue


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
    codex_auth_health_task = asyncio.create_task(_codex_auth_health_loop())
    yield
    codex_auth_health_task.cancel()
    try:
        await codex_auth_health_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(api_router)
