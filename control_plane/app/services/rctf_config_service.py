from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.app.db.models import CTFIntegrationConfig

# Reuse the shared cipher and base-url helpers from the CTFd config service so
# both providers encrypt secrets with the same derived key.
from control_plane.app.services.ctfd_config_service import (
    _build_cipher,
    _normalize_base_url,
)

RCTF_PROVIDER = "rctf"

# rCTF authenticates with a single long-lived team token, so there is exactly
# one auth mode (unlike CTFd's api_token/session_cookie pair).
RCTF_AUTH_MODE = "team_token"


@dataclass(slots=True)
class RCTFAuthMaterial:
    base_url: str
    mode: str
    secret: str


def _encrypt_secret(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return _build_cipher().encrypt(normalized.encode("utf-8")).decode("utf-8")


def _decrypt_secret(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    from cryptography.fernet import InvalidToken

    try:
        return _build_cipher().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def _row_query(ctf_id: UUID | str):
    return select(CTFIntegrationConfig).where(
        CTFIntegrationConfig.ctf_id == ctf_id,
        CTFIntegrationConfig.provider == RCTF_PROVIDER,
    )


def _load_row(db: Session, ctf_id: UUID | str) -> CTFIntegrationConfig | None:
    return db.execute(_row_query(ctf_id)).scalar_one_or_none()


def _get_or_create_row(db: Session, ctf_id: UUID | str) -> CTFIntegrationConfig:
    row = _load_row(db, ctf_id)
    if row is None:
        row = CTFIntegrationConfig(ctf_id=ctf_id, provider=RCTF_PROVIDER, config_json={})
        db.add(row)
        db.flush()
    return row


def _safe_payload(row: CTFIntegrationConfig | None) -> dict[str, Any]:
    if row is None or not isinstance(row.config_json, dict):
        return {}
    return dict(row.config_json)


def get_rctf_config_response(db: Session, ctf_id: UUID | str) -> dict[str, Any]:
    row = _load_row(db, ctf_id)
    payload = _safe_payload(row)
    base_url = str(payload.get("base_url") or "")
    has_team_token = bool(payload.get("team_token_encrypted"))
    return {
        "base_url": base_url,
        "configured": bool(base_url and has_team_token),
        "has_team_token": has_team_token,
        "api_version": payload.get("api_version"),
        "last_submit_status": payload.get("last_submit_status"),
        "updated_at": row.updated_at if row is not None else None,
    }


def get_rctf_decrypted_credentials(db: Session, ctf_id: UUID | str) -> dict[str, Any] | None:
    row = _load_row(db, ctf_id)
    if row is None:
        return None
    payload = _safe_payload(row)
    base_url = _normalize_base_url(payload.get("base_url"))
    if not base_url:
        return None
    return {
        "base_url": base_url,
        "team_token": _decrypt_secret(payload.get("team_token_encrypted")),
    }


def upsert_rctf_config(
    db: Session,
    *,
    ctf_id: UUID | str,
    base_url: str | None = None,
    team_token: str | None = None,
    api_version: str | None = None,
    clear_team_token: bool = False,
) -> CTFIntegrationConfig:
    row = _get_or_create_row(db, ctf_id)
    payload = _safe_payload(row)

    normalized_base_url = _normalize_base_url(base_url)
    if normalized_base_url is not None:
        payload["base_url"] = normalized_base_url

    if api_version:
        # Remember which challenge API last served this CTF (e.g. "v2").
        payload["api_version"] = api_version

    if clear_team_token:
        payload.pop("team_token_encrypted", None)
    elif team_token is not None:
        encrypted = _encrypt_secret(team_token)
        if encrypted:
            payload["team_token_encrypted"] = encrypted

    row.config_json = json.loads(json.dumps(payload))
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def clear_rctf_team_token(db: Session, *, ctf_id: UUID | str) -> dict[str, Any]:
    row = _load_row(db, ctf_id)
    if row is None:
        return get_rctf_config_response(db, ctf_id)
    payload = _safe_payload(row)
    payload.pop("team_token_encrypted", None)
    row.config_json = json.loads(json.dumps(payload))
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    return get_rctf_config_response(db, ctf_id)


def mark_rctf_submit_result(
    db: Session,
    *,
    ctf_id: UUID | str,
    auth_mode: str | None,
    status: str,
    commit: bool = True,
) -> None:
    row = _load_row(db, ctf_id)
    if row is None:
        return
    payload = _safe_payload(row)
    if auth_mode == RCTF_AUTH_MODE:
        payload["last_submit_auth_mode"] = auth_mode
    payload["last_submit_status"] = status
    payload["last_submit_at"] = datetime.now(timezone.utc).isoformat()
    row.config_json = json.loads(json.dumps(payload))
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    if commit:
        db.commit()


def resolve_rctf_auth_candidates(
    db: Session,
    *,
    ctf_id: UUID | str,
) -> list[RCTFAuthMaterial]:
    creds = get_rctf_decrypted_credentials(db, ctf_id)
    if not creds:
        return []
    base_url = str(creds.get("base_url") or "").strip()
    team_token = str(creds.get("team_token") or "").strip()
    if not base_url or not team_token:
        return []
    return [RCTFAuthMaterial(base_url=base_url, mode=RCTF_AUTH_MODE, secret=team_token)]
