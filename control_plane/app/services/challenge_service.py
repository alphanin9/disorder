from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from control_plane.app.db.models import CTFEvent, ChallengeManifest
from control_plane.app.schemas.challenge import ChallengeCreateRequest, ChallengeUpdateRequest
from control_plane.app.schemas.ctf import CTFCreateRequest, CTFUpdateRequest


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,127}$")


def _normalize_slug(value: str) -> str:
    slug = value.strip().lower().replace("_", "-")
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def list_ctfs(db: Session) -> list[CTFEvent]:
    return db.execute(select(CTFEvent).order_by(CTFEvent.created_at.desc())).scalars().all()


def get_ctf_or_none(db: Session, ctf_id: str) -> CTFEvent | None:
    return db.get(CTFEvent, ctf_id)


def create_ctf(db: Session, request: CTFCreateRequest) -> CTFEvent:
    slug = _normalize_slug(request.slug)
    if not slug or not SLUG_RE.fullmatch(slug):
        raise ValueError("Invalid CTF slug")

    existing = db.execute(select(CTFEvent).where(CTFEvent.slug == slug)).scalar_one_or_none()
    if existing is not None:
        raise ValueError("CTF slug already exists")

    event = CTFEvent(
        name=request.name,
        slug=slug,
        platform=request.platform,
        default_flag_regex=request.default_flag_regex,
        notes=request.notes,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def update_ctf(db: Session, ctf: CTFEvent, request: CTFUpdateRequest) -> CTFEvent:
    fields_set = request.model_fields_set

    if "name" in fields_set:
        if request.name is None:
            raise ValueError("CTF name cannot be null")
        ctf.name = request.name
    if "slug" in fields_set:
        if request.slug is None:
            raise ValueError("CTF slug cannot be null")
        slug = _normalize_slug(request.slug)
        if not slug or not SLUG_RE.fullmatch(slug):
            raise ValueError("Invalid CTF slug")
        existing = db.execute(select(CTFEvent).where(CTFEvent.slug == slug, CTFEvent.id != ctf.id)).scalar_one_or_none()
        if existing is not None:
            raise ValueError("CTF slug already exists")
        ctf.slug = slug
    if "platform" in fields_set:
        ctf.platform = request.platform
    if "default_flag_regex" in fields_set:
        ctf.default_flag_regex = request.default_flag_regex
    if "notes" in fields_set:
        ctf.notes = request.notes

    ctf.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ctf)
    return ctf


def list_challenges(db: Session, ctf_id: str | None = None) -> list[ChallengeManifest]:
    stmt = select(ChallengeManifest).options(joinedload(ChallengeManifest.ctf)).order_by(ChallengeManifest.synced_at.desc())
    if ctf_id is not None:
        stmt = stmt.where(ChallengeManifest.ctf_id == ctf_id)
    return db.execute(stmt).scalars().all()


def get_challenge_or_none(db: Session, challenge_id: str) -> ChallengeManifest | None:
    stmt = select(ChallengeManifest).options(joinedload(ChallengeManifest.ctf)).where(ChallengeManifest.id == challenge_id)
    return db.execute(stmt).scalar_one_or_none()


def create_challenge(db: Session, request: ChallengeCreateRequest) -> ChallengeManifest:
    ctf = db.get(CTFEvent, request.ctf_id)
    if ctf is None:
        raise ValueError("CTF not found")

    platform_challenge_id = request.platform_challenge_id or str(uuid4())

    existing = db.execute(
        select(ChallengeManifest).where(
            ChallengeManifest.ctf_id == ctf.id,
            ChallengeManifest.platform == request.platform,
            ChallengeManifest.platform_challenge_id == platform_challenge_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("platform/platform_challenge_id already exists")

    artifacts_payload = [artifact.model_dump() for artifact in request.artifacts]

    challenge = ChallengeManifest(
        ctf_id=ctf.id,
        platform=request.platform,
        platform_challenge_id=platform_challenge_id,
        name=request.name,
        category=request.category,
        points=request.points,
        description_md=request.description_md,
        description_raw=request.description_raw,
        artifacts=artifacts_payload,
        remote_endpoints=request.remote_endpoints,
        local_deploy_hints=request.local_deploy_hints,
        flag_regex=request.flag_regex,
        synced_at=datetime.now(timezone.utc),
    )
    db.add(challenge)
    db.commit()

    refreshed = get_challenge_or_none(db, str(challenge.id))
    assert refreshed is not None
    return refreshed


def update_challenge(db: Session, challenge: ChallengeManifest, request: ChallengeUpdateRequest) -> ChallengeManifest:
    fields_set = request.model_fields_set

    if "ctf_id" in fields_set:
        if request.ctf_id is None:
            raise ValueError("ctf_id cannot be null")
        ctf = db.get(CTFEvent, request.ctf_id)
        if ctf is None:
            raise ValueError("CTF not found")
        challenge.ctf_id = ctf.id

    if "name" in fields_set:
        if request.name is None:
            raise ValueError("challenge name cannot be null")
        challenge.name = request.name
    if "category" in fields_set:
        if request.category is None:
            raise ValueError("challenge category cannot be null")
        challenge.category = request.category
    if "points" in fields_set:
        if request.points is None:
            raise ValueError("challenge points cannot be null")
        challenge.points = request.points
    if "description_md" in fields_set:
        if request.description_md is None:
            raise ValueError("challenge description_md cannot be null")
        challenge.description_md = request.description_md
    if "description_raw" in fields_set:
        challenge.description_raw = request.description_raw
    if "artifacts" in fields_set:
        challenge.artifacts = [artifact.model_dump() for artifact in request.artifacts] if request.artifacts is not None else []
    if "remote_endpoints" in fields_set:
        challenge.remote_endpoints = request.remote_endpoints
    if "local_deploy_hints" in fields_set:
        challenge.local_deploy_hints = request.local_deploy_hints
    if "flag_regex" in fields_set:
        challenge.flag_regex = request.flag_regex

    challenge.synced_at = datetime.now(timezone.utc)

    db.commit()
    refreshed = get_challenge_or_none(db, str(challenge.id))
    assert refreshed is not None
    return refreshed


def ensure_ctf_for_sync(db: Session, base_url: str) -> CTFEvent:
    host = base_url.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
    slug = _normalize_slug(f"ctfd-{host}")
    existing = db.execute(select(CTFEvent).where(CTFEvent.slug == slug)).scalar_one_or_none()
    if existing is not None:
        return existing

    event = CTFEvent(
        name=f"CTFd {host}",
        slug=slug,
        platform="ctfd",
        default_flag_regex=r"flag\{.*?\}",
        notes=f"Auto-created from CTFd sync source {base_url}",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
