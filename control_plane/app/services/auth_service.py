from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.app.core.config import get_settings
from control_plane.app.db.models import IntegrationConfig
from control_plane.app.schemas.auth import (
    CodexAuthFileRead,
    CodexAuthStatusResponse,
    CodexAuthTagRead,
    CodexDeviceAuthPollResponse,
    CodexDeviceAuthStartResponse,
)

STORE_NAME = "codex_auth_store"
TAG_REGEX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_DEVICE_USERCODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
CODEX_DEVICE_TOKEN_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
CODEX_DEVICE_VERIFICATION_URI = "https://auth.openai.com/codex/device"
CODEX_DEVICE_REDIRECT_URI = "https://auth.openai.com/deviceauth/callback"
CODEX_BACKEND_BASE_URL = "https://chatgpt.com/backend-api"
CODEX_JWT_AUTH_CLAIM = "https://api.openai.com/auth"
AUTH_JSON_FILE_NAME = "auth.json"
DEFAULT_CODEX_LIMIT_PROBE_MODELS = (
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.3-codex",
    "gpt-5.2-codex",
    "gpt-5-codex",
)


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
        "device_flows": [],
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
        "device_flows": payload.get("device_flows") if isinstance(payload.get("device_flows"), list) else [],
        "updated_at": payload.get("updated_at") or datetime.now(timezone.utc).isoformat(),
    }
    return row, store


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _save_store(db: Session, row: IntegrationConfig, store: dict[str, Any]) -> None:
    store["updated_at"] = datetime.now(timezone.utc).isoformat()
    row.config_json = json.loads(json.dumps(store))
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)


def _file_to_schema(item: dict[str, Any]) -> CodexAuthFileRead:
    uploaded = item.get("uploaded_at")
    uploaded_at = _parse_datetime(uploaded) or datetime.now(timezone.utc)
    return CodexAuthFileRead(
        id=str(item.get("id")),
        tag=str(item.get("tag")),
        file_name=str(item.get("file_name")),
        sha256=str(item.get("sha256")),
        size_bytes=int(item.get("size_bytes", 0)),
        uploaded_at=uploaded_at,
        source=str(item.get("source")) if item.get("source") else None,
        health_status=str(item.get("health_status")) if item.get("health_status") else None,
        last_checked_at=_parse_datetime(item.get("last_checked_at")),
        last_health_error=str(item.get("last_health_error")) if item.get("last_health_error") else None,
        limit_status=str(item.get("limit_status")) if item.get("limit_status") else None,
        last_limit_checked_at=_parse_datetime(item.get("last_limit_checked_at")),
        last_limit_error=str(item.get("last_limit_error")) if item.get("last_limit_error") else None,
        quota_snapshot=item.get("quota_snapshot") if isinstance(item.get("quota_snapshot"), dict) else None,
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

    health_status = "unknown"
    limit_status = "unknown"
    if files:
        health_values = {file_row.health_status or "unknown" for file_row in files}
        if "invalid" in health_values:
            health_status = "invalid"
        elif "valid" in health_values:
            health_status = "valid"
        elif "check_failed" in health_values:
            health_status = "check_failed"

        limit_values = {file_row.limit_status or "unknown" for file_row in files}
        if "exhausted" in limit_values:
            limit_status = "exhausted"
        elif "available" in limit_values:
            limit_status = "available"
        elif "rate_limited" in limit_values:
            limit_status = "rate_limited"
        elif "check_failed" in limit_values:
            limit_status = "check_failed"

    return CodexAuthStatusResponse(
        configured=len(files) > 0,
        active_tag=store.get("active_tag"),
        tags=tags,
        health_status=health_status,
        reauth_required=health_status == "invalid",
        limit_status=limit_status,
    )


def _store_codex_auth_file(
    db: Session,
    *,
    tag: str,
    file_name: str,
    raw_bytes: bytes,
    source: str,
    health_status: str | None = None,
    last_checked_at: datetime | None = None,
    last_health_error: str | None = None,
) -> CodexAuthFileRead:
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
        "source": source,
        "health_status": health_status,
        "last_checked_at": last_checked_at.isoformat() if last_checked_at else None,
        "last_health_error": last_health_error,
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


def upload_codex_auth_file(db: Session, *, tag: str, file_name: str, raw_bytes: bytes) -> CodexAuthFileRead:
    return _store_codex_auth_file(
        db,
        tag=tag,
        file_name=file_name,
        raw_bytes=raw_bytes,
        source="upload",
    )


def _decode_jwt_payload(token: str | None) -> dict[str, Any]:
    if not token or token.count(".") < 2:
        return {}
    try:
        payload = token.split(".", 2)[1]
        padded = payload + "=" * ((4 - len(payload) % 4) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8"))
        parsed = json.loads(decoded)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_account_id_from_tokens(tokens: dict[str, Any]) -> str | None:
    direct = tokens.get("account_id") or tokens.get("accountId") or tokens.get("chatgpt_account_id")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    for token_key in ("id_token", "access_token"):
        claims = _decode_jwt_payload(str(tokens.get(token_key) or ""))
        auth_claim = claims.get(CODEX_JWT_AUTH_CLAIM)
        if isinstance(auth_claim, dict):
            claim_id = auth_claim.get("chatgpt_account_id")
            if isinstance(claim_id, str) and claim_id.strip():
                return claim_id.strip()
        for claim_key in ("chatgpt_account_id", "account_id", "accountId"):
            claim_id = claims.get(claim_key)
            if isinstance(claim_id, str) and claim_id.strip():
                return claim_id.strip()
    return None


def _build_codex_auth_json(tokens: dict[str, Any]) -> bytes:
    access_token = str(tokens.get("access_token") or "").strip()
    refresh_token = str(tokens.get("refresh_token") or "").strip()
    id_token = str(tokens.get("id_token") or "").strip()
    if not access_token or not refresh_token:
        raise ValueError("Codex token response did not include access_token and refresh_token")
    if not id_token:
        id_token = access_token

    claims = _decode_jwt_payload(id_token or access_token)
    email = str(claims.get("email") or "").strip().lower() or None
    account_id = _extract_account_id_from_tokens({**tokens, "id_token": id_token, "access_token": access_token})
    token_payload: dict[str, Any] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }
    if id_token:
        token_payload["id_token"] = id_token
    if account_id:
        token_payload["account_id"] = account_id

    auth_payload = {
        "auth_mode": "chatgpt",
        "email": email,
        "tokens": token_payload,
        "last_refresh": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "OPENAI_API_KEY": None,
    }
    return json.dumps(auth_payload, indent=2).encode("utf-8") + b"\n"


def _extract_refresh_token(raw_bytes: bytes) -> str | None:
    tokens = _extract_auth_tokens(raw_bytes)
    refresh_token = tokens.get("refresh_token")
    return refresh_token.strip() if isinstance(refresh_token, str) and refresh_token.strip() else None


def _extract_auth_tokens(raw_bytes: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        return {}
    return dict(tokens)


def _request_codex_token_refresh(refresh_token: str) -> dict[str, Any]:
    with httpx.Client(timeout=httpx.Timeout(20.0), headers={"Accept": "application/json"}) as client:
        response = client.post(
            CODEX_OAUTH_TOKEN_URL,
            headers={"Content-Type": "application/json"},
            json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CODEX_OAUTH_CLIENT_ID,
            },
        )
    if response.status_code != 200:
        message = f"Codex token refresh failed with status {response.status_code}"
        try:
            body = response.json()
            if isinstance(body, dict):
                error = body.get("error")
                if isinstance(error, dict) and error.get("message"):
                    message = str(error["message"])
                elif isinstance(error, str):
                    message = error
        except ValueError:
            pass
        raise ValueError(message)
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Codex token refresh returned invalid JSON")
    return payload


def _header_float(headers: httpx.Headers, name: str) -> float | None:
    raw = headers.get(name)
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value == value and value not in (float("inf"), float("-inf")) else None


def _header_int(headers: httpx.Headers, name: str) -> int | None:
    raw = headers.get(name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_reset_at_ms(headers: httpx.Headers, prefix: str) -> int | None:
    reset_after = _header_int(headers, f"{prefix}-reset-after-seconds")
    if reset_after and reset_after > 0:
        return int(datetime.now(timezone.utc).timestamp() * 1000) + reset_after * 1000

    raw = headers.get(f"{prefix}-reset-at")
    if not raw:
        return None
    value = raw.strip()
    if value.isdigit():
        parsed = int(value)
        return parsed * 1000 if parsed < 10_000_000_000 else parsed
    try:
        parsed_datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(parsed_datetime.timestamp() * 1000)


def _quota_window(headers: httpx.Headers, prefix: str) -> dict[str, Any]:
    return {
        "used_percent": _header_float(headers, f"{prefix}-used-percent"),
        "window_minutes": _header_int(headers, f"{prefix}-window-minutes"),
        "reset_at_ms": _parse_reset_at_ms(headers, prefix),
    }


def _parse_quota_snapshot(headers: httpx.Headers, *, status_code: int, model: str) -> dict[str, Any] | None:
    quota_header_names = {
        "x-codex-primary-used-percent",
        "x-codex-primary-window-minutes",
        "x-codex-primary-reset-at",
        "x-codex-primary-reset-after-seconds",
        "x-codex-secondary-used-percent",
        "x-codex-secondary-window-minutes",
        "x-codex-secondary-reset-at",
        "x-codex-secondary-reset-after-seconds",
    }
    if not any(headers.get(name) is not None for name in quota_header_names):
        return None
    return {
        "status": status_code,
        "model": model,
        "plan_type": headers.get("x-codex-plan-type"),
        "active_limit": _header_int(headers, "x-codex-active-limit"),
        "primary": _quota_window(headers, "x-codex-primary"),
        "secondary": _quota_window(headers, "x-codex-secondary"),
    }


def _quota_status(snapshot: dict[str, Any]) -> str:
    if snapshot.get("status") == 429:
        return "rate_limited"
    windows = [snapshot.get("primary"), snapshot.get("secondary")]
    for window in windows:
        if isinstance(window, dict):
            used_percent = window.get("used_percent")
            if isinstance(used_percent, int | float) and used_percent >= 100:
                return "exhausted"
    return "available"


def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return str(error["message"])
        if isinstance(payload.get("message"), str):
            return str(payload["message"])
    return f"HTTP {response.status_code}"


def _codex_probe_models(
    primary_model: str | None, fallback_models: str | None = None
) -> list[str]:
    candidates: list[str] = []
    if isinstance(primary_model, str) and primary_model.strip():
        candidates.append(primary_model.strip())

    fallback_values = (
        [value.strip() for value in fallback_models.split(",")]
        if isinstance(fallback_models, str) and fallback_models.strip()
        else list(DEFAULT_CODEX_LIMIT_PROBE_MODELS)
    )
    candidates.extend(value for value in fallback_values if value)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def _is_unsupported_codex_model_response(response: httpx.Response) -> bool:
    if response.status_code not in {400, 404}:
        return False
    try:
        payload = response.json()
    except ValueError:
        payload = {"message": response.text}

    values: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, dict):
            for nested in value.values():
                collect(nested)

    collect(payload)
    haystack = " ".join(values).lower()
    unsupported_markers = (
        "model_not_supported_with_chatgpt_account",
        "model is not supported",
        "model_not_found",
        "does not exist or you do not have access",
        "not currently available for this chatgpt account",
    )
    return any(marker in haystack for marker in unsupported_markers)


def _probe_codex_limits(
    tokens: dict[str, Any],
    *,
    model: str,
    fallback_models: str | None = None,
) -> dict[str, Any]:
    access_token = str(tokens.get("access_token") or "").strip()
    account_id = _extract_account_id_from_tokens(tokens)
    if not access_token:
        raise ValueError("Stored auth.json is missing access_token")
    if not account_id:
        raise ValueError("Stored auth.json is missing ChatGPT account id")

    last_error: str | None = None
    for candidate_model in _codex_probe_models(model, fallback_models):
        body = {
            "model": candidate_model,
            "stream": True,
            "store": False,
            "include": ["reasoning.encrypted_content"],
            "instructions": "You are a quota probe. Respond with ok.",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "quota ping"}],
                }
            ],
            "reasoning": {"effort": "none", "summary": "auto"},
            "text": {"verbosity": "low"},
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "chatgpt-account-id": account_id,
            "OpenAI-Beta": "responses=experimental",
            "originator": "codex_cli_rs",
            "accept": "text/event-stream",
            "content-type": "application/json",
        }
        with httpx.Client(timeout=httpx.Timeout(20.0), headers={"Accept": "application/json"}) as client:
            with client.stream(
                "POST",
                f"{CODEX_BACKEND_BASE_URL}/codex/responses",
                headers=headers,
                json=body,
            ) as response:
                snapshot = _parse_quota_snapshot(
                    response.headers,
                    status_code=response.status_code,
                    model=candidate_model,
                )
                if snapshot:
                    response.close()
                    return snapshot
                if response.status_code >= 400:
                    response.read()
                    message = _extract_error_message(response)
                    if _is_unsupported_codex_model_response(response):
                        last_error = message
                        continue
                    raise ValueError(message)
                response.close()
                last_error = "Codex limit probe response did not include quota headers"
    raise ValueError(last_error or "Codex limit probe response did not include quota headers")


def _mark_file_health(
    item: dict[str, Any],
    *,
    status: str,
    checked_at: datetime,
    error: str | None = None,
    replacement_bytes: bytes | None = None,
    limit_status: str | None = None,
    quota_snapshot: dict[str, Any] | None = None,
    limit_error: str | None = None,
) -> dict[str, Any]:
    updated = dict(item)
    updated["health_status"] = status
    updated["last_checked_at"] = checked_at.isoformat()
    updated["last_health_error"] = error
    if limit_status is not None:
        updated["limit_status"] = limit_status
        updated["quota_snapshot"] = quota_snapshot
        updated["last_limit_checked_at"] = checked_at.isoformat()
        updated["last_limit_error"] = limit_error
    if replacement_bytes is not None:
        cipher = _build_cipher()
        updated["encrypted_payload"] = cipher.encrypt(replacement_bytes).decode("utf-8")
        updated["sha256"] = hashlib.sha256(replacement_bytes).hexdigest()
        updated["size_bytes"] = len(replacement_bytes)
    return updated


def check_codex_auth_health(db: Session, *, force: bool = False) -> CodexAuthStatusResponse:
    settings = get_settings()
    row, store = _load_store(db)
    files = list(store.get("files", []))
    if not files:
        return get_codex_auth_status(db)

    now = datetime.now(timezone.utc)
    interval = max(60, settings.codex_auth_health_check_interval_seconds)
    cipher = _build_cipher()
    changed = False
    checked_files: list[dict[str, Any]] = []
    for item in files:
        if str(item.get("file_name")) != AUTH_JSON_FILE_NAME:
            checked_files.append(item)
            continue
        last_checked_at = _parse_datetime(item.get("last_checked_at"))
        if not force and last_checked_at and (now - last_checked_at).total_seconds() < interval:
            checked_files.append(item)
            continue

        encrypted = item.get("encrypted_payload")
        try:
            if not isinstance(encrypted, str):
                raise ValueError("Stored auth payload is missing")
            raw_bytes = cipher.decrypt(encrypted.encode("utf-8"))
            existing_tokens = _extract_auth_tokens(raw_bytes)
            refresh_token = str(existing_tokens.get("refresh_token") or "").strip()
            if not refresh_token:
                raise ValueError("Stored auth.json is missing refresh_token")
            refreshed = _request_codex_token_refresh(refresh_token)
            if not refreshed.get("refresh_token"):
                refreshed["refresh_token"] = refresh_token
            if not refreshed.get("id_token") and existing_tokens.get("id_token"):
                refreshed["id_token"] = existing_tokens["id_token"]
            if not refreshed.get("account_id") and existing_tokens.get("account_id"):
                refreshed["account_id"] = existing_tokens["account_id"]
            replacement = _build_codex_auth_json(refreshed)
            limit_status: str | None = None
            quota_snapshot: dict[str, Any] | None = None
            limit_error: str | None = None
            if settings.codex_auth_limit_probe_enabled:
                try:
                    quota_snapshot = _probe_codex_limits(
                        {**existing_tokens, **refreshed},
                        model=settings.codex_auth_limit_probe_model,
                        fallback_models=settings.codex_auth_limit_probe_fallback_models,
                    )
                    limit_status = _quota_status(quota_snapshot)
                except Exception as limit_exc:  # noqa: BLE001
                    limit_status = "check_failed"
                    limit_error = str(limit_exc)
            checked_files.append(
                _mark_file_health(
                    item,
                    status="valid",
                    checked_at=now,
                    replacement_bytes=replacement,
                    limit_status=limit_status,
                    quota_snapshot=quota_snapshot,
                    limit_error=limit_error,
                )
            )
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            invalid = "invalid" in error.lower() or "401" in error or "403" in error
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
    return get_codex_auth_status(db)


def start_codex_device_auth(db: Session, *, tag: str) -> CodexDeviceAuthStartResponse:
    settings = get_settings()
    normalized_tag = normalize_auth_tag(tag)
    with httpx.Client(timeout=httpx.Timeout(20.0), headers={"Accept": "application/json"}) as client:
        response = client.post(
            CODEX_DEVICE_USERCODE_URL,
            json={"client_id": CODEX_OAUTH_CLIENT_ID},
            headers={"Content-Type": "application/json"},
        )
    if response.status_code != 200:
        raise ValueError(f"Codex device auth start failed with status {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Codex device auth start returned invalid JSON")

    user_code = str(payload.get("user_code") or "").strip()
    device_auth_id = str(payload.get("device_auth_id") or payload.get("device_code") or "").strip()
    if not user_code or not device_auth_id:
        raise ValueError("Codex device auth start response was missing user_code or device_auth_id")

    interval_seconds = max(3, int(payload.get("interval") or 5))
    expires_in = int(payload.get("expires_in") or settings.codex_auth_device_flow_timeout_seconds)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in))
    flow_id = str(uuid.uuid4())
    cipher = _build_cipher()

    row, store = _load_store(db)
    flows = [
        flow
        for flow in list(store.get("device_flows", []))
        if _parse_datetime(flow.get("expires_at")) and _parse_datetime(flow.get("expires_at")) > datetime.now(timezone.utc)
    ]
    flows.append(
        {
            "id": flow_id,
            "tag": normalized_tag,
            "user_code": user_code,
            "encrypted_device_auth_id": cipher.encrypt(device_auth_id.encode("utf-8")).decode("utf-8"),
            "interval_seconds": interval_seconds,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }
    )
    store["device_flows"] = flows
    _save_store(db, row, store)
    return CodexDeviceAuthStartResponse(
        flow_id=flow_id,
        tag=normalized_tag,
        user_code=user_code,
        verification_uri=CODEX_DEVICE_VERIFICATION_URI,
        expires_at=expires_at,
        interval_seconds=interval_seconds,
    )


def _exchange_device_authorization_code(authorization_code: str, code_verifier: str) -> dict[str, Any]:
    with httpx.Client(timeout=httpx.Timeout(20.0), headers={"Accept": "application/json"}) as client:
        response = client.post(
            CODEX_OAUTH_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": CODEX_DEVICE_REDIRECT_URI,
                "client_id": CODEX_OAUTH_CLIENT_ID,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if response.status_code != 200:
        raise ValueError(f"Codex token exchange failed with status {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Codex token exchange returned invalid JSON")
    return payload


def poll_codex_device_auth(db: Session, *, flow_id: str) -> CodexDeviceAuthPollResponse:
    row, store = _load_store(db)
    flows = list(store.get("device_flows", []))
    flow = next((item for item in flows if str(item.get("id")) == flow_id), None)
    if flow is None:
        raise ValueError("Codex device auth flow not found")

    tag = normalize_auth_tag(str(flow.get("tag") or "default"))
    expires_at = _parse_datetime(flow.get("expires_at"))
    if expires_at is None or expires_at <= datetime.now(timezone.utc):
        store["device_flows"] = [item for item in flows if str(item.get("id")) != flow_id]
        _save_store(db, row, store)
        return CodexDeviceAuthPollResponse(flow_id=flow_id, tag=tag, status="expired", message="Device auth code expired")

    encrypted_device_auth_id = flow.get("encrypted_device_auth_id")
    if not isinstance(encrypted_device_auth_id, str):
        raise ValueError("Codex device auth flow is missing device_auth_id")
    try:
        device_auth_id = _build_cipher().decrypt(encrypted_device_auth_id.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Codex device auth flow could not be decrypted") from exc

    user_code = str(flow.get("user_code") or "").strip()
    with httpx.Client(timeout=httpx.Timeout(20.0), headers={"Accept": "application/json"}) as client:
        response = client.post(
            CODEX_DEVICE_TOKEN_URL,
            json={"device_auth_id": device_auth_id, "user_code": user_code},
            headers={"Content-Type": "application/json"},
        )

    if response.status_code in {403, 404}:
        return CodexDeviceAuthPollResponse(flow_id=flow_id, tag=tag, status="pending", message="Waiting for device authorization")
    if response.status_code != 200:
        raise ValueError(f"Codex device auth polling failed with status {response.status_code}")

    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Codex device auth polling returned invalid JSON")
    authorization_code = str(payload.get("authorization_code") or "").strip()
    code_verifier = str(payload.get("code_verifier") or "").strip()
    if not authorization_code or not code_verifier:
        raise ValueError("Codex device auth polling response was missing authorization_code or code_verifier")

    token_payload = _exchange_device_authorization_code(authorization_code, code_verifier)
    auth_json = _build_codex_auth_json(token_payload)
    auth_file = _store_codex_auth_file(
        db,
        tag=tag,
        file_name=AUTH_JSON_FILE_NAME,
        raw_bytes=auth_json,
        source="device_auth",
        health_status="valid",
        last_checked_at=datetime.now(timezone.utc),
    )

    row, store = _load_store(db)
    store["device_flows"] = [item for item in list(store.get("device_flows", [])) if str(item.get("id")) != flow_id]
    _save_store(db, row, store)
    return CodexDeviceAuthPollResponse(
        flow_id=flow_id,
        tag=tag,
        status="authorized",
        message="Codex device auth completed",
        auth_file=auth_file,
        auth_status=get_codex_auth_status(db),
    )


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
