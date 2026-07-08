from datetime import datetime
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


class CTFdSyncResponse(BaseModel):
    synced: int
    platform: str
    ctf_id: str
    ctf_slug: str
    auth_mode_used: Literal["session_cookie", "api_token"]
    stored_auth_modes: list[Literal["session_cookie", "api_token"]]


class CTFdPerCtfConfigResponse(BaseModel):
    base_url: str
    configured: bool
    preferred_auth_mode: Literal["session_cookie", "api_token"] | None = None
    has_api_token: bool
    has_session_cookie: bool
    stored_auth_modes: list[Literal["session_cookie", "api_token"]]
    last_sync_auth_mode: Literal["session_cookie", "api_token"] | None = None
    last_submit_auth_mode: Literal["session_cookie", "api_token"] | None = None
    last_submit_status: str | None = None
    updated_at: datetime | None = None


class RCTFSyncRequest(BaseModel):
    # base_url is required: it identifies which CTF (and thus which stored
    # team token) to use. Only team_token may be omitted on re-sync.
    base_url: HttpUrl
    team_token: str | None = None


class RCTFSyncResponse(BaseModel):
    synced: int
    platform: str
    # Challenge API version negotiated during the sync ("v1" or "v2").
    api_version: str | None = None
    ctf_id: str
    ctf_slug: str
    has_team_token: bool


class RCTFPerCtfConfigResponse(BaseModel):
    base_url: str
    configured: bool
    has_team_token: bool
    api_version: str | None = None
    last_submit_status: str | None = None
    updated_at: datetime | None = None
