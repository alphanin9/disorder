from __future__ import annotations

from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.app.adapters.ctfd import (
    CTFdClient,
    extract_file_entries,
    normalize_description,
    parse_remote_endpoints,
)
from control_plane.app.db.models import ChallengeManifest, IntegrationConfig
from control_plane.app.schemas.integration import CTFdSyncRequest
from control_plane.app.services.challenge_service import ensure_ctf_for_sync
from control_plane.app.services.ctfd_config_service import (
    get_ctfd_config_response as get_ctfd_config_response_for_ctf,
    get_ctfd_decrypted_credentials,
    upsert_ctfd_config as upsert_ctfd_config_for_ctf,
)
from control_plane.app.store import get_blob_store
from control_plane.app.store.minio import artifact_object_key, sha256_bytes


def get_ctfd_config(db: Session) -> dict | None:
    stmt = select(IntegrationConfig).where(IntegrationConfig.name == "ctfd")
    row = db.execute(stmt).scalar_one_or_none()
    return row.config_json if row else None


def upsert_ctfd_config(db: Session, base_url: str, api_token: str) -> IntegrationConfig:
    stmt = select(IntegrationConfig).where(IntegrationConfig.name == "ctfd")
    existing = db.execute(stmt).scalar_one_or_none()
    if existing is None:
        existing = IntegrationConfig(name="ctfd", config_json={})
        db.add(existing)
    existing.config_json = {"base_url": base_url.rstrip("/"), "api_token": api_token}
    existing.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(existing)
    return existing


def _resolve_auth_mode(request: CTFdSyncRequest) -> str:
    if request.auth_mode is not None:
        return request.auth_mode
    if request.session_cookie:
        return "session_cookie"
    if request.api_token:
        return "api_token"
    return "session_cookie"


def _friendly_ctfd_http_error_message(auth_mode: str, exc: httpx.HTTPStatusError) -> str | None:
    status_code = exc.response.status_code
    redirect_codes = {301, 302, 303, 307, 308}
    location = (exc.response.headers.get("location") or "").lower()

    if auth_mode == "session_cookie":
        if status_code in redirect_codes and "/login" in location:
            return "CTFd session cookie is invalid or expired. Paste a fresh session cookie and try again."
        if status_code in {401, 403}:
            return "CTFd session cookie is invalid or expired. Paste a fresh session cookie and try again."

    if auth_mode == "api_token" and status_code in {401, 403}:
        return "CTFd API token is invalid or missing required permissions."

    return None


def sync_ctfd_challenges(db: Session, request: CTFdSyncRequest) -> dict:
    legacy_config = get_ctfd_config(db) or {}
    base_url = str(request.base_url) if request.base_url else legacy_config.get("base_url")
    auth_mode = _resolve_auth_mode(request)
    session_cookie = (request.session_cookie or "").strip()
    api_token = (request.api_token or "").strip() or None

    if not base_url:
        raise ValueError("CTFd integration is not configured. Provide base_url.")

    ctf_event = ensure_ctf_for_sync(db, base_url=base_url)
    per_ctf_creds = get_ctfd_decrypted_credentials(db, ctf_event.id) or {}
    configured_api_token = str(per_ctf_creds.get("api_token") or "").strip() or None
    configured_session_cookie = str(per_ctf_creds.get("session_cookie") or "").strip() or None
    if not api_token:
        legacy_api_token = str(legacy_config.get("api_token") or "").strip() or None
        legacy_base_url = str(legacy_config.get("base_url") or "").strip()
        if configured_api_token:
            api_token = configured_api_token
        elif legacy_api_token and legacy_base_url.rstrip("/") == str(base_url).rstrip("/"):
            api_token = legacy_api_token

    if not session_cookie and configured_session_cookie:
        session_cookie = configured_session_cookie

    if auth_mode == "session_cookie":
        if not session_cookie:
            raise ValueError("CTFd sync with session_cookie auth requires session_cookie.")
        client = CTFdClient(base_url=base_url, session_cookie=session_cookie)
    else:
        if not api_token:
            raise ValueError("CTFd integration is not configured. Provide base_url and api_token.")
        client = CTFdClient(base_url=base_url, api_token=api_token)

    blob_store = get_blob_store()

    try:
        summaries = client.list_challenges()
        synced = 0

        for summary in summaries:
            details = client.get_challenge(summary.challenge_id)
            description_raw = str(details.get("description") or "")
            description_md = normalize_description(description_raw)
            remote_endpoints = parse_remote_endpoints(description_md)

            artifacts: list[dict] = []
            file_entries = extract_file_entries(details)
            for file_entry in file_entries:
                file_bytes = client.download_file(file_entry["url"])
                sha_hex = sha256_bytes(file_bytes)
                object_key = artifact_object_key(
                    platform="ctfd",
                    challenge_id=summary.challenge_id,
                    file_name=file_entry["name"],
                    sha256_hex=sha_hex,
                    scope=str(ctf_event.id),
                )
                if not blob_store.object_exists(object_key):
                    blob_store.put_bytes(object_key=object_key, data=file_bytes)
                artifacts.append(
                    {
                        "name": file_entry["name"],
                        "sha256": sha_hex,
                        "size_bytes": len(file_bytes),
                        "object_key": object_key,
                    }
                )

            local_deploy_hints = {
                "compose_present": any(a["name"] in {"docker-compose.yml", "compose.yml"} for a in artifacts),
                "notes": None,
            }

            query = select(ChallengeManifest).where(
                ChallengeManifest.ctf_id == ctf_event.id,
                ChallengeManifest.platform == "ctfd",
                ChallengeManifest.platform_challenge_id == summary.challenge_id,
            )
            existing = db.execute(query).scalar_one_or_none()
            if existing is None:
                existing = ChallengeManifest(platform="ctfd", platform_challenge_id=summary.challenge_id)
                db.add(existing)

            existing.ctf_id = ctf_event.id
            existing.name = summary.name
            existing.category = summary.category
            existing.points = summary.points
            existing.description_md = description_md
            existing.description_raw = description_raw
            existing.artifacts = artifacts
            existing.remote_endpoints = remote_endpoints
            existing.local_deploy_hints = local_deploy_hints
            existing.synced_at = datetime.now(timezone.utc)

            synced += 1

        db.commit()
        if auth_mode == "api_token" and api_token:
            upsert_ctfd_config(db, base_url=base_url, api_token=api_token)
        elif auth_mode == "session_cookie":
            legacy_api_token = str(legacy_config.get("api_token") or "").strip() or None
            if legacy_api_token:
                upsert_ctfd_config(db, base_url=base_url, api_token=legacy_api_token)
            else:
                stmt = select(IntegrationConfig).where(IntegrationConfig.name == "ctfd")
                existing = db.execute(stmt).scalar_one_or_none()
                if existing is None:
                    existing = IntegrationConfig(name="ctfd", config_json={})
                    db.add(existing)
                existing.config_json = {"base_url": str(base_url).rstrip("/")}
                existing.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(existing)
        upsert_ctfd_config_for_ctf(
            db,
            ctf_id=ctf_event.id,
            base_url=base_url,
            preferred_auth_mode=auth_mode,
            last_sync_auth_mode=auth_mode,
            api_token=api_token if auth_mode == "api_token" else None,
            session_cookie=session_cookie if auth_mode == "session_cookie" else None,
        )
        per_ctf_config = get_ctfd_config_response_for_ctf(db, ctf_event.id)
        return {
            "synced": synced,
            "platform": "ctfd",
            "ctf_id": str(ctf_event.id),
            "ctf_slug": ctf_event.slug,
            "auth_mode_used": auth_mode,
            "stored_auth_modes": per_ctf_config.get("stored_auth_modes", []),
        }
    except httpx.HTTPStatusError as exc:
        message = _friendly_ctfd_http_error_message(auth_mode=auth_mode, exc=exc)
        if message:
            raise ValueError(message) from exc
        raise ValueError(f"CTFd request failed with HTTP {exc.response.status_code}.") from exc
    except httpx.RequestError as exc:
        raise ValueError("Unable to reach CTFd. Check base URL and network connectivity.") from exc
    finally:
        client.close()
