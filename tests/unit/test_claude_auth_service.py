from __future__ import annotations

import base64
import hashlib
import json

import pytest

from control_plane.app.services.claude_auth_service import (
    CREDENTIALS_FILE_NAME,
    _build_claude_credentials_json,
    _build_pkce_pair,
    _extract_oauth_from_bytes,
    _token_needs_refresh,
)


def test_credentials_file_name_is_claude_dotfile() -> None:
    assert CREDENTIALS_FILE_NAME == ".credentials.json"


def test_build_claude_credentials_shape() -> None:
    raw, expires_at = _build_claude_credentials_json(
        {
            "access_token": "acc",
            "refresh_token": "ref",
            "expires_in": 3600,
            "scope": "user:inference user:profile",
        }
    )
    payload = json.loads(raw)
    oauth = payload["claudeAiOauth"]
    assert oauth["accessToken"] == "acc"
    assert oauth["refreshToken"] == "ref"
    assert oauth["scopes"] == ["user:inference", "user:profile"]
    assert oauth["expiresAt"] > 0
    assert expires_at is not None


def test_build_claude_credentials_uses_fallback_scopes() -> None:
    raw, _ = _build_claude_credentials_json(
        {"access_token": "acc", "refresh_token": "ref"},
        fallback_scopes=["user:inference"],
    )
    payload = json.loads(raw)
    assert payload["claudeAiOauth"]["scopes"] == ["user:inference"]
    # No expires_in -> expiresAt 0 (treated as non-expiring by the CLI/refresh path).
    assert payload["claudeAiOauth"]["expiresAt"] == 0


def test_build_claude_credentials_requires_access_token() -> None:
    with pytest.raises(ValueError):
        _build_claude_credentials_json({"refresh_token": "ref"})


def test_pkce_pair_is_valid_s256() -> None:
    verifier, challenge = _build_pkce_pair()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("utf-8")).digest())
        .decode("utf-8")
        .rstrip("=")
    )
    assert challenge == expected
    # PKCE verifiers must be URL-safe with no padding.
    assert "=" not in verifier
    assert "+" not in verifier and "/" not in verifier


def test_extract_oauth_from_bytes() -> None:
    raw = json.dumps({"claudeAiOauth": {"accessToken": "x", "refreshToken": "y"}}).encode()
    oauth = _extract_oauth_from_bytes(raw)
    assert oauth["accessToken"] == "x"
    assert _extract_oauth_from_bytes(b"not json") == {}


def test_token_needs_refresh() -> None:
    from datetime import datetime, timedelta, timezone

    assert _token_needs_refresh(None) is False
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    assert _token_needs_refresh(past) is True
    assert _token_needs_refresh(future) is False
