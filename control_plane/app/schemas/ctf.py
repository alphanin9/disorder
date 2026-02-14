from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CTFRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    platform: str | None = None
    default_flag_regex: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class CTFListResponse(BaseModel):
    items: list[CTFRead]


class CTFCreateRequest(BaseModel):
    name: str
    slug: str
    platform: str | None = None
    default_flag_regex: str | None = r"flag\{.*?\}"
    notes: str | None = None


class CTFUpdateRequest(BaseModel):
    name: str | None = None
    slug: str | None = None
    platform: str | None = None
    default_flag_regex: str | None = None
    notes: str | None = None
