from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.app.core.config import get_settings
from control_plane.app.db.models import CTFIntegrationConfig

CTFD_PROVIDER = "ctfd"


@dataclass(slots=True)
class CTFdAuthMaterial:
    base_url: str
    mode: str
    secret: str


def _build_cipher() -> Fernet:
    settings = get_settings()
    configured_key = settings.codex_auth_encryption_key
    if configured_key:
        try:
            return Fernet(configured_key.encode("utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError("Invalid CODEX_AUTH_ENCRYPTION_KEY (expected Fernet key)") from exc

    digest = hashlib.sha256(f"{settings.app_name}:{settings.minio_secret_key}".encode("utf-8")).digest()
    derived_key = base64.urlsafe_b64encode(digest)
    return Fernet(derived_key)


def _encrypt_secret(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    cipher = _build_cipher()
    return cipher.encrypt(normalized.encode("utf-8")).decode("utf-8")


def _decrypt_secret(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    cipher = _build_cipher()
    try:
        return cipher.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def _normalize_base_url(base_url: str | None) -> str | None:
    if base_url is None:
        return None
    normalized = str(base_url).strip().rstrip("/")
    return normalized or None


def _row_query(ctf_id: UUID | str):
    return select(CTFIntegrationConfig).where(
        CTFIntegrationConfig.ctf_id == ctf_id,
        CTFIntegrationConfig.provider == CTFD_PROVIDER,
    )


def _load_row(db: Session, ctf_id: UUID | str) -> CTFIntegrationConfig | None:
    return db.execute(_row_query(ctf_id)).scalar_one_or_none()


def _get_or_create_row(db: Session, ctf_id: UUID | str) -> CTFIntegrationConfig:
    row = _load_row(db, ctf_id)
    if row is None:
        row = CTFIntegrationConfig(ctf_id=ctf_id, provider=CTFD_PROVIDER, config_json={})
        db.add(row)
        db.flush()
    return row


def _safe_payload(row: CTFIntegrationConfig | None) -> dict[str, Any]:
    if row is None or not isinstance(row.config_json, dict):
        return {}
    return dict(row.config_json)


def list_ctfd_auth_modes(payload: dict[str, Any]) -> list[str]:
    preferred = str(payload.get("preferred_auth_mode") or "").strip()
    modes: list[str] = []
    if preferred in {"api_token", "session_cookie"}:
        modes.append(preferred)
    if payload.get("api_token_encrypted") and "api_token" not in modes:
        modes.append("api_token")
    if payload.get("session_cookie_encrypted") and "session_cookie" not in modes:
        modes.append("session_cookie")
    return modes


def get_ctfd_config_record(db: Session, ctf_id: UUID | str) -> dict[str, Any] | None:
    row = _load_row(db, ctf_id)
    if row is None:
        return None
    payload = _safe_payload(row)
    payload["updated_at"] = row.updated_at
    return payload


def get_ctfd_config_response(db: Session, ctf_id: UUID | str) -> dict[str, Any]:
    row = _load_row(db, ctf_id)
    payload = _safe_payload(row)
    base_url = str(payload.get("base_url") or "")
    auth_modes = list_ctfd_auth_modes(payload)
    return {
        "base_url": base_url,
        "configured": bool(base_url and auth_modes),
        "preferred_auth_mode": payload.get("preferred_auth_mode"),
        "has_api_token": bool(payload.get("api_token_encrypted")),
        "has_session_cookie": bool(payload.get("session_cookie_encrypted")),
        "stored_auth_modes": auth_modes,
        "last_sync_auth_mode": payload.get("last_sync_auth_mode"),
        "last_submit_auth_mode": payload.get("last_submit_auth_mode"),
        "last_submit_status": payload.get("last_submit_status"),
        "updated_at": row.updated_at if row is not None else None,
    }


def get_ctfd_decrypted_credentials(db: Session, ctf_id: UUID | str) -> dict[str, Any] | None:
    row = _load_row(db, ctf_id)
    if row is None:
        return None
    payload = _safe_payload(row)
    base_url = _normalize_base_url(payload.get("base_url"))
    if not base_url:
        return None
    return {
        "base_url": base_url,
        "preferred_auth_mode": payload.get("preferred_auth_mode"),
        "api_token": _decrypt_secret(payload.get("api_token_encrypted")),
        "session_cookie": _decrypt_secret(payload.get("session_cookie_encrypted")),
        "last_sync_auth_mode": payload.get("last_sync_auth_mode"),
    }


def upsert_ctfd_config(
    db: Session,
    *,
    ctf_id: UUID | str,
    base_url: str | None = None,
    preferred_auth_mode: str | None = None,
    last_sync_auth_mode: str | None = None,
    api_token: str | None = None,
    session_cookie: str | None = None,
    clear_api_token: bool = False,
    clear_session_cookie: bool = False,
) -> CTFIntegrationConfig:
    row = _get_or_create_row(db, ctf_id)
    payload = _safe_payload(row)

    normalized_base_url = _normalize_base_url(base_url)
    if normalized_base_url is not None:
        payload["base_url"] = normalized_base_url

    if preferred_auth_mode in {"api_token", "session_cookie"}:
        payload["preferred_auth_mode"] = preferred_auth_mode
    if last_sync_auth_mode in {"api_token", "session_cookie"}:
        payload["last_sync_auth_mode"] = last_sync_auth_mode

    if clear_api_token:
        payload.pop("api_token_encrypted", None)
    elif api_token is not None:
        encrypted = _encrypt_secret(api_token)
        if encrypted:
            payload["api_token_encrypted"] = encrypted

    if clear_session_cookie:
        payload.pop("session_cookie_encrypted", None)
    elif session_cookie is not None:
        encrypted = _encrypt_secret(session_cookie)
        if encrypted:
            payload["session_cookie_encrypted"] = encrypted

    row.config_json = json.loads(json.dumps(payload))
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def clear_ctfd_api_token(db: Session, *, ctf_id: UUID | str) -> dict[str, Any]:
    row = _load_row(db, ctf_id)
    if row is None:
        return get_ctfd_config_response(db, ctf_id)
    payload = _safe_payload(row)
    payload.pop("api_token_encrypted", None)
    if payload.get("preferred_auth_mode") == "api_token":
        payload["preferred_auth_mode"] = "session_cookie" if payload.get("session_cookie_encrypted") else None
    row.config_json = json.loads(json.dumps(payload))
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    return get_ctfd_config_response(db, ctf_id)


def clear_ctfd_session_cookie(db: Session, *, ctf_id: UUID | str) -> dict[str, Any]:
    row = _load_row(db, ctf_id)
    if row is None:
        return get_ctfd_config_response(db, ctf_id)
    payload = _safe_payload(row)
    payload.pop("session_cookie_encrypted", None)
    if payload.get("preferred_auth_mode") == "session_cookie":
        payload["preferred_auth_mode"] = "api_token" if payload.get("api_token_encrypted") else None
    row.config_json = json.loads(json.dumps(payload))
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    return get_ctfd_config_response(db, ctf_id)


def mark_ctfd_submit_result(
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
    if auth_mode in {"api_token", "session_cookie"}:
        payload["last_submit_auth_mode"] = auth_mode
    payload["last_submit_status"] = status
    payload["last_submit_at"] = datetime.now(timezone.utc).isoformat()
    row.config_json = json.loads(json.dumps(payload))
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    if commit:
        db.commit()


def resolve_ctfd_auth_candidates(
    db: Session,
    *,
    ctf_id: UUID | str,
    preferred_mode: str | None = None,
) -> list[CTFdAuthMaterial]:
    creds = get_ctfd_decrypted_credentials(db, ctf_id)
    if not creds:
        return []
    base_url = str(creds.get("base_url") or "").strip()
    if not base_url:
        return []

    available: dict[str, str] = {}
    api_token = str(creds.get("api_token") or "").strip()
    if api_token:
        available["api_token"] = api_token
    session_cookie = str(creds.get("session_cookie") or "").strip()
    if session_cookie:
        available["session_cookie"] = session_cookie

    order: list[str] = []
    for mode in (preferred_mode, creds.get("preferred_auth_mode"), "api_token", "session_cookie"):
        if mode in available and mode not in order:
            order.append(str(mode))

    return [CTFdAuthMaterial(base_url=base_url, mode=mode, secret=available[mode]) for mode in order]
