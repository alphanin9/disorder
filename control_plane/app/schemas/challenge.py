from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChallengeManifestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ctf_id: UUID
    ctf_name: str | None = None
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


class ChallengeArtifactRead(BaseModel):
    name: str
    sha256: str
    size_bytes: int
    object_key: str


class ChallengeCreateRequest(BaseModel):
    ctf_id: UUID
    name: str
    category: str = "misc"
    points: int = 0
    description_md: str = ""
    description_raw: str | None = None
    platform: str = "manual"
    platform_challenge_id: str | None = None
    artifacts: list[ChallengeArtifactRead] = Field(default_factory=list)
    remote_endpoints: list[dict] = Field(default_factory=list)
    local_deploy_hints: dict = Field(default_factory=lambda: {"compose_present": False, "notes": None})
    flag_regex: str | None = None


class ChallengeUpdateRequest(BaseModel):
    ctf_id: UUID | None = None
    name: str | None = None
    category: str | None = None
    points: int | None = None
    description_md: str | None = None
    description_raw: str | None = None
    artifacts: list[ChallengeArtifactRead] | None = None
    remote_endpoints: list[dict] | None = None
    local_deploy_hints: dict | None = None
    flag_regex: str | None = None
