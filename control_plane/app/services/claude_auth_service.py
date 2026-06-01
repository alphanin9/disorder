"""Claude Code (Anthropic) OAuth credential store and helpers.

Mirrors ``auth_service.py`` (Codex) but for Claude Code. Anthropic does not
expose a poll-based device flow like OpenAI's Codex; instead Claude Code uses an
authorization-code + PKCE flow where the operator logs in via a browser and
pastes back a ``code#state`` string. This module:

* begins an OAuth flow (generates PKCE verifier/state, returns the authorize URL),
* completes it (exchanges the pasted code for tokens),
* stores the resulting credentials encrypted, keyed by tag, in the shared
  ``integration_configs`` table,
* refreshes/health-checks tokens, and
* hands decrypted ``.credentials.json`` material to the orchestrator so it can be
  seeded into each sandbox's ``~/.claude`` (devcontainer-style).

The encrypted credential payload is the exact file the Claude CLI reads:
``{"claudeAiOauth": {"accessToken", "refreshToken", "expiresAt", "scopes"}}``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.app.core.config import get_settings
from control_plane.app.db.models import IntegrationConfig
from control_plane.app.schemas.auth import (
    ClaudeAuthFileRead,
    ClaudeAuthStatusResponse,
    ClaudeAuthTagRead,
    ClaudeOAuthCompleteResponse,
    ClaudeOAuthStartResponse,
)

# Reuse the shared cipher and tag/file helpers from the Codex auth service so
# both providers encrypt with the same key and validate tags identically.
from control_plane.app.services.auth_service import (
    _build_cipher,
    _parse_datetime,
    normalize_auth_tag,
    sanitize_auth_file_name,
)

STORE_NAME = "claude_auth_store"
CREDENTIALS_FILE_NAME = ".credentials.json"
OAUTH_BETA_HEADER = "oauth-2025-04-20"
# Refresh slightly early so a token isn't handed to a sandbox moments before it
# expires (matches claude-swap's 5 minute buffer).
TOKEN_EXPIRY_BUFFER_SECONDS = 5 * 60


@dataclass(slots=True)
class ClaudeAuthMaterial:
    tag: str
    file_name: str
    content: bytes
    sha256: str


# ----- store plumbing -------------------------------------------------------


def _empty_store() -> dict[str, Any]:
    return {
        "active_tag": None,
        "files": [],
        "oauth_flows": [],
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
    oauth_flows = payload.get("oauth_flows")
    if not isinstance(oauth_flows, list):
        oauth_flows = []
    store = {
        "active_tag": payload.get("active_tag"),
        "files": files,
        "oauth_flows": oauth_flows,
        "updated_at": payload.get("updated_at")
        or datetime.now(timezone.utc).isoformat(),
    }
    return row, store


def _save_store(db: Session, row: IntegrationConfig, store: dict[str, Any]) -> None:
    store["updated_at"] = datetime.now(timezone.utc).isoformat()
    row.config_json = json.loads(json.dumps(store))
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)


def _file_to_schema(item: dict[str, Any]) -> ClaudeAuthFileRead:
    uploaded = item.get("uploaded_at")
    uploaded_at = _parse_datetime(uploaded) or datetime.now(timezone.utc)
    return ClaudeAuthFileRead(
        id=str(item.get("id")),
        tag=str(item.get("tag")),
        file_name=str(item.get("file_name")),
        sha256=str(item.get("sha256")),
        size_bytes=int(item.get("size_bytes", 0)),
        uploaded_at=uploaded_at,
        source=str(item.get("source")) if item.get("source") else None,
        health_status=str(item.get("health_status"))
        if item.get("health_status")
        else None,
        last_checked_at=_parse_datetime(item.get("last_checked_at")),
        last_health_error=str(item.get("last_health_error"))
        if item.get("last_health_error")
        else None,
        expires_at=_parse_datetime(item.get("expires_at")),
        usage_snapshot=item.get("usage_snapshot")
        if isinstance(item.get("usage_snapshot"), dict)
        else None,
    )


def get_claude_auth_status(db: Session) -> ClaudeAuthStatusResponse:
    _, store = _load_store(db)
    files = [_file_to_schema(item) for item in store.get("files", [])]
    grouped: dict[str, list[ClaudeAuthFileRead]] = {}
    for file_row in files:
        grouped.setdefault(file_row.tag, []).append(file_row)

    tags = [
        ClaudeAuthTagRead(
            tag=tag,
            file_count=len(items),
            files=sorted(items, key=lambda entry: (entry.file_name, entry.uploaded_at)),
        )
        for tag, items in grouped.items()
    ]
    tags.sort(key=lambda entry: entry.tag)

    health_status = "unknown"
    if files:
        health_values = {file_row.health_status or "unknown" for file_row in files}
        if "invalid" in health_values:
            health_status = "invalid"
        elif "valid" in health_values:
            health_status = "valid"
        elif "check_failed" in health_values:
            health_status = "check_failed"

    return ClaudeAuthStatusResponse(
        configured=len(files) > 0,
        active_tag=store.get("active_tag"),
        tags=tags,
        health_status=health_status,
        reauth_required=health_status == "invalid",
    )


# ----- credential payloads --------------------------------------------------


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _build_claude_credentials_json(
    tokens: dict[str, Any], *, fallback_scopes: list[str] | None = None
) -> tuple[bytes, datetime | None]:
    """Render the ``~/.claude/.credentials.json`` payload from token data.

    Returns the encoded bytes and the access-token expiry (if known).
    """
    access_token = str(tokens.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("Claude token response did not include access_token")
    refresh_token = str(tokens.get("refresh_token") or "").strip()

    expires_at_ms: int = 0
    expires_at_dt: datetime | None = None
    expires_in = tokens.get("expires_in")
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        expires_at_ms = _now_ms() + int(expires_in) * 1000
        expires_at_dt = datetime.fromtimestamp(
            expires_at_ms / 1000, tz=timezone.utc
        )

    scope = tokens.get("scope")
    if isinstance(scope, str) and scope.strip():
        scopes = scope.split()
    else:
        scopes = list(fallback_scopes or [])

    payload = {
        "claudeAiOauth": {
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "expiresAt": expires_at_ms,
            "scopes": scopes,
        }
    }
    return json.dumps(payload, indent=2).encode("utf-8") + b"\n", expires_at_dt


def _extract_oauth_from_bytes(raw_bytes: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    oauth = payload.get("claudeAiOauth") if isinstance(payload, dict) else None
    return dict(oauth) if isinstance(oauth, dict) else {}


def _store_claude_credentials(
    db: Session,
    *,
    tag: str,
    raw_bytes: bytes,
    source: str,
    expires_at: datetime | None,
    health_status: str | None = None,
    last_checked_at: datetime | None = None,
) -> ClaudeAuthFileRead:
    settings = get_settings()
    normalized_tag = normalize_auth_tag(tag)

    if not raw_bytes:
        raise ValueError("Empty Claude credentials are not allowed")
    if len(raw_bytes) > settings.codex_auth_max_file_bytes:
        raise ValueError(
            f"Claude credentials exceed limit of {settings.codex_auth_max_file_bytes} bytes"
        )

    cipher = _build_cipher()
    encrypted_payload = cipher.encrypt(raw_bytes).decode("utf-8")
    sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
    now_iso = datetime.now(timezone.utc).isoformat()

    row, store = _load_store(db)
    files: list[dict[str, Any]] = list(store.get("files", []))

    replacement_index = next(
        (
            idx
            for idx, item in enumerate(files)
            if str(item.get("tag")) == normalized_tag
            and str(item.get("file_name")) == CREDENTIALS_FILE_NAME
        ),
        None,
    )

    payload = {
        "id": str(uuid.uuid4()),
        "tag": normalized_tag,
        "file_name": CREDENTIALS_FILE_NAME,
        "sha256": sha256_hex,
        "size_bytes": len(raw_bytes),
        "uploaded_at": now_iso,
        "encrypted_payload": encrypted_payload,
        "source": source,
        "health_status": health_status,
        "last_checked_at": last_checked_at.isoformat() if last_checked_at else None,
        "last_health_error": None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "usage_snapshot": None,
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


# ----- OAuth (authorization-code + PKCE) ------------------------------------


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _build_pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("utf-8")).digest())
    return verifier, challenge


def start_claude_oauth(db: Session, *, tag: str) -> ClaudeOAuthStartResponse:
    settings = get_settings()
    normalized_tag = normalize_auth_tag(tag)

    verifier, challenge = _build_pkce_pair()
    state = _b64url(secrets.token_bytes(24))
    params = {
        "code": "true",
        "client_id": settings.claude_oauth_client_id,
        "response_type": "code",
        "redirect_uri": settings.claude_oauth_redirect_uri,
        "scope": settings.claude_oauth_scopes,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    authorize_url = httpx.URL(settings.claude_oauth_authorize_url, params=params)

    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=max(60, settings.claude_auth_device_flow_timeout_seconds)
    )
    flow_id = str(uuid.uuid4())
    cipher = _build_cipher()

    row, store = _load_store(db)
    flows = [
        flow
        for flow in list(store.get("oauth_flows", []))
        if _parse_datetime(flow.get("expires_at"))
        and _parse_datetime(flow.get("expires_at")) > datetime.now(timezone.utc)
    ]
    flows.append(
        {
            "id": flow_id,
            "tag": normalized_tag,
            "state": state,
            "encrypted_code_verifier": cipher.encrypt(
                verifier.encode("utf-8")
            ).decode("utf-8"),
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    store["oauth_flows"] = flows
    _save_store(db, row, store)

    return ClaudeOAuthStartResponse(
        flow_id=flow_id,
        tag=normalized_tag,
        authorize_url=str(authorize_url),
        expires_at=expires_at,
    )


def _request_claude_token(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    with httpx.Client(
        timeout=httpx.Timeout(20.0), headers={"Accept": "application/json"}
    ) as client:
        response = client.post(
            settings.claude_oauth_token_url,
            headers={"Content-Type": "application/json"},
            json={**payload, "client_id": settings.claude_oauth_client_id},
        )
    if response.status_code != 200:
        message = f"Claude token request failed with status {response.status_code}"
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = body.get("error_description") or body.get("error")
                if isinstance(detail, str) and detail:
                    message = detail
        except ValueError:
            pass
        raise ValueError(message)
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("Claude token request returned invalid JSON")
    return body


def complete_claude_oauth(
    db: Session, *, flow_id: str, code: str
) -> ClaudeOAuthCompleteResponse:
    settings = get_settings()
    row, store = _load_store(db)
    flows = list(store.get("oauth_flows", []))
    flow = next((item for item in flows if str(item.get("id")) == flow_id), None)
    if flow is None:
        raise ValueError("Claude OAuth flow not found")

    tag = normalize_auth_tag(str(flow.get("tag") or "default"))
    expires_at = _parse_datetime(flow.get("expires_at"))
    if expires_at is None or expires_at <= datetime.now(timezone.utc):
        store["oauth_flows"] = [
            item for item in flows if str(item.get("id")) != flow_id
        ]
        _save_store(db, row, store)
        return ClaudeOAuthCompleteResponse(
            flow_id=flow_id,
            tag=tag,
            status="expired",
            message="Claude OAuth flow expired. Start sign-in again.",
        )

    encrypted_verifier = flow.get("encrypted_code_verifier")
    if not isinstance(encrypted_verifier, str):
        raise ValueError("Claude OAuth flow is missing its code verifier")
    try:
        code_verifier = _build_cipher().decrypt(
            encrypted_verifier.encode("utf-8")
        ).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Claude OAuth flow could not be decrypted") from exc

    # Claude returns the authorization code to the user as ``code#state``.
    raw_code = code.strip()
    authorization_code = raw_code
    returned_state = ""
    if "#" in raw_code:
        authorization_code, returned_state = raw_code.split("#", 1)
    authorization_code = authorization_code.strip()
    returned_state = returned_state.strip()
    if not authorization_code:
        raise ValueError("Authorization code is empty")

    expected_state = str(flow.get("state") or "")
    if returned_state and expected_state and returned_state != expected_state:
        raise ValueError("Authorization state mismatch; restart the sign-in flow")

    token_payload = _request_claude_token(
        {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "state": returned_state or expected_state,
            "redirect_uri": settings.claude_oauth_redirect_uri,
            "code_verifier": code_verifier,
        }
    )

    fallback_scopes = settings.claude_oauth_scopes.split()
    raw_bytes, token_expiry = _build_claude_credentials_json(
        token_payload, fallback_scopes=fallback_scopes
    )
    auth_file = _store_claude_credentials(
        db,
        tag=tag,
        raw_bytes=raw_bytes,
        source="oauth",
        expires_at=token_expiry,
        health_status="valid",
        last_checked_at=datetime.now(timezone.utc),
    )

    row, store = _load_store(db)
    store["oauth_flows"] = [
        item for item in list(store.get("oauth_flows", [])) if str(item.get("id")) != flow_id
    ]
    _save_store(db, row, store)

    return ClaudeOAuthCompleteResponse(
        flow_id=flow_id,
        tag=tag,
        status="authorized",
        message="Claude Code sign-in complete",
        auth_file=auth_file,
        auth_status=get_claude_auth_status(db),
    )


# ----- refresh / health / usage --------------------------------------------


def _fetch_claude_usage(access_token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        with httpx.Client(timeout=httpx.Timeout(10.0)) as client:
            response = client.get(
                settings.claude_oauth_usage_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "anthropic-beta": OAUTH_BETA_HEADER,
                },
            )
        if response.status_code != 200:
            return None
        body = response.json()
        return body if isinstance(body, dict) else None
    except Exception:  # noqa: BLE001 - usage is best-effort
        return None


def _mark_file_health(
    item: dict[str, Any],
    *,
    status: str,
    checked_at: datetime,
    error: str | None = None,
    replacement_bytes: bytes | None = None,
    expires_at: datetime | None = None,
    usage_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updated = dict(item)
    updated["health_status"] = status
    updated["last_checked_at"] = checked_at.isoformat()
    updated["last_health_error"] = error
    if expires_at is not None:
        updated["expires_at"] = expires_at.isoformat()
    if usage_snapshot is not None:
        updated["usage_snapshot"] = usage_snapshot
    if replacement_bytes is not None:
        cipher = _build_cipher()
        updated["encrypted_payload"] = cipher.encrypt(replacement_bytes).decode("utf-8")
        updated["sha256"] = hashlib.sha256(replacement_bytes).hexdigest()
        updated["size_bytes"] = len(replacement_bytes)
    return updated


def _token_needs_refresh(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    return datetime.now(timezone.utc) + timedelta(
        seconds=TOKEN_EXPIRY_BUFFER_SECONDS
    ) >= expires_at


def check_claude_auth_health(db: Session, *, force: bool = False) -> ClaudeAuthStatusResponse:
    settings = get_settings()
    row, store = _load_store(db)
    files = list(store.get("files", []))
    if not files:
        return get_claude_auth_status(db)

    now = datetime.now(timezone.utc)
    interval = max(60, settings.claude_auth_health_check_interval_seconds)
    cipher = _build_cipher()
    changed = False
    checked_files: list[dict[str, Any]] = []
    for item in files:
        if str(item.get("file_name")) != CREDENTIALS_FILE_NAME:
            checked_files.append(item)
            continue
        last_checked_at = _parse_datetime(item.get("last_checked_at"))
        if not force and last_checked_at and (now - last_checked_at).total_seconds() < interval:
            checked_files.append(item)
            continue

        encrypted = item.get("encrypted_payload")
        try:
            if not isinstance(encrypted, str):
                raise ValueError("Stored Claude credentials are missing")
            raw_bytes = cipher.decrypt(encrypted.encode("utf-8"))
            oauth = _extract_oauth_from_bytes(raw_bytes)
            access_token = str(oauth.get("accessToken") or "").strip()
            refresh_token = str(oauth.get("refreshToken") or "").strip()
            stored_expiry = _parse_datetime(item.get("expires_at"))

            replacement: bytes | None = None
            new_expiry = stored_expiry
            if refresh_token and (force or _token_needs_refresh(stored_expiry)):
                refreshed = _request_claude_token(
                    {"grant_type": "refresh_token", "refresh_token": refresh_token}
                )
                if not refreshed.get("refresh_token"):
                    refreshed["refresh_token"] = refresh_token
                replacement, new_expiry = _build_claude_credentials_json(
                    refreshed, fallback_scopes=oauth.get("scopes")
                )
                access_token = str(refreshed.get("access_token") or access_token)
            elif not access_token:
                raise ValueError("Stored Claude credentials are missing an access token")

            usage_snapshot = None
            if settings.claude_auth_usage_probe_enabled and access_token:
                usage_snapshot = _fetch_claude_usage(access_token)

            checked_files.append(
                _mark_file_health(
                    item,
                    status="valid",
                    checked_at=now,
                    replacement_bytes=replacement,
                    expires_at=new_expiry,
                    usage_snapshot=usage_snapshot,
                )
            )
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            invalid = (
                "invalid" in error.lower()
                or "401" in error
                or "403" in error
                or "invalid_grant" in error.lower()
            )
            checked_files.append(
                _mark_file_health(
                    item,
                    status="invalid" if invalid else "check_failed",
                    checked_at=now,
                    error=error,
                )
            )
        changed = True

    if changed:
        store["files"] = checked_files
        _save_store(db, row, store)
    return get_claude_auth_status(db)


# ----- tag/file management --------------------------------------------------


def set_claude_active_tag(db: Session, tag: str) -> ClaudeAuthStatusResponse:
    normalized_tag = normalize_auth_tag(tag)
    row, store = _load_store(db)
    files = store.get("files", [])
    if not any(str(item.get("tag")) == normalized_tag for item in files):
        raise ValueError(f"Auth tag '{normalized_tag}' has no stored credentials")
    store["active_tag"] = normalized_tag
    _save_store(db, row, store)
    return get_claude_auth_status(db)


def delete_claude_auth_file(db: Session, file_id: str) -> ClaudeAuthStatusResponse:
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
    return get_claude_auth_status(db)


def delete_claude_auth_tag(db: Session, tag: str) -> ClaudeAuthStatusResponse:
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
    return get_claude_auth_status(db)


def get_claude_auth_material_for_tag(
    db: Session, requested_tag: str | None = None
) -> tuple[str | None, list[ClaudeAuthMaterial]]:
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

    material: list[ClaudeAuthMaterial] = []
    for item in selected:
        encrypted = item.get("encrypted_payload")
        if not isinstance(encrypted, str) or not encrypted:
            continue
        try:
            decrypted = cipher.decrypt(encrypted.encode("utf-8"))
        except InvalidToken:
            continue
        material.append(
            ClaudeAuthMaterial(
                tag=tag,
                file_name=sanitize_auth_file_name(item.get("file_name")),
                content=decrypted,
                sha256=str(item.get("sha256") or ""),
            )
        )
    return tag, material
