from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.app.adapters.ctfd import CTFdClient
from control_plane.app.core.config import get_settings
from control_plane.app.db.models import ChallengeManifest, FlagSubmissionAttempt
from control_plane.app.services.ctfd_config_service import mark_ctfd_submit_result, resolve_ctfd_auth_candidates


@dataclass(slots=True)
class SubmissionAttemptOutcome:
    normalized_verdict: str
    verified: bool
    details: str
    auth_mode: str | None
    http_status: int | None
    response_payload: dict[str, Any]
    error_message: str | None = None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ctfd_response_text(payload: dict[str, Any]) -> str:
    for key in ("status", "message", "result"):
        value = payload.get(key)
        if value is not None:
            return str(value)
    return "unknown"


def _normalize_ctfd_verdict(payload: dict[str, Any]) -> tuple[str, bool, str]:
    text = _ctfd_response_text(payload)
    lowered = text.lower()
    if "correct" in lowered:
        return "correct", True, text
    if "already" in lowered or "solved" in lowered:
        return "already_solved", True, text
    if "rate" in lowered:
        return "rate_limited", False, text
    if any(token in lowered for token in ("incorrect", "wrong", "invalid")):
        return "incorrect", False, text
    return "unknown", False, text


def _classify_ctfd_http_error(auth_mode: str | None, exc: httpx.HTTPStatusError) -> tuple[str, str, bool, int | None]:
    status_code = exc.response.status_code
    redirect_codes = {301, 302, 303, 307, 308}
    location = (exc.response.headers.get("location") or "").lower()
    if auth_mode == "session_cookie" and status_code in redirect_codes and "/login" in location:
        return "error", "CTFd session cookie is invalid or expired (redirected to login).", True, status_code
    if auth_mode == "session_cookie" and status_code in {401, 403}:
        return "error", "CTFd session cookie is invalid or expired.", True, status_code
    if auth_mode == "api_token" and status_code in {401, 403}:
        return "error", "CTFd API token is invalid or missing required permissions.", True, status_code
    if status_code == 429:
        return "rate_limited", "CTFd rate limited flag submission.", False, status_code
    return "error", f"CTFd request failed with HTTP {status_code}.", False, status_code


def _record_flag_submission_attempt(
    db: Session,
    *,
    run_id: UUID | str,
    challenge: ChallengeManifest,
    auth_mode: str | None,
    flag: str,
    verdict_normalized: str,
    http_status: int | None,
    error_message: str | None,
    request_payload_json: dict[str, Any],
    response_payload_json: dict[str, Any],
) -> None:
    row = FlagSubmissionAttempt(
        run_id=run_id,
        challenge_id=challenge.id,
        platform=challenge.platform,
        auth_mode=auth_mode,
        submission_hash=_sha256_text(flag),
        verdict_normalized=verdict_normalized,
        http_status=http_status,
        error_message=error_message,
        request_payload_json=request_payload_json,
        response_payload_json=response_payload_json,
    )
    db.add(row)
    db.flush()


def _run_submission_attempt_count(db: Session, run_id: UUID | str) -> int:
    stmt = select(FlagSubmissionAttempt).where(FlagSubmissionAttempt.run_id == run_id)
    return len(list(db.execute(stmt).scalars().all()))


def _has_duplicate_submission_hash(db: Session, run_id: UUID | str, flag_hash: str) -> bool:
    stmt = (
        select(FlagSubmissionAttempt.id)
        .where(FlagSubmissionAttempt.run_id == run_id, FlagSubmissionAttempt.submission_hash == flag_hash)
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def _latest_attempt_for_submission_hash(
    db: Session,
    run_id: UUID | str,
    flag_hash: str,
) -> FlagSubmissionAttempt | None:
    stmt = (
        select(FlagSubmissionAttempt)
        .where(FlagSubmissionAttempt.run_id == run_id, FlagSubmissionAttempt.submission_hash == flag_hash)
        .order_by(FlagSubmissionAttempt.submitted_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def _verification_from_prior_attempt(prior: FlagSubmissionAttempt) -> dict[str, Any]:
    verified = prior.verdict_normalized in {"correct", "already_solved"}
    details = f"Reused prior CTFd submission attempt verdict: {prior.verdict_normalized}."
    if prior.auth_mode:
        details += f" auth={prior.auth_mode}."
    if prior.http_status is not None:
        details += f" http_status={prior.http_status}."
    if prior.error_message:
        details += f" error={prior.error_message[:160]}."
    return {
        "method": "platform_submit",
        "verified": verified,
        "details": details,
    }


def _attempt_ctfd_submit(
    *,
    challenge: ChallengeManifest,
    flag: str,
    base_url: str,
    auth_mode: str,
    secret: str,
) -> SubmissionAttemptOutcome:
    client_kwargs: dict[str, Any] = {"base_url": base_url}
    if auth_mode == "api_token":
        client_kwargs["api_token"] = secret
    else:
        client_kwargs["session_cookie"] = secret

    client = CTFdClient(**client_kwargs)
    try:
        payload = client.submit_flag(challenge.platform_challenge_id, flag)
        verdict_normalized, verified, verdict_text = _normalize_ctfd_verdict(payload)
        return SubmissionAttemptOutcome(
            normalized_verdict=verdict_normalized,
            verified=verified,
            details=f"CTFd submission verdict: {verdict_text}",
            auth_mode=auth_mode,
            http_status=200,
            response_payload=payload if isinstance(payload, dict) else {"raw": payload},
        )
    except httpx.HTTPStatusError as exc:
        normalized_verdict, detail, allow_fallback, http_status = _classify_ctfd_http_error(auth_mode, exc)
        error_payload: dict[str, Any] = {"kind": "http_error", "status_code": http_status}
        location = exc.response.headers.get("location")
        if location:
            error_payload["location"] = location
        error_payload["body_preview"] = exc.response.text[:512]
        outcome = SubmissionAttemptOutcome(
            normalized_verdict=normalized_verdict,
            verified=False,
            details=detail,
            auth_mode=auth_mode,
            http_status=http_status,
            response_payload=error_payload,
            error_message=str(exc),
        )
        # encode fallback allowance for caller via response payload marker to avoid another result type
        outcome.response_payload["_allow_fallback"] = allow_fallback
        return outcome
    except httpx.RequestError as exc:
        return SubmissionAttemptOutcome(
            normalized_verdict="error",
            verified=False,
            details="Unable to reach CTFd for flag submission.",
            auth_mode=auth_mode,
            http_status=None,
            response_payload={"kind": "request_error"},
            error_message=str(exc),
        )
    except Exception as exc:  # pragma: no cover - defensive
        return SubmissionAttemptOutcome(
            normalized_verdict="error",
            verified=False,
            details="Unexpected error during CTFd flag submission.",
            auth_mode=auth_mode,
            http_status=None,
            response_payload={"kind": "unexpected_error"},
            error_message=str(exc),
        )
    finally:
        client.close()


def _regex_fallback_verification(flag: str, regex: str | None, platform_error: str | None) -> dict[str, Any]:
    if regex:
        try:
            matched = bool(re.search(regex, flag))
            details = f"Regex verification {'matched' if matched else 'did not match'} pattern: {regex}"
            if platform_error:
                details += f"; platform submit unavailable: {platform_error}"
            return {"method": "regex_only", "verified": matched, "details": details}
        except re.error as exc:
            platform_error = f"Invalid regex pattern: {exc}"

    return {
        "method": "none",
        "verified": False,
        "details": platform_error or "No verification method configured.",
    }


def build_flag_verification(
    db: Session,
    *,
    run_id: UUID | str,
    challenge: ChallengeManifest,
    flag: str,
    regex: str | None,
) -> dict[str, Any]:
    normalized_flag = str(flag or "").strip()
    if not normalized_flag:
        return {
            "method": "none",
            "verified": False,
            "details": "Run reached flag_found without a concrete flag value.",
        }

    settings = get_settings()
    platform_error: str | None = None
    if challenge.platform == "ctfd":
        if not settings.ctfd_auto_submit_enabled:
            platform_error = "CTFd auto-submit is disabled by configuration."
        else:
            max_attempts = max(1, int(settings.ctfd_auto_submit_max_attempts_per_run))
            existing_attempts = _run_submission_attempt_count(db, run_id)
            if existing_attempts >= max_attempts:
                platform_error = f"CTFd auto-submit skipped: per-run attempt cap reached ({max_attempts})."
            else:
                submission_hash = _sha256_text(normalized_flag)
                if _has_duplicate_submission_hash(db, run_id, submission_hash):
                    prior_attempt = _latest_attempt_for_submission_hash(db, run_id, submission_hash)
                    if prior_attempt is not None:
                        return _verification_from_prior_attempt(prior_attempt)
                    platform_error = "CTFd auto-submit skipped: duplicate flag candidate already submitted for this run."
                else:
                    candidates = resolve_ctfd_auth_candidates(db, ctf_id=challenge.ctf_id)
                    if not candidates:
                        platform_error = "No per-CTF CTFd credentials configured for this challenge."
                    else:
                        last_outcome: SubmissionAttemptOutcome | None = None
                        for index, candidate in enumerate(candidates):
                            outcome = _attempt_ctfd_submit(
                                challenge=challenge,
                                flag=normalized_flag,
                                base_url=candidate.base_url,
                                auth_mode=candidate.mode,
                                secret=candidate.secret,
                            )
                            last_outcome = outcome

                            _record_flag_submission_attempt(
                                db,
                                run_id=run_id,
                                challenge=challenge,
                                auth_mode=candidate.mode,
                                flag=normalized_flag,
                                verdict_normalized=outcome.normalized_verdict,
                                http_status=outcome.http_status,
                                error_message=outcome.error_message,
                                request_payload_json={
                                    "challenge_id": challenge.platform_challenge_id,
                                    "submission_sha256": submission_hash,
                                    "submission_length": len(normalized_flag),
                                },
                                response_payload_json=outcome.response_payload,
                            )

                            if outcome.normalized_verdict not in {"error"}:
                                mark_ctfd_submit_result(
                                    db,
                                    ctf_id=challenge.ctf_id,
                                    auth_mode=candidate.mode,
                                    status=outcome.normalized_verdict,
                                    commit=False,
                                )
                                return {
                                    "method": "platform_submit",
                                    "verified": outcome.verified,
                                    "details": outcome.details,
                                }

                            mark_ctfd_submit_result(
                                db,
                                ctf_id=challenge.ctf_id,
                                auth_mode=candidate.mode,
                                status=outcome.normalized_verdict,
                                commit=False,
                            )

                            allow_fallback = bool(outcome.response_payload.get("_allow_fallback"))
                            has_more = index + 1 < len(candidates)
                            if not (allow_fallback and has_more):
                                break

                        if last_outcome is not None:
                            platform_error = last_outcome.details

    return _regex_fallback_verification(normalized_flag, regex, platform_error)


def list_run_flag_submission_attempts(db: Session, run_id: UUID | str) -> list[FlagSubmissionAttempt]:
    stmt = (
        select(FlagSubmissionAttempt)
        .where(FlagSubmissionAttempt.run_id == run_id)
        .order_by(FlagSubmissionAttempt.submitted_at.asc())
    )
    return db.execute(stmt).scalars().all()
