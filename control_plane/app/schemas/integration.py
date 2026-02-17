from typing import Literal

from pydantic import BaseModel, HttpUrl


class CTFdSyncRequest(BaseModel):
    base_url: HttpUrl | None = None
    auth_mode: Literal["session_cookie", "api_token"] | None = None
    api_token: str | None = None
    session_cookie: str | None = None


class CTFdConfigResponse(BaseModel):
    base_url: str
    configured: bool
