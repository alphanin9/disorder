from pydantic import BaseModel, HttpUrl


class CTFdSyncRequest(BaseModel):
    base_url: HttpUrl | None = None
    api_token: str | None = None


class CTFdConfigResponse(BaseModel):
    base_url: str
    configured: bool
