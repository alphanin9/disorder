from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.app.core.config import get_settings
from control_plane.app.db.models import IntegrationConfig
from control_plane.app.schemas.auth import CodexAuthFileRead, CodexAuthStatusResponse, CodexAuthTagRead

STORE_NAME = "codex_auth_store"
TAG_REGEX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


@dataclass(slots=True)
class CodexAuthMaterial:
    tag: str
    file_name: str
    content: bytes
    sha256: str


def normalize_auth_tag(raw_tag: str) -> str:
    tag = raw_tag.strip()
    if not tag:
        raise ValueError("Auth tag is required")
    if not TAG_REGEX.fullmatch(tag):
        raise ValueError("Auth tag must match [A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
    return tag


def sanitize_auth_file_name(raw_name: str | None) -> str:
    safe_name = Path((raw_name or "auth.json").replace("\\", "/")).name.strip()
    return safe_name or "auth.json"


def is_allowed_auth_file_name(file_name: str) -> bool:
    settings = get_settings()
    file_name_lower = file_name.lower()
    patterns = [pattern.strip().lower() for pattern in settings.sandbox_codex_auth_include.split(",") if pattern.strip()]
    if not patterns:
        return False
    return any(fnmatch(file_name_lower, pattern) for pattern in patterns)


def _build_cipher() -> Fernet:
    settings = get_settings()
    configured_key = settings.codex_auth_encryption_key
    if configured_key:
        try:
            return Fernet(configured_key.encode("utf-8"))
        except Exception as exc:  # pragma: no cover - defensive validation
            raise ValueError("Invalid CODEX_AUTH_ENCRYPTION_KEY (expected Fernet key)") from exc

    # Dev-friendly fallback: deterministic key derived from existing app secrets.
    digest = hashlib.sha256(f"{settings.app_name}:{settings.minio_secret_key}".encode("utf-8")).digest()
    derived_key = base64.urlsafe_b64encode(digest)
    return Fernet(derived_key)


def _empty_store() -> dict[str, Any]:
    return {
        "active_tag": None,
        "files": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _get_or_create_store_row(db: Session) -> IntegrationConfig:
    stmt = select(IntegrationConfig).where(IntegrationConfig.name == STORE_NAME)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        row = IntegrationConfig(name=STORE_NAME, config_json=_empty_store())
        db.add(row)
        db.flush()
    return row


def _load_store(db: Session) -> tuple[IntegrationConfig, dict[str, Any]]:
    row = _get_or_create_store_row(db)
    payload = row.config_json or {}
    files = payload.get("files")
    if not isinstance(files, list):
        files = []

    store = {
        "active_tag": payload.get("active_tag"),
        "files": files,
        "updated_at": payload.get("updated_at") or datetime.now(timezone.utc).isoformat(),
    }
    return row, store


def _save_store(db: Session, row: IntegrationConfig, store: dict[str, Any]) -> None:
    store["updated_at"] = datetime.now(timezone.utc).isoformat()
    row.config_json = json.loads(json.dumps(store))
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)


def _file_to_schema(item: dict[str, Any]) -> CodexAuthFileRead:
    uploaded = item.get("uploaded_at")
    if isinstance(uploaded, str):
        try:
            uploaded_at = datetime.fromisoformat(uploaded.replace("Z", "+00:00"))
        except ValueError:
            uploaded_at = datetime.now(timezone.utc)
    else:
        uploaded_at = datetime.now(timezone.utc)
    return CodexAuthFileRead(
        id=str(item.get("id")),
        tag=str(item.get("tag")),
        file_name=str(item.get("file_name")),
        sha256=str(item.get("sha256")),
        size_bytes=int(item.get("size_bytes", 0)),
        uploaded_at=uploaded_at,
    )


def get_codex_auth_status(db: Session) -> CodexAuthStatusResponse:
    _, store = _load_store(db)
    files = [_file_to_schema(item) for item in store.get("files", [])]
    grouped: dict[str, list[CodexAuthFileRead]] = {}
    for file_row in files:
        grouped.setdefault(file_row.tag, []).append(file_row)

    tags = [
        CodexAuthTagRead(tag=tag, file_count=len(items), files=sorted(items, key=lambda entry: (entry.file_name, entry.uploaded_at)))
        for tag, items in grouped.items()
    ]
    tags.sort(key=lambda entry: entry.tag)

    return CodexAuthStatusResponse(
        configured=len(files) > 0,
        active_tag=store.get("active_tag"),
        tags=tags,
    )


def upload_codex_auth_file(db: Session, *, tag: str, file_name: str, raw_bytes: bytes) -> CodexAuthFileRead:
    settings = get_settings()
    normalized_tag = normalize_auth_tag(tag)
    sanitized_file_name = sanitize_auth_file_name(file_name)

    if not is_allowed_auth_file_name(sanitized_file_name):
        raise ValueError(f"File '{sanitized_file_name}' is not allowed by auth file allowlist")

    if not raw_bytes:
        raise ValueError("Empty auth file upload is not allowed")

    if len(raw_bytes) > settings.codex_auth_max_file_bytes:
        raise ValueError(f"Auth file exceeds limit of {settings.codex_auth_max_file_bytes} bytes")

    cipher = _build_cipher()
    encrypted_payload = cipher.encrypt(raw_bytes).decode("utf-8")
    sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
    uploaded_at = datetime.now(timezone.utc).isoformat()

    row, store = _load_store(db)
    files: list[dict[str, Any]] = list(store.get("files", []))

    replacement_index = next(
        (
            idx
            for idx, item in enumerate(files)
            if str(item.get("tag")) == normalized_tag and str(item.get("file_name")) == sanitized_file_name
        ),
        None,
    )

    payload = {
        "id": str(uuid.uuid4()),
        "tag": normalized_tag,
        "file_name": sanitized_file_name,
        "sha256": sha256_hex,
        "size_bytes": len(raw_bytes),
        "uploaded_at": uploaded_at,
        "encrypted_payload": encrypted_payload,
    }

    if replacement_index is None:
        files.append(payload)
    else:
        payload["id"] = str(files[replacement_index].get("id") or payload["id"])
        files[replacement_index] = payload

    if not store.get("active_tag"):
        store["active_tag"] = normalized_tag
    store["files"] = files
    _save_store(db, row, store)

    return _file_to_schema(payload)


def set_codex_active_tag(db: Session, tag: str) -> CodexAuthStatusResponse:
    normalized_tag = normalize_auth_tag(tag)
    row, store = _load_store(db)
    files = store.get("files", [])
    if not any(str(item.get("tag")) == normalized_tag for item in files):
        raise ValueError(f"Auth tag '{normalized_tag}' has no uploaded files")
    store["active_tag"] = normalized_tag
    _save_store(db, row, store)
    return get_codex_auth_status(db)


def delete_codex_auth_file(db: Session, file_id: str) -> CodexAuthStatusResponse:
    row, store = _load_store(db)
    files = list(store.get("files", []))
    remaining = [item for item in files if str(item.get("id")) != file_id]
    if len(remaining) == len(files):
        raise ValueError("Auth file not found")

    active_tag = store.get("active_tag")
    if active_tag and not any(str(item.get("tag")) == active_tag for item in remaining):
        store["active_tag"] = str(remaining[0].get("tag")) if remaining else None
    store["files"] = remaining
    _save_store(db, row, store)
    return get_codex_auth_status(db)


def delete_codex_auth_tag(db: Session, tag: str) -> CodexAuthStatusResponse:
    normalized_tag = normalize_auth_tag(tag)
    row, store = _load_store(db)
    files = list(store.get("files", []))
    remaining = [item for item in files if str(item.get("tag")) != normalized_tag]
    if len(remaining) == len(files):
        raise ValueError(f"Auth tag '{normalized_tag}' not found")

    active_tag = store.get("active_tag")
    if active_tag == normalized_tag:
        store["active_tag"] = str(remaining[0].get("tag")) if remaining else None
    store["files"] = remaining
    _save_store(db, row, store)
    return get_codex_auth_status(db)


def get_codex_auth_material_for_tag(db: Session, requested_tag: str | None = None) -> tuple[str | None, list[CodexAuthMaterial]]:
    _, store = _load_store(db)
    files = list(store.get("files", []))
    if not files:
        return None, []

    tag = normalize_auth_tag(requested_tag) if requested_tag else store.get("active_tag")
    if not isinstance(tag, str) or not tag:
        return None, []

    selected = [item for item in files if str(item.get("tag")) == tag]
    if not selected:
        return tag, []

    try:
        cipher = _build_cipher()
    except ValueError:
        return tag, []
    material: list[CodexAuthMaterial] = []
    for item in selected:
        encrypted = item.get("encrypted_payload")
        if not isinstance(encrypted, str) or not encrypted:
            continue
        try:
            decrypted = cipher.decrypt(encrypted.encode("utf-8"))
        except InvalidToken:
            continue

        material.append(
            CodexAuthMaterial(
                tag=tag,
                file_name=sanitize_auth_file_name(item.get("file_name")),
                content=decrypted,
                sha256=str(item.get("sha256") or ""),
            )
        )
    return tag, material
