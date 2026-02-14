from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ChallengeManifestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    platform: str
    platform_challenge_id: str
    name: str
    category: str
    points: int
    description_md: str
    description_raw: str | None = None
    artifacts: list[dict]
    remote_endpoints: list[dict]
    local_deploy_hints: dict
    flag_regex: str | None = None
    synced_at: datetime


class ChallengeListResponse(BaseModel):
    items: list[ChallengeManifestRead]
